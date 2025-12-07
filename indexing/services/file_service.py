"""
文件服务模块

职责:
- 文件存储（保存到 data/files/）
- 文件 CRUD 操作
- 文件名冲突处理
"""

import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

from ..database import get_connection
from ..settings import get_settings


def get_files_dir() -> Path:
    """获取文件存储目录"""
    settings = get_settings()
    return settings.get_files_path()


def ensure_files_dir() -> Path:
    """确保文件存储目录存在"""
    files_dir = get_files_dir()
    files_dir.mkdir(parents=True, exist_ok=True)
    return files_dir


def calculate_file_hash(content: bytes) -> str:
    """计算文件内容的 SHA256 哈希值"""
    return hashlib.sha256(content).hexdigest()


def get_unique_filename(original_filename: str) -> str:
    """
    获取唯一文件名，处理同名文件冲突

    Args:
        original_filename: 原始文件名

    Returns:
        唯一的文件名（如果冲突则添加后缀 _1, _2, ...）
    """
    files_dir = ensure_files_dir()

    file_path = files_dir / original_filename
    if not file_path.exists():
        return original_filename

    # 文件名冲突，添加后缀
    stem = file_path.stem
    suffix = file_path.suffix
    counter = 1

    while True:
        new_filename = f"{stem}_{counter}{suffix}"
        new_path = files_dir / new_filename
        if not new_path.exists():
            return new_filename
        counter += 1


async def save_file(filename: str, content: bytes) -> Dict[str, Any]:
    """
    保存文件到 data/files/ 目录

    Args:
        filename: 原始文件名
        content: 文件内容（bytes）

    Returns:
        {
            "filename": 实际保存的文件名,
            "file_path": 完整路径,
            "file_hash": 文件哈希,
            "file_size": 文件大小
        }
    """
    import aiofiles

    files_dir = ensure_files_dir()

    # 计算哈希
    file_hash = calculate_file_hash(content)

    # 获取唯一文件名
    unique_filename = get_unique_filename(filename)
    file_path = files_dir / unique_filename

    # 异步写入文件
    async with aiofiles.open(file_path, "wb") as f:
        await f.write(content)

    return {
        "filename": unique_filename,
        "file_path": str(file_path),
        "file_hash": file_hash,
        "file_size": len(content),
    }


def check_file_hash_exists(file_hash: str) -> Optional[int]:
    """
    检查文件哈希是否已存在

    Returns:
        存在则返回 file_id，否则返回 None
    """
    conn = get_connection()
    try:
        result = conn.execute(
            "SELECT id FROM files WHERE file_hash = ?", (file_hash,)
        ).fetchone()
        return result["id"] if result else None
    finally:
        conn.close()


def insert_file_record(
    file_hash: str,
    filename: str,
    file_path: str,
    file_size: int,
    status: str = "pending"
) -> int:
    """
    插入文件记录到 files 表

    Returns:
        新插入的 file_id
    """
    conn = get_connection()
    try:
        now = datetime.now().isoformat()
        cursor = conn.execute(
            """
            INSERT INTO files (file_hash, filename, file_path, file_size, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (file_hash, filename, file_path, file_size, status, now, now),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def update_file_status(file_id: int, status: str) -> None:
    """更新文件状态"""
    conn = get_connection()
    try:
        now = datetime.now().isoformat()
        conn.execute(
            "UPDATE files SET status = ?, updated_at = ? WHERE id = ?",
            (status, now, file_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_file_by_id(file_id: int) -> Optional[Dict[str, Any]]:
    """根据 ID 获取文件信息"""
    conn = get_connection()
    try:
        result = conn.execute(
            "SELECT * FROM files WHERE id = ?", (file_id,)
        ).fetchone()
        return dict(result) if result else None
    finally:
        conn.close()


def get_files_list(status: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    获取文件列表

    Args:
        status: 可选，按状态筛选 ('pending', 'indexed', 'error')

    Returns:
        文件列表
    """
    conn = get_connection()
    try:
        if status:
            rows = conn.execute(
                "SELECT * FROM files WHERE status = ? ORDER BY created_at DESC",
                (status,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM files ORDER BY created_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_chunks_by_file_id(file_id: int) -> Optional[List[Dict[str, Any]]]:
    """
    获取文件的所有切片

    Args:
        file_id: 文件 ID

    Returns:
        切片列表，如果文件不存在返回 None
    """
    conn = get_connection()
    try:
        # 先检查文件是否存在
        file_exists = conn.execute(
            "SELECT id FROM files WHERE id = ?", (file_id,)
        ).fetchone()

        if not file_exists:
            return None

        rows = conn.execute(
            "SELECT id, doc_title, chunk_text FROM chunks WHERE file_id = ? ORDER BY id",
            (file_id,)
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def delete_file(file_id: int) -> bool:
    """
    删除文件（数据库记录 + 物理文件）

    注意：由于外键级联删除，chunks 表中的相关记录会自动删除

    Returns:
        是否删除成功
    """
    conn = get_connection()
    try:
        # 获取文件路径
        result = conn.execute(
            "SELECT file_path FROM files WHERE id = ?", (file_id,)
        ).fetchone()

        if not result:
            return False

        file_path = Path(result["file_path"])

        # 删除 vec_chunks 中的相关记录（需要手动删除，因为没有外键关联）
        conn.execute(
            """
            DELETE FROM vec_chunks WHERE chunk_id IN (
                SELECT id FROM chunks WHERE file_id = ?
            )
            """,
            (file_id,)
        )

        # 删除数据库记录（chunks 会级联删除）
        conn.execute("DELETE FROM files WHERE id = ?", (file_id,))
        conn.commit()

        # 删除物理文件
        if file_path.exists():
            file_path.unlink()

        return True
    finally:
        conn.close()


def create_empty_file(filename: str) -> Dict[str, Any]:
    """
    创建空 MD 文件

    Args:
        filename: 文件名（如不带后缀会自动补充 .md）

    Returns:
        {
            "file_id": 新文件 ID,
            "filename": 实际文件名,
            "file_path": 文件路径
        }

    Raises:
        ValueError: 文件名为空或已存在同名文件
    """
    # 处理文件名
    filename = filename.strip()
    if not filename:
        raise ValueError("文件名不能为空")

    # 自动补充 .md 后缀
    if not filename.lower().endswith(".md"):
        filename = filename + ".md"

    files_dir = ensure_files_dir()

    # 获取唯一文件名
    unique_filename = get_unique_filename(filename)
    file_path = files_dir / unique_filename

    # 创建空文件
    file_path.touch()

    # 计算空文件 hash（空内容的 SHA256）
    file_hash = calculate_file_hash(b"")

    # 检查是否已存在空文件记录（理论上每次 hash 都相同，但允许多个空文件）
    # 这里用文件名+时间戳生成唯一 hash
    import time
    unique_hash = calculate_file_hash(f"{unique_filename}_{time.time()}".encode())

    # 插入数据库记录
    file_id = insert_file_record(
        file_hash=unique_hash,
        filename=unique_filename,
        file_path=str(file_path),
        file_size=0,
        status="empty"
    )

    return {
        "file_id": file_id,
        "filename": unique_filename,
        "file_path": str(file_path),
    }


def scan_untracked_files() -> List[Dict[str, Any]]:
    """
    扫描物理文件目录，找出未被数据库记录的文件

    用于云同步后发现新下载的文件

    Returns:
        未跟踪文件列表，每项包含 filename, file_path, file_size
    """
    files_dir = get_files_dir()
    if not files_dir.exists():
        return []

    # 获取数据库中所有文件名
    conn = get_connection()
    try:
        rows = conn.execute("SELECT filename FROM files").fetchall()
        tracked_filenames = {row["filename"] for row in rows}
    finally:
        conn.close()

    # 扫描物理目录
    untracked = []
    for file_path in files_dir.iterdir():
        if not file_path.is_file():
            continue

        # 只处理支持的格式
        if not (file_path.suffix.lower() in [".md", ".pdf"]):
            continue

        if file_path.name not in tracked_filenames:
            untracked.append({
                "filename": file_path.name,
                "file_path": str(file_path),
                "file_size": file_path.stat().st_size,
            })

    return untracked


def get_storage_stats() -> Dict[str, Any]:
    """
    获取存储统计信息

    Returns:
        {
            "total_files": 文件总数,
            "indexed_files": 已索引文件数,
            "total_chunks": 切片总数,
            "total_size": 总存储大小（字节）
        }
    """
    conn = get_connection()
    try:
        # 文件统计
        file_stats = conn.execute("""
            SELECT
                COUNT(*) as total_files,
                SUM(CASE WHEN status = 'indexed' THEN 1 ELSE 0 END) as indexed_files,
                COALESCE(SUM(file_size), 0) as total_size
            FROM files
        """).fetchone()

        # 切片统计
        chunk_count = conn.execute(
            "SELECT COUNT(*) as total_chunks FROM chunks"
        ).fetchone()

        return {
            "total_files": file_stats["total_files"] or 0,
            "indexed_files": file_stats["indexed_files"] or 0,
            "total_chunks": chunk_count["total_chunks"] or 0,
            "total_size": file_stats["total_size"] or 0,
        }
    finally:
        conn.close()
