"""
后台处理模块

职责:
- 文件处理（分块 + 向量生成 + 入库）
- 异步任务执行
- 进度更新
"""

import asyncio
from pathlib import Path
from typing import List, Dict, Optional

from ..database import get_db_cursor
from ..settings import get_embedding_config
from ..utils import serialize_float32
from . import task_service, file_service, chunk_service
from .converter import convert_to_markdown
from .chunking import ChunkerFactory
from .rate_limiter import get_rate_limiter
from .embedding_client import get_embeddings_model


# ========== 向量生成 ==========


async def generate_embeddings(
    texts: List[str], embeddings_model, batch_size: int = 20
) -> List[List[float]]:
    """
    批量生成嵌入向量

    Args:
        texts: 文本列表
        embeddings_model: 嵌入模型实例
        batch_size: 每批处理数量

    Returns:
        向量列表
    """
    all_embeddings = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        # embed_documents 是同步方法，用 asyncio 包装
        batch_embeddings = await asyncio.to_thread(
            embeddings_model.embed_documents, batch
        )
        all_embeddings.extend(batch_embeddings)

    return all_embeddings


# ========== 数据库写入 ==========


def insert_chunks_batch(
    file_id: int, chunks: List[Dict], embeddings_list: List[List[float]],
    progress_callback=None
) -> None:
    """
    分批插入分块到数据库（异步优化，避免长时间锁定数据库）

    优化策略：
    - 每批写入 50 个切片，提交一次事务
    - 减少单次事务锁定时间
    - 支持进度回调（85%-100%）
    - 使用 executemany 批量插入（性能提升 10x）

    Args:
        file_id: 文件 ID
        chunks: 切片列表
        embeddings_list: 向量列表
        progress_callback: 进度回调函数 callback(progress)
    """
    import logging
    logger = logging.getLogger(__name__)

    batch_size = 50  # 每批写入 50 个切片
    total_chunks = len(chunks)

    logger.info(f"[批量写入] 开始写入: {total_chunks} 个切片, 批次大小: {batch_size}")

    for batch_start in range(0, total_chunks, batch_size):
        batch_end = min(batch_start + batch_size, total_chunks)
        batch_chunks = chunks[batch_start:batch_end]
        batch_embeddings = embeddings_list[batch_start:batch_end]

        # 单批次写入（使用连接池）
        with get_db_cursor() as cursor:
            # 准备批量插入数据
            vec_chunks_data = []

            for chunk, embedding in zip(batch_chunks, batch_embeddings):
                embedding_blob = serialize_float32(embedding)

                # 插入 chunks 表
                cursor.execute(
                    """
                    INSERT INTO chunks (file_id, doc_title, chunk_text, embedding)
                    VALUES (?, ?, ?, ?)
                    """,
                    (file_id, chunk["doc_title"], chunk["chunk_text"], embedding_blob),
                )

                chunk_id = cursor.lastrowid

                # 准备向量表数据
                vec_chunks_data.append((chunk_id, embedding_blob))

            # 批量插入向量表（性能优化）
            if vec_chunks_data:
                cursor.executemany(
                    """
                    INSERT INTO vec_chunks (chunk_id, embedding)
                    VALUES (?, ?)
                    """,
                    vec_chunks_data
                )

        logger.info(f"[批量写入] 批次 {batch_start//batch_size + 1}: 已写入 {batch_end}/{total_chunks} 个切片")

        # 更新进度（85%-100%）
        if progress_callback:
            progress = 85 + int(15 * batch_end / total_chunks)
            progress_callback(progress)

    logger.info(f"[批量写入] 完成: 共写入 {total_chunks} 个切片")


# ========== 任务处理 ==========


async def process_task(task_id: int) -> None:
    """
    处理单个任务

    流程:
    1. 获取关联的 file_id
    2. 转换文件为 Markdown 格式
    3. 分块处理
    4. 生成向量
    5. 写入 chunks + vec_chunks
    6. 更新状态为 indexed
    """
    task = await asyncio.to_thread(task_service.get_task, task_id)
    if not task:
        return

    file_id = task.get("file_id")
    if not file_id:
        await asyncio.to_thread(
            task_service.update_task_status,
            task_id,
            "failed",
            error_message="任务未关联文件",
        )
        return

    # 获取文件信息
    file_info = await asyncio.to_thread(file_service.get_file_by_id, file_id)
    if not file_info:
        await asyncio.to_thread(
            task_service.update_task_status,
            task_id,
            "failed",
            error_message="关联文件不存在",
        )
        return

    working_file_path = Path(file_info["file_path"])  # 工作文件路径
    original_file_path = Path(file_info["original_file_path"]) if file_info["original_file_path"] else None
    original_filename = file_info["filename"]

    try:
        # 更新状态为处理中
        await asyncio.to_thread(
            task_service.update_task_status,
            task_id,
            "processing",
            progress=5,
        )

        # 调试日志
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"[开始处理] 文件ID: {file_id}, 工作文件: {working_file_path}, 原始文件: {original_file_path}")

        # 检查文件是否存在
        if original_file_path:
            logger.info(f"[原始文件检查] 路径: {original_file_path}, 存在: {original_file_path.exists()}")
        logger.info(f"[工作文件检查] 路径: {working_file_path}, 存在: {working_file_path.exists()}")

        # 1. 从原始文件转换为 Markdown 格式
        # 如果有原始文件，从原始文件转换；否则直接读取工作文件（应用内新建的情况）
        if original_file_path and original_file_path.exists():
            logger.info(f"[转换模式] 从原始文件转换")

            # 定义 PDF 转换进度回调（优化：减少数据库更新频率）
            last_progress = [5]  # 使用列表存储可变值

            def pdf_progress_callback(current_page: int, total_pages: int):
                # 转换阶段占 5%-15%，映射到进度条
                progress = 5 + int(10 * current_page / total_pages)
                # 只在进度变化时更新（避免频繁数据库写入）
                if progress != last_progress[0]:
                    last_progress[0] = progress
                    try:
                        task_service.update_task_status(task_id, "processing", progress=progress)
                    except Exception as e:
                        # 进度更新失败不影响转换流程
                        logger.warning(f"[PDF转换] 进度更新失败: {e}")

            # 检查是否是 PDF 文件
            if original_file_path.suffix.lower() == '.pdf':
                from .converter import convert_pdf_to_markdown
                content = await asyncio.to_thread(
                    convert_pdf_to_markdown,
                    original_file_path,
                    pdf_progress_callback
                )
            else:
                # 非 PDF 文件：显示转换进度
                await asyncio.to_thread(
                    task_service.update_task_status,
                    task_id,
                    "processing",
                    progress=10,
                )
                content = await asyncio.to_thread(convert_to_markdown, original_file_path)
                await asyncio.to_thread(
                    task_service.update_task_status,
                    task_id,
                    "processing",
                    progress=15,
                )
        else:
            logger.info(f"[转换模式] 直接读取工作文件")
            # 应用内新建的文件，直接读取工作文件（异步读取）
            await asyncio.to_thread(
                task_service.update_task_status,
                task_id,
                "processing",
                progress=10,
            )
            import aiofiles
            async with aiofiles.open(working_file_path, "r", encoding="utf-8") as f:
                content = await f.read()
            await asyncio.to_thread(
                task_service.update_task_status,
                task_id,
                "processing",
                progress=15,
            )

        logger.info(f"[转换后] 内容长度: {len(content)}")

        # 将转换后的内容写入工作文件（异步写入，避免阻塞事件循环）
        import aiofiles
        async with aiofiles.open(working_file_path, "w", encoding="utf-8") as f:
            await f.write(content)

        logger.info(f"[处理文件] 文件名: {original_filename}, 内容长度: {len(content)}, 前100字符: {content[:100]}")

        # 2. 分块处理 - 使用工厂模式根据文件类型选择分块器
        await asyncio.to_thread(
            task_service.update_task_status,
            task_id,
            "processing",
            progress=20,
        )

        base_name = Path(original_filename).stem

        # 优先使用原始文件类型（如 pptx），如果没有则使用工作文件扩展名（如 md）
        original_file_type = file_info.get("original_file_type")
        if original_file_type:
            file_extension = f".{original_file_type}"  # 添加点号前缀
        else:
            # 应用内新建的文件，使用工作文件扩展名
            file_extension = working_file_path.suffix.lower()

        logger.info(f"[分块策略] 文件: {original_filename}, 原始类型: {original_file_type}, 扩展名: {file_extension}")

        try:
            chunker = ChunkerFactory.get_chunker(file_extension)
            await asyncio.to_thread(
                task_service.update_task_status,
                task_id,
                "processing",
                progress=25,
            )
            chunks = await asyncio.to_thread(chunker.chunk, content, base_name)
            await asyncio.to_thread(
                task_service.update_task_status,
                task_id,
                "processing",
                progress=30,
            )
        except ValueError as e:
            logger.error(f"[分块失败] {e}")
            await asyncio.to_thread(file_service.update_file_status, file_id, "error")
            await asyncio.to_thread(
                task_service.update_task_status,
                task_id,
                "failed",
                error_message=str(e),
            )
            return

        logger.info(f"[分块结果] 文件: {original_filename}, 分块数: {len(chunks) if chunks else 0}")

        if not chunks:
            await asyncio.to_thread(file_service.update_file_status, file_id, "error")
            await asyncio.to_thread(
                task_service.update_task_status,
                task_id,
                "failed",
                error_message="无有效分块",
            )
            return

        # 3. 生成向量
        config = get_embedding_config()
        if not config["api_key"]:
            await asyncio.to_thread(file_service.update_file_status, file_id, "error")
            await asyncio.to_thread(
                task_service.update_task_status,
                task_id,
                "failed",
                error_message="未配置 EMBEDDING_API_KEY",
            )
            return

        # 获取 embedding 实例（单例，复用连接）
        embeddings_model = get_embeddings_model()
        texts = [chunk["chunk_text"] for chunk in chunks]

        # 获取速率限制器
        rate_limiter = get_rate_limiter()
        logger.info(f"[向量生成] 速率限制器已初始化: RPM={rate_limiter.rpm}, 最小间隔={rate_limiter.min_interval}s")

        # 分批生成向量，更新进度
        embeddings_list = []
        batch_size = 10  # 每批 10 个切片（平衡 TPM 限制和请求效率）
        total_batches = (len(texts) + batch_size - 1) // batch_size

        logger.info(f"[向量生成] 开始生成向量: {len(texts)} 个切片, {total_batches} 批次")

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]

            # 请求速率许可（每个批次消耗 1 个令牌）
            logger.info(f"[向量生成] 批次 {i // batch_size + 1}: 请求速率许可")
            await rate_limiter.acquire(1)
            logger.info(f"[向量生成] 批次 {i // batch_size + 1}: 许可已获取，开始生成向量")

            # 生成向量（带重试）
            max_retries = 3
            retry_delay = 5  # 秒

            for retry in range(max_retries):
                try:
                    batch_embeddings = await asyncio.to_thread(
                        embeddings_model.embed_documents, batch
                    )
                    embeddings_list.extend(batch_embeddings)
                    break  # 成功，退出重试循环

                except Exception as e:
                    error_msg = str(e).lower()

                    # 判断是否是速率限制错误
                    if "429" in error_msg or "403" in error_msg or "rate limit" in error_msg:
                        if retry < max_retries - 1:
                            wait_time = retry_delay * (retry + 1)  # 递增等待时间
                            logger.warning(
                                f"[向量生成] API 速率限制错误，{wait_time}秒后重试 "
                                f"(第 {retry+1}/{max_retries} 次)"
                            )
                            await asyncio.sleep(wait_time)
                        else:
                            logger.error(f"[向量生成] 重试 {max_retries} 次后仍失败: {e}")
                            raise
                    else:
                        # 非速率限制错误，直接抛出
                        logger.error(f"[向量生成] API 调用失败: {e}")
                        raise

            # 更新进度 (30% - 80%)
            batch_idx = i // batch_size + 1
            progress = 30 + int(50 * batch_idx / total_batches)
            await asyncio.to_thread(
                task_service.update_task_status,
                task_id,
                "processing",
                progress=progress,
            )

            # 日志记录（每 50 批次）
            if batch_idx % 50 == 0:
                stats = rate_limiter.get_stats()
                logger.info(
                    f"[向量生成] 进度: {batch_idx}/{total_batches} 批次 "
                    f"(RPM 限制: {stats['rpm']}, 间隔: {stats['min_interval']:.3f}s)"
                )

        logger.info(f"[向量生成] 完成: 共生成 {len(embeddings_list)} 个向量")

        # 4. 写入数据库（分批写入，带进度回调）
        def write_progress_callback(progress: int):
            task_service.update_task_status(task_id, "processing", progress=progress)

        await asyncio.to_thread(
            insert_chunks_batch,
            file_id,
            chunks,
            embeddings_list,
            progress_callback=write_progress_callback
        )

        # 5. 更新文件状态
        await asyncio.to_thread(file_service.update_file_status, file_id, "indexed")

        # 6. 完成
        await asyncio.to_thread(
            task_service.update_task_status,
            task_id,
            "completed",
            progress=100,
        )

    except Exception as e:
        # 处理失败
        await asyncio.to_thread(
            task_service.update_task_status,
            task_id,
            "failed",
            error_message=str(e),
        )
        await asyncio.to_thread(file_service.update_file_status, file_id, "error")


# ========== 任务队列管理 ==========


class TaskProcessor:
    """任务处理器（后台运行）"""

    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """启动任务处理器"""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._process_loop())

    async def stop(self) -> None:
        """停止任务处理器"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _process_loop(self) -> None:
        """任务处理循环"""
        while self._running:
            # 获取待处理任务
            pending_tasks = task_service.get_pending_tasks()

            if pending_tasks:
                for task in pending_tasks:
                    if not self._running:
                        break
                    await self._dispatch_task(task)
            else:
                # 无任务时等待
                await asyncio.sleep(1)

    async def _dispatch_task(self, task: dict) -> None:
        """根据任务类型分发处理"""
        task_id = task["id"]
        error_message = task.get("error_message", "") or ""

        if error_message.startswith("CHUNK_UPDATE|"):
            # Chunk 内容更新任务
            await chunk_service.process_chunk_update_task(task_id)
        elif error_message.startswith("CHUNK_ADD|"):
            # Chunk 新增任务
            await chunk_service.process_chunk_add_task(task_id)
        else:
            # 默认：文件处理任务
            await process_task(task_id)


# 全局任务处理器实例
processor = TaskProcessor()
