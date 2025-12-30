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

from ..database import get_db_cursor
from ..settings import get_settings


def get_files_dir() -> Path:
    """获取文件存储根目录"""
    settings = get_settings()
    return settings.get_files_path()


def get_originals_dir() -> Path:
    """获取原始文件存储目录"""
    return get_files_dir() / "originals"


def get_working_dir() -> Path:
    """获取工作文件存储目录"""
    return get_files_dir() / "working"


def ensure_files_dir() -> Path:
    """确保文件存储目录存在（包括子目录）"""
    files_dir = get_files_dir()
    files_dir.mkdir(parents=True, exist_ok=True)

    # 确保 originals 和 working 子目录存在
    get_originals_dir().mkdir(parents=True, exist_ok=True)
    get_working_dir().mkdir(parents=True, exist_ok=True)

    return files_dir


def calculate_file_hash(content: bytes) -> str:
    """计算文件内容的 SHA256 哈希值"""
    return hashlib.sha256(content).hexdigest()


def get_unique_filename(original_filename: str, check_in_working: bool = True) -> str:
    """
    获取唯一文件名，处理同名文件冲突

    Args:
        original_filename: 原始文件名
        check_in_working: 是否在 working 目录中检查（默认 True）

    Returns:
        唯一的文件名（如果冲突则添加后缀 _1, _2, ...）
    """
    ensure_files_dir()

    # 根据参数选择检查目录
    check_dir = get_working_dir() if check_in_working else get_originals_dir()

    file_path = check_dir / original_filename
    if not file_path.exists():
        return original_filename

    # 文件名冲突，添加后缀
    stem = file_path.stem
    suffix = file_path.suffix
    counter = 1

    while True:
        new_filename = f"{stem}_{counter}{suffix}"
        new_path = check_dir / new_filename
        if not new_path.exists():
            return new_filename
        counter += 1


async def save_file(filename: str, content: bytes) -> Dict[str, Any]:
    """
    保存文件（原始文件 + 工作文件分离）

    流程：
    1. 保存原始文件到 originals/ 目录
    2. 创建工作文件到 working/ 目录（初始为空，后续由processor转换填充）

    Args:
        filename: 原始文件名
        content: 文件内容（bytes）

    Returns:
        {
            "filename": 工作文件名（.md格式）,
            "file_path": 工作文件完整路径,
            "file_hash": 原始文件哈希,
            "file_size": 原始文件大小,
            "original_file_type": 原始文件类型（md/pdf）,
            "original_file_path": 原始文件路径
        }
    """
    import aiofiles
    import logging

    logger = logging.getLogger(__name__)

    ensure_files_dir()

    # 计算原始文件哈希
    file_hash = calculate_file_hash(content)

    # 获取原始文件类型
    file_suffix = Path(filename).suffix.lower()
    original_file_type = file_suffix.lstrip(".")  # 去掉点号，如 "pdf", "md"

    # 1. 保存原始文件到 originals/
    original_unique_filename = get_unique_filename(filename, check_in_working=False)
    original_file_path = get_originals_dir() / original_unique_filename

    async with aiofiles.open(original_file_path, "wb") as f:
        await f.write(content)

    logger.info(f"[save_file] 原始文件已保存: {original_file_path}")

    # 2. 生成工作文件名（统一为 .md 格式）
    working_filename_stem = Path(original_unique_filename).stem
    working_filename = f"{working_filename_stem}.md"

    # 检查 working 目录中的文件名冲突
    working_unique_filename = get_unique_filename(working_filename, check_in_working=True)
    working_file_path = get_working_dir() / working_unique_filename

    # 创建空的工作文件（内容由 processor 转换后填充）
    async with aiofiles.open(working_file_path, "wb") as f:
        await f.write(b"")

    logger.info(f"[save_file] 工作文件已创建: {working_file_path}")

    result = {
        "filename": working_unique_filename,
        "file_path": str(working_file_path),
        "file_hash": file_hash,
        "file_size": len(content),
        "original_file_type": original_file_type,
        "original_file_path": str(original_file_path),
    }

    logger.info(f"[save_file] 返回结果: {result}")

    return result


def check_file_hash_exists(file_hash: str) -> Optional[int]:
    """
    检查文件哈希是否已存在（使用连接池）

    Returns:
        存在则返回 file_id，否则返回 None
    """
    with get_db_cursor() as cursor:
        cursor.execute("SELECT id FROM files WHERE file_hash = ?", (file_hash,))
        result = cursor.fetchone()
        return result["id"] if result else None


def insert_file_record(
    file_hash: str,
    filename: str,
    file_path: str,
    file_size: int,
    status: str = "pending",
    original_file_type: Optional[str] = None,
    original_file_path: Optional[str] = None
) -> int:
    """
    插入文件记录到 files 表

    Args:
        file_hash: 文件哈希
        filename: 工作文件名
        file_path: 工作文件路径
        file_size: 原始文件大小
        status: 文件状态
        original_file_type: 原始文件类型（md/pdf）
        original_file_path: 原始文件路径

    Returns:
        新插入的 file_id
    """
    import logging
    logger = logging.getLogger(__name__)

    logger.info(f"[insert_file_record] 准备写入: filename={filename}, original_file_type={original_file_type}, original_file_path={original_file_path}")

    with get_db_cursor() as cursor:
        now = datetime.now().isoformat()
        cursor.execute(
            """
            INSERT INTO files (
                file_hash, filename, file_path, file_size,
                original_file_type, original_file_path,
                status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (file_hash, filename, file_path, file_size,
             original_file_type, original_file_path,
             status, now, now),
        )
        file_id = cursor.lastrowid

        logger.info(f"[insert_file_record] 写入成功: file_id={file_id}")

        return file_id


def update_file_status(file_id: int, status: str) -> None:
    """更新文件状态（使用连接池）"""
    with get_db_cursor() as cursor:
        now = datetime.now().isoformat()
        cursor.execute(
            "UPDATE files SET status = ?, updated_at = ? WHERE id = ?",
            (status, now, file_id),
        )


def get_file_by_id(file_id: int) -> Optional[Dict[str, Any]]:
    """根据 ID 获取文件信息（使用连接池）"""
    with get_db_cursor() as cursor:
        cursor.execute("SELECT * FROM files WHERE id = ?", (file_id,))
        result = cursor.fetchone()
        return dict(result) if result else None


def get_files_list(status: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    获取文件列表（使用连接池优化）

    Args:
        status: 可选，按状态筛选 ('pending', 'indexed', 'error')

    Returns:
        文件列表
    """
    with get_db_cursor() as cursor:
        if status:
            cursor.execute(
                "SELECT * FROM files WHERE status = ? ORDER BY created_at DESC",
                (status,)
            )
        else:
            cursor.execute("SELECT * FROM files ORDER BY created_at DESC")
        return [dict(row) for row in cursor.fetchall()]


def get_chunks_by_file_id(file_id: int) -> Optional[List[Dict[str, Any]]]:
    """
    获取文件的所有切片（使用连接池优化）

    Args:
        file_id: 文件 ID

    Returns:
        切片列表，如果文件不存在返回 None
    """
    with get_db_cursor() as cursor:
        # 先检查文件是否存在
        cursor.execute("SELECT id FROM files WHERE id = ?", (file_id,))
        if not cursor.fetchone():
            return None

        cursor.execute(
            "SELECT id, doc_title, chunk_text FROM chunks WHERE file_id = ? ORDER BY id",
            (file_id,)
        )
        return [dict(row) for row in cursor.fetchall()]


def delete_file(file_id: int) -> bool:
    """
    删除文件（数据库记录 + 物理文件，使用连接池优化）

    同时删除：
    1. 工作文件（working/）
    2. 原始文件（originals/）
    3. 数据库记录（外键级联删除 chunks）

    Returns:
        是否删除成功
    """
    with get_db_cursor() as cursor:
        # 获取文件路径信息
        cursor.execute(
            "SELECT file_path, original_file_path FROM files WHERE id = ?", (file_id,)
        )
        result = cursor.fetchone()

        if not result:
            return False

        working_file_path = Path(result["file_path"])
        original_file_path = Path(result["original_file_path"]) if result["original_file_path"] else None

        # 删除 vec_chunks 中的相关记录（需要手动删除，因为没有外键关联）
        cursor.execute(
            """
            DELETE FROM vec_chunks WHERE chunk_id IN (
                SELECT id FROM chunks WHERE file_id = ?
            )
            """,
            (file_id,)
        )

        # 删除数据库记录（chunks 会级联删除）
        cursor.execute("DELETE FROM files WHERE id = ?", (file_id,))

    # 删除工作文件
    if working_file_path.exists():
        working_file_path.unlink()

    # 删除原始文件
    if original_file_path and original_file_path.exists():
        original_file_path.unlink()

    return True


def create_empty_file(filename: str) -> Dict[str, Any]:
    """
    创建空 MD 文件（仅工作文件，无原始文件备份）

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

    ensure_files_dir()

    # 获取唯一文件名（在 working 目录中检查）
    unique_filename = get_unique_filename(filename, check_in_working=True)
    working_file_path = get_working_dir() / unique_filename

    # 创建空文件
    working_file_path.touch()

    # 用文件名+时间戳生成唯一 hash（避免多个空文件哈希冲突）
    import time
    unique_hash = calculate_file_hash(f"{unique_filename}_{time.time()}".encode())

    # 插入数据库记录（无原始文件）
    file_id = insert_file_record(
        file_hash=unique_hash,
        filename=unique_filename,
        file_path=str(working_file_path),
        file_size=0,
        original_file_type=None,  # 应用内新建，无原始文件
        original_file_path=None,
        status="empty"
    )

    return {
        "file_id": file_id,
        "filename": unique_filename,
        "file_path": str(working_file_path),
    }


def scan_untracked_files() -> List[Dict[str, Any]]:
    """
    扫描原始文件目录（originals/），找出未被数据库记录的文件

    用于云同步后发现新下载的原始文件，并关联/创建对应的工作文件

    Returns:
        未跟踪文件列表，每项包含:
        - original_filename: 原始文件名
        - original_file_path: 原始文件完整路径
        - original_file_type: 原始文件类型（不带点号，如 "pdf"）
        - original_file_size: 原始文件大小
        - working_filename: 工作文件名（.md格式）
        - working_file_path: 工作文件完整路径
    """
    originals_dir = get_originals_dir()
    working_dir = get_working_dir()

    if not originals_dir.exists():
        return []

    # 确保 working 目录存在
    working_dir.mkdir(parents=True, exist_ok=True)

    # 获取数据库中所有已跟踪的原始文件路径（使用连接池）
    with get_db_cursor() as cursor:
        cursor.execute("SELECT original_file_path FROM files WHERE original_file_path IS NOT NULL")
        rows = cursor.fetchall()
        tracked_originals = {row["original_file_path"] for row in rows}

    # 扫描 originals 目录
    untracked = []
    supported_exts = [".md", ".pdf", ".pptx", ".xlsx", ".docx", ".txt"]

    for original_file in originals_dir.iterdir():
        if not original_file.is_file():
            continue

        # 检查文件扩展名
        file_ext = original_file.suffix.lower()
        if file_ext not in supported_exts:
            continue

        # 如果原始文件未被跟踪
        if str(original_file) not in tracked_originals:
            # 生成对应的工作文件路径
            working_filename = f"{original_file.stem}.md"
            working_file_path = working_dir / working_filename

            untracked.append({
                "original_filename": original_file.name,
                "original_file_path": str(original_file),
                "original_file_type": file_ext.lstrip("."),  # 去掉点号
                "original_file_size": original_file.stat().st_size,
                "working_filename": working_filename,
                "working_file_path": str(working_file_path),
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
    with get_db_cursor() as cursor:
        # 文件统计
        cursor.execute("""
            SELECT
                COUNT(*) as total_files,
                SUM(CASE WHEN status = 'indexed' THEN 1 ELSE 0 END) as indexed_files,
                COALESCE(SUM(file_size), 0) as total_size
            FROM files
        """)
        file_stats = cursor.fetchone()

        # 切片统计
        cursor.execute("SELECT COUNT(*) as total_chunks FROM chunks")
        chunk_count = cursor.fetchone()

        return {
            "total_files": file_stats["total_files"] or 0,
            "indexed_files": file_stats["indexed_files"] or 0,
            "total_chunks": chunk_count["total_chunks"] or 0,
            "total_size": file_stats["total_size"] or 0,
        }
