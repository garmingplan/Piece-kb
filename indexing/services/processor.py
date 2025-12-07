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

from langchain_openai import OpenAIEmbeddings

from ..database import get_connection
from ..settings import get_embedding_config
from ..utils import serialize_float32
from . import task_service, file_service, chunk_service
from .converter import convert_to_markdown
from .chunker import split_by_headings


# ========== 向量生成 ==========


async def generate_embeddings(
    texts: List[str], embeddings_model: OpenAIEmbeddings, batch_size: int = 20
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
    file_id: int, chunks: List[Dict], embeddings_list: List[List[float]]
) -> None:
    """批量插入分块到数据库"""
    conn = get_connection()
    try:
        for chunk, embedding in zip(chunks, embeddings_list):
            embedding_blob = serialize_float32(embedding)

            # 插入 chunks 表
            cursor = conn.execute(
                """
                INSERT INTO chunks (file_id, doc_title, chunk_text, embedding)
                VALUES (?, ?, ?, ?)
                """,
                (file_id, chunk["doc_title"], chunk["chunk_text"], embedding_blob),
            )

            chunk_id = cursor.lastrowid

            # 插入向量表
            conn.execute(
                """
                INSERT INTO vec_chunks (chunk_id, embedding)
                VALUES (?, ?)
                """,
                (chunk_id, embedding_blob),
            )

        conn.commit()
    finally:
        conn.close()


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
    task = task_service.get_task(task_id)
    if not task:
        return

    file_id = task.get("file_id")
    if not file_id:
        task_service.update_task_status(
            task_id, "failed", error_message="任务未关联文件"
        )
        return

    # 获取文件信息
    file_info = file_service.get_file_by_id(file_id)
    if not file_info:
        task_service.update_task_status(
            task_id, "failed", error_message="关联文件不存在"
        )
        return

    file_path = Path(file_info["file_path"])
    original_filename = file_info["filename"]

    try:
        # 更新状态为处理中
        task_service.update_task_status(task_id, "processing", progress=5)

        # 1. 转换文件为 Markdown 格式
        content = await asyncio.to_thread(convert_to_markdown, file_path)

        task_service.update_task_status(task_id, "processing", progress=15)

        # 2. 分块处理
        base_name = Path(original_filename).stem
        chunks = split_by_headings(content, base_name)

        if not chunks:
            file_service.update_file_status(file_id, "error")
            task_service.update_task_status(
                task_id, "failed", error_message="无有效分块"
            )
            return

        task_service.update_task_status(task_id, "processing", progress=30)

        # 3. 生成向量
        config = get_embedding_config()
        if not config["api_key"]:
            file_service.update_file_status(file_id, "error")
            task_service.update_task_status(
                task_id, "failed", error_message="未配置 EMBEDDING_API_KEY"
            )
            return

        embeddings_model = OpenAIEmbeddings(**config)
        texts = [chunk["chunk_text"] for chunk in chunks]

        # 分批生成向量，更新进度
        embeddings_list = []
        batch_size = 20
        total_batches = (len(texts) + batch_size - 1) // batch_size

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            batch_embeddings = await asyncio.to_thread(
                embeddings_model.embed_documents, batch
            )
            embeddings_list.extend(batch_embeddings)

            # 更新进度 (30% - 80%)
            batch_idx = i // batch_size + 1
            progress = 30 + int(50 * batch_idx / total_batches)
            task_service.update_task_status(task_id, "processing", progress=progress)

        # 4. 写入数据库
        task_service.update_task_status(task_id, "processing", progress=85)
        insert_chunks_batch(file_id, chunks, embeddings_list)

        # 5. 更新文件状态
        file_service.update_file_status(file_id, "indexed")

        # 6. 完成
        task_service.update_task_status(task_id, "completed", progress=100)

    except Exception as e:
        # 处理失败
        task_service.update_task_status(task_id, "failed", error_message=str(e))
        file_service.update_file_status(file_id, "error")


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
