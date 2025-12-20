"""
Chunk 服务模块

职责:
- Chunk CRUD 操作（增删改查）
- 向量索引同步（vec_chunks）
- 文件状态联动（删除最后一个切片时删除整个文件）
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from langchain_openai import OpenAIEmbeddings

from ..database import get_connection
from ..settings import get_embedding_config
from ..utils import serialize_float32
from . import task_service
from . import file_service
from .rate_limiter import get_rate_limiter


# ========== 工作文件同步 ==========


def rebuild_working_file(file_id: int) -> None:
    """
    根据数据库中的切片重建工作文件

    将文件的所有切片按照 doc_title 重建为 Markdown 格式并写入工作文件

    Args:
        file_id: 文件 ID
    """
    # 获取文件信息
    file_info = file_service.get_file_by_id(file_id)
    if not file_info:
        return

    working_file_path = Path(file_info["file_path"])

    # 获取所有切片
    chunks = file_service.get_chunks_by_file_id(file_id)
    if not chunks:
        # 没有切片，清空工作文件
        working_file_path.write_text("", encoding="utf-8")
        return

    # 重建 Markdown 内容
    lines = []
    for chunk in chunks:
        doc_title = chunk["doc_title"]
        chunk_text = chunk["chunk_text"]

        # 检查 chunk_text 是否已经包含标题（以 # 开头）
        if chunk_text.strip().startswith('#'):
            # chunk_text 已包含标题，直接输出
            lines.append(f"{chunk_text}\n\n")
            continue

        # 根据 doc_title 中的下划线数量判断标题级别
        # 格式: "文件名_章节" 或 "文件名_章节_小节"
        title_parts = doc_title.split("_")

        if len(title_parts) == 2:
            # 二级标题
            clean_title = title_parts[1].lstrip('#').strip()
            lines.append(f"## {clean_title}\n\n")
        elif len(title_parts) >= 3:
            # 三级标题
            clean_title = title_parts[-1].lstrip('#').strip()
            lines.append(f"### {clean_title}\n\n")
        else:
            # 兜底：doc_title 格式不规范（无下划线或只有文件名）
            # 使用完整的 doc_title 作为二级标题
            clean_title = doc_title.lstrip('#').strip()
            lines.append(f"## {clean_title}\n\n")

        lines.append(f"{chunk_text}\n\n")

    # 写入工作文件
    working_file_path.write_text("".join(lines), encoding="utf-8")


# ========== 查询操作 ==========


def get_chunk_by_id(chunk_id: int) -> Optional[Dict[str, Any]]:
    """根据 ID 获取 chunk 信息"""
    conn = get_connection()
    try:
        result = conn.execute(
            "SELECT id, file_id, doc_title, chunk_text FROM chunks WHERE id = ?",
            (chunk_id,)
        ).fetchone()
        return dict(result) if result else None
    finally:
        conn.close()


def get_chunks_count_by_file_id(file_id: int) -> int:
    """获取文件的 chunk 数量"""
    conn = get_connection()
    try:
        result = conn.execute(
            "SELECT COUNT(*) as count FROM chunks WHERE file_id = ?",
            (file_id,)
        ).fetchone()
        return result["count"]
    finally:
        conn.close()


# ========== 删除操作 ==========


def delete_chunk(chunk_id: int) -> Dict[str, Any]:
    """
    删除单个 chunk

    流程:
    1. 获取 chunk 信息（file_id）
    2. 检查是否为文件的最后一个切片
    3. 如果是最后一个切片，删除整个文件（包括原始文件）
    4. 否则，只删除该切片

    Returns:
        {"success": bool, "file_id": int, "file_deleted": bool}
    """
    conn = get_connection()
    try:
        # 1. 获取 chunk 信息
        chunk = conn.execute(
            "SELECT file_id FROM chunks WHERE id = ?", (chunk_id,)
        ).fetchone()

        if not chunk:
            return {"success": False, "error": "Chunk 不存在"}

        file_id = chunk["file_id"]

        # 2. 检查是否为最后一个切片
        remaining = conn.execute(
            "SELECT COUNT(*) as count FROM chunks WHERE file_id = ?", (file_id,)
        ).fetchone()["count"]

        if remaining == 1:
            # 最后一个切片，删除整个文件
            conn.close()  # 先关闭连接，file_service 会创建新连接
            success = file_service.delete_file(file_id)
            return {"success": success, "file_id": file_id, "file_deleted": True}

        # 3. 删除 vec_chunks 记录（手动，无外键）
        conn.execute("DELETE FROM vec_chunks WHERE chunk_id = ?", (chunk_id,))

        # 4. 删除 chunks 记录（FTS5 触发器自动同步）
        conn.execute("DELETE FROM chunks WHERE id = ?", (chunk_id,))

        conn.commit()

        # 5. 重建工作文件
        conn.close()
        rebuild_working_file(file_id)

        return {"success": True, "file_id": file_id, "file_deleted": False}

    except Exception:
        conn.close()
        raise


# ========== 修改操作 ==========


def update_chunk_title(chunk_id: int, doc_title: str) -> Optional[Dict[str, Any]]:
    """
    修改 chunk 标题（同步操作，不需要重新生成 embedding）

    Returns:
        更新后的 chunk 信息，失败返回 None
    """
    conn = get_connection()
    try:
        # 检查 chunk 是否存在并获取 file_id
        existing = conn.execute(
            "SELECT id, file_id FROM chunks WHERE id = ?", (chunk_id,)
        ).fetchone()

        if not existing:
            return None

        file_id = existing["file_id"]

        # 更新标题（FTS5 触发器自动同步）
        conn.execute(
            "UPDATE chunks SET doc_title = ? WHERE id = ?",
            (doc_title, chunk_id)
        )
        conn.commit()

        # 重建工作文件
        conn.close()
        rebuild_working_file(file_id)

        # 返回更新后的 chunk
        return get_chunk_by_id(chunk_id)

    except Exception:
        conn.close()
        raise


def create_chunk_update_task(chunk_id: int, chunk_text: str) -> int:
    """
    创建 chunk 内容更新任务（异步，需要重新生成 embedding）

    Returns:
        task_id
    """
    # 获取 chunk 信息用于任务描述
    chunk = get_chunk_by_id(chunk_id)
    if not chunk:
        raise ValueError("Chunk 不存在")

    # 创建任务
    task_id = task_service.create_task(f"更新切片: {chunk['doc_title'][:20]}")

    # 存储待更新的数据到任务（通过 error_message 字段临时存储，或者扩展 tasks 表）
    # 这里简化处理：直接在内存中处理
    conn = get_connection()
    try:
        # 使用 error_message 字段临时存储 chunk_id 和新内容
        # 格式: "CHUNK_UPDATE|{chunk_id}|{chunk_text}"
        task_data = f"CHUNK_UPDATE|{chunk_id}|{chunk_text}"
        conn.execute(
            "UPDATE tasks SET error_message = ? WHERE id = ?",
            (task_data, task_id)
        )
        conn.commit()
    finally:
        conn.close()

    return task_id


async def process_chunk_update_task(task_id: int) -> None:
    """
    处理 chunk 内容更新任务

    流程:
    1. 解析任务数据
    2. 生成新的 embedding
    3. 更新 chunks 表
    4. 更新 vec_chunks 表
    """
    task = task_service.get_task(task_id)
    if not task or not task.get("error_message", "").startswith("CHUNK_UPDATE|"):
        task_service.update_task_status(task_id, "failed", error_message="无效的任务数据")
        return

    try:
        # 解析任务数据
        parts = task["error_message"].split("|", 2)
        chunk_id = int(parts[1])
        chunk_text = parts[2]

        task_service.update_task_status(task_id, "processing", progress=10)

        # 获取 embedding 配置
        config = get_embedding_config()
        if not config["api_key"]:
            task_service.update_task_status(task_id, "failed", error_message="未配置 API Key")
            return

        task_service.update_task_status(task_id, "processing", progress=30)

        # 请求速率许可
        rate_limiter = get_rate_limiter()
        await rate_limiter.acquire(1)

        # 生成新的 embedding
        embeddings_model = OpenAIEmbeddings(**config)
        embedding = await asyncio.to_thread(
            embeddings_model.embed_documents, [chunk_text]
        )
        embedding_blob = serialize_float32(embedding[0])

        task_service.update_task_status(task_id, "processing", progress=70)

        # 更新数据库
        conn = get_connection()
        try:
            # 获取 file_id
            file_id_row = conn.execute(
                "SELECT file_id FROM chunks WHERE id = ?", (chunk_id,)
            ).fetchone()

            if not file_id_row:
                raise Exception("Chunk 不存在")

            file_id = file_id_row["file_id"]

            # 更新 chunks 表（FTS5 触发器自动同步）
            conn.execute(
                "UPDATE chunks SET chunk_text = ?, embedding = ? WHERE id = ?",
                (chunk_text, embedding_blob, chunk_id)
            )

            # 更新 vec_chunks 表
            conn.execute(
                "UPDATE vec_chunks SET embedding = ? WHERE chunk_id = ?",
                (embedding_blob, chunk_id)
            )

            conn.commit()
        finally:
            conn.close()

        # 重建工作文件
        rebuild_working_file(file_id)

        # 完成任务，保存 chunk_id 到 error_message（用于返回给客户端）
        task_service.update_task_status(
            task_id, "completed", progress=100,
            error_message=f"CHUNK_ID:{chunk_id}"
        )

    except Exception as e:
        task_service.update_task_status(task_id, "failed", error_message=str(e))


# ========== 新增操作 ==========


def create_chunk_add_task(file_id: int, doc_title: str, chunk_text: str) -> int:
    """
    创建新增 chunk 任务（异步，需要生成 embedding）

    Returns:
        task_id
    """
    # 检查文件是否存在
    conn = get_connection()
    try:
        file_exists = conn.execute(
            "SELECT id FROM files WHERE id = ?", (file_id,)
        ).fetchone()

        if not file_exists:
            raise ValueError("文件不存在")
    finally:
        conn.close()

    # 创建任务
    task_id = task_service.create_task(f"新增切片: {doc_title[:20]}")

    # 存储待新增的数据
    conn = get_connection()
    try:
        task_data = f"CHUNK_ADD|{file_id}|{doc_title}|{chunk_text}"
        conn.execute(
            "UPDATE tasks SET error_message = ? WHERE id = ?",
            (task_data, task_id)
        )
        conn.commit()
    finally:
        conn.close()

    return task_id


async def process_chunk_add_task(task_id: int) -> None:
    """
    处理新增 chunk 任务

    流程:
    1. 解析任务数据
    2. 生成 embedding
    3. 插入 chunks 表
    4. 插入 vec_chunks 表
    5. 更新文件状态（如果是 empty → indexed）
    """
    task = task_service.get_task(task_id)
    if not task or not task.get("error_message", "").startswith("CHUNK_ADD|"):
        task_service.update_task_status(task_id, "failed", error_message="无效的任务数据")
        return

    try:
        # 解析任务数据
        parts = task["error_message"].split("|", 3)
        file_id = int(parts[1])
        doc_title = parts[2]
        chunk_text = parts[3]

        task_service.update_task_status(task_id, "processing", progress=10)

        # 获取 embedding 配置
        config = get_embedding_config()
        if not config["api_key"]:
            task_service.update_task_status(task_id, "failed", error_message="未配置 API Key")
            return

        task_service.update_task_status(task_id, "processing", progress=30)

        # 请求速率许可
        rate_limiter = get_rate_limiter()
        await rate_limiter.acquire(1)

        # 生成 embedding
        embeddings_model = OpenAIEmbeddings(**config)
        embedding = await asyncio.to_thread(
            embeddings_model.embed_documents, [chunk_text]
        )
        embedding_blob = serialize_float32(embedding[0])

        task_service.update_task_status(task_id, "processing", progress=70)

        # 插入数据库
        conn = get_connection()
        try:
            # 插入 chunks 表（FTS5 触发器自动同步）
            cursor = conn.execute(
                """
                INSERT INTO chunks (file_id, doc_title, chunk_text, embedding)
                VALUES (?, ?, ?, ?)
                """,
                (file_id, doc_title, chunk_text, embedding_blob)
            )
            chunk_id = cursor.lastrowid

            # 插入 vec_chunks 表
            conn.execute(
                "INSERT INTO vec_chunks (chunk_id, embedding) VALUES (?, ?)",
                (chunk_id, embedding_blob)
            )

            # 更新文件状态（如果是 empty → indexed）
            now = datetime.now().isoformat()
            conn.execute(
                "UPDATE files SET status = 'indexed', updated_at = ? WHERE id = ? AND status = 'empty'",
                (now, file_id)
            )

            conn.commit()
        finally:
            conn.close()

        # 重建工作文件
        rebuild_working_file(file_id)

        # 完成任务，保存 chunk_id 到 error_message（用于返回给客户端）
        task_service.update_task_status(
            task_id, "completed", progress=100,
            error_message=f"CHUNK_ID:{chunk_id}"
        )

    except Exception as e:
        task_service.update_task_status(task_id, "failed", error_message=str(e))
