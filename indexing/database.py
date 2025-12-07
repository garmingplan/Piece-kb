"""
SQLite 数据库初始化和管理模块

职责:
- 数据库创建和初始化（表结构、FTS5、vec0）
- 数据写入操作
- 数据库维护（清理、重建索引等）

表结构设计（3 张普通表 + 2 张虚拟表）:
- files 表: 文件物理元数据（母表，去重、状态追踪）
- chunks 表: 检索单元（子表，外键关联 files）
- tasks 表: 异步任务队列
- chunks_fts 虚拟表: FTS5 全文检索索引（通过触发器自动同步）
- vec_chunks 虚拟表: sqlite-vec 向量检索索引（需手动同步）
"""

import os
import sys
import sqlite3
import logging
from pathlib import Path

from .settings import get_settings, get_vector_dim

logger = logging.getLogger(__name__)


def _get_sqlite_vec_path() -> str:
    """
    获取 sqlite-vec 扩展的路径

    在 PyInstaller 打包环境下，需要特殊处理路径
    """
    # 检查是否在 PyInstaller 打包环境中
    if getattr(sys, 'frozen', False):
        # 打包环境：从 _internal/sqlite_vec 目录加载
        base_path = Path(sys._MEIPASS)
        vec_path = base_path / "sqlite_vec" / "vec0"
    else:
        # 开发环境：使用 sqlite_vec 模块的默认路径
        import sqlite_vec
        vec_path = Path(sqlite_vec.__file__).parent / "vec0"

    return str(vec_path.resolve())


def _load_sqlite_vec(conn: sqlite3.Connection) -> None:
    """
    加载 sqlite-vec 扩展

    Args:
        conn: 数据库连接
    """
    conn.enable_load_extension(True)
    try:
        vec_path = _get_sqlite_vec_path()
        conn.load_extension(vec_path)
    finally:
        conn.enable_load_extension(False)


def get_db_path() -> Path:
    """获取数据库路径"""
    settings = get_settings()
    return settings.get_db_path()


def get_connection(db_path: Path = None) -> sqlite3.Connection:
    """
    获取数据库连接，自动加载 sqlite-vec 扩展

    Args:
        db_path: 数据库文件路径，默认使用配置路径

    Returns:
        sqlite3.Connection: 已加载扩展的数据库连接
    """
    if db_path is None:
        db_path = get_db_path()

    # 确保 data 目录存在
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # 创建连接
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # 启用 WAL 模式
    conn.execute("PRAGMA journal_mode=WAL")

    # 启用外键约束
    conn.execute("PRAGMA foreign_keys=ON")

    # 加载 sqlite-vec 扩展
    _load_sqlite_vec(conn)

    return conn


def init_database(db_path: Path = None) -> None:
    """
    初始化数据库：创建表结构、FTS5 虚拟表、vec0 虚拟表

    表结构：
    - files: 文件物理元数据（母表）
    - chunks: 检索单元（子表，外键关联 files）

    Args:
        db_path: 数据库文件路径，默认使用配置路径
    """
    if db_path is None:
        db_path = get_db_path()

    conn = get_connection(db_path)

    try:
        # 1. 创建 files 表（母表：文件物理元数据）
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_hash TEXT UNIQUE NOT NULL,
                filename TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_size INTEGER,
                status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'indexed', 'error', 'empty')),
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # 2. 创建 files 表索引
        conn.execute("CREATE INDEX IF NOT EXISTS idx_file_hash ON files(file_hash)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_file_status ON files(status)")

        # 3. 创建 chunks 表（子表：检索单元）
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER NOT NULL,
                doc_title TEXT NOT NULL,
                chunk_text TEXT NOT NULL,
                embedding BLOB,
                FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
            )
        """
        )

        # 4. 创建 chunks 表索引
        conn.execute("CREATE INDEX IF NOT EXISTS idx_doc_title ON chunks(doc_title)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_file_id ON chunks(file_id)")

        # 5. 创建 FTS5 虚拟表（全文检索 chunk_text 和 doc_title）
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts
            USING fts5(
                chunk_text,
                doc_title,
                content='chunks',
                content_rowid='id',
                tokenize='unicode61'
            )
        """
        )

        # 6. 创建触发器：chunks 表插入时同步到 FTS5
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS chunks_ai
            AFTER INSERT ON chunks BEGIN
                INSERT INTO chunks_fts(rowid, chunk_text, doc_title)
                VALUES (new.id, new.chunk_text, new.doc_title);
            END
        """
        )

        # 7. 创建触发器：chunks 表删除时同步到 FTS5
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS chunks_ad
            AFTER DELETE ON chunks BEGIN
                INSERT INTO chunks_fts(chunks_fts, rowid, chunk_text, doc_title)
                VALUES ('delete', old.id, old.chunk_text, old.doc_title);
            END
        """
        )

        # 8. 创建触发器：chunks 表更新时同步到 FTS5
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS chunks_au
            AFTER UPDATE ON chunks BEGIN
                INSERT INTO chunks_fts(chunks_fts, rowid, chunk_text, doc_title)
                VALUES ('delete', old.id, old.chunk_text, old.doc_title);
                INSERT INTO chunks_fts(rowid, chunk_text, doc_title)
                VALUES (new.id, new.chunk_text, new.doc_title);
            END
        """
        )

        # 9. 创建 vec0 虚拟表（向量检索）
        vector_dim = get_vector_dim()
        conn.execute(
            f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0(
                chunk_id INTEGER PRIMARY KEY,
                embedding float[{vector_dim}]
            )
        """
        )

        # 10. 创建 tasks 表（异步任务队列）
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER,
                original_filename TEXT NOT NULL,
                status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'processing', 'completed', 'failed')),
                progress INTEGER DEFAULT 0,
                error_message TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE SET NULL
            )
        """
        )

        # 11. 创建 tasks 表索引
        conn.execute("CREATE INDEX IF NOT EXISTS idx_task_status ON tasks(status)")

        conn.commit()
        logger.info(f"[DB] 数据库初始化完成: {db_path}")

    finally:
        conn.close()


def get_db_info(db_path: Path = None) -> dict:
    """
    获取数据库信息

    Returns:
        dict: 包含版本信息和表统计的字典
    """
    if db_path is None:
        db_path = get_db_path()

    conn = get_connection(db_path)

    try:
        sqlite_version = conn.execute("SELECT sqlite_version()").fetchone()[0]
        vec_version = conn.execute("SELECT vec_version()").fetchone()[0]

        # 检查表是否存在
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = [t[0] for t in tables]

        file_count = 0
        chunk_count = 0
        vec_count = 0

        if "files" in table_names:
            file_count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]

        if "chunks" in table_names:
            chunk_count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]

        if "vec_chunks" in table_names:
            vec_count = conn.execute("SELECT COUNT(*) FROM vec_chunks").fetchone()[0]

        return {
            "sqlite_version": sqlite_version,
            "vec_version": vec_version,
            "db_path": str(db_path),
            "file_count": file_count,
            "chunk_count": chunk_count,
            "vec_count": vec_count,
            "tables": table_names,
        }

    finally:
        conn.close()


if __name__ == "__main__":
    # 直接运行时初始化数据库
    logger.info("=" * 50)
    logger.info("SQLite 数据库初始化")
    logger.info("=" * 50)

    init_database()

    # 打印数据库信息
    info = get_db_info()
    logger.info(f"\nSQLite 版本: {info['sqlite_version']}")
    logger.info(f"sqlite-vec 版本: {info['vec_version']}")
    logger.info(f"数据库路径: {info['db_path']}")
    logger.info(f"表列表: {info['tables']}")
    logger.info(f"文件数: {info['file_count']}")
    logger.info(f"分块数: {info['chunk_count']}")
    logger.info(f"向量记录数: {info['vec_count']}")
