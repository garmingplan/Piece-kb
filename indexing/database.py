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
import threading
from pathlib import Path
from contextlib import contextmanager
from queue import Queue, Empty

from .settings import get_settings, get_vector_dim

logger = logging.getLogger(__name__)

# 全局连接池（线程安全）
_connection_pool = None
_pool_lock = threading.Lock()
_pool_size = 10  # 连接池大小


class ConnectionPool:
    """
    SQLite 连接池实现

    特性:
    - 支持多个连接并发使用
    - 自动回收和复用连接
    - 线程安全
    """

    def __init__(self, db_path: Path, pool_size: int = 5):
        """
        初始化连接池

        Args:
            db_path: 数据库文件路径
            pool_size: 连接池大小
        """
        self.db_path = db_path
        self.pool_size = pool_size
        self._pool = Queue(maxsize=pool_size)
        self._all_connections = []
        self._lock = threading.Lock()

        # 预创建连接
        for _ in range(pool_size):
            conn = self._create_connection()
            self._pool.put(conn)
            self._all_connections.append(conn)

        logger.info(f"[DB Pool] 连接池初始化成功，大小: {pool_size}")

    def _create_connection(self) -> sqlite3.Connection:
        """创建新的数据库连接"""
        conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
            timeout=30.0
        )
        conn.row_factory = sqlite3.Row

        # 启用 WAL 模式
        conn.execute("PRAGMA journal_mode=WAL")

        # 启用外键约束
        conn.execute("PRAGMA foreign_keys=ON")

        # 性能优化
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-64000")  # 64MB 缓存
        conn.execute("PRAGMA temp_store=MEMORY")

        # 加载 sqlite-vec 扩展
        _load_sqlite_vec(conn)

        return conn

    def get_connection(self, timeout: float = 5.0) -> sqlite3.Connection:
        """
        从连接池获取连接

        Args:
            timeout: 超时时间（秒）

        Returns:
            数据库连接

        Raises:
            Empty: 连接池为空且超时
        """
        try:
            return self._pool.get(timeout=timeout)
        except Empty:
            raise RuntimeError("连接池已耗尽，无法获取连接")

    def return_connection(self, conn: sqlite3.Connection) -> None:
        """
        归还连接到连接池

        Args:
            conn: 数据库连接
        """
        self._pool.put(conn)

    def close_all(self) -> None:
        """关闭所有连接"""
        with self._lock:
            for conn in self._all_connections:
                try:
                    conn.close()
                except Exception as e:
                    logger.error(f"[DB Pool] 关闭连接失败: {e}")
            self._all_connections.clear()

            # 清空队列
            while not self._pool.empty():
                try:
                    self._pool.get_nowait()
                except Empty:
                    break

        logger.info("[DB Pool] 所有连接已关闭")


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


def init_connection_pool(db_path: Path = None) -> None:
    """
    初始化数据库连接池（应用启动时调用一次）

    使用真正的连接池（多个连接），支持并发访问

    Args:
        db_path: 数据库文件路径，默认使用配置路径
    """
    global _connection_pool

    with _pool_lock:
        if _connection_pool is not None:
            logger.warning("[DB Pool] 连接池已存在，跳过初始化")
            return

        if db_path is None:
            db_path = get_db_path()

        # 确保 data 目录存在
        db_path.parent.mkdir(parents=True, exist_ok=True)

        # 创建连接池
        _connection_pool = ConnectionPool(db_path, pool_size=_pool_size)

        logger.info(f"[DB Pool] 连接池初始化成功: {db_path}")


def close_connection_pool() -> None:
    """关闭数据库连接池（应用关闭时调用）"""
    global _connection_pool

    with _pool_lock:
        if _connection_pool is not None:
            _connection_pool.close_all()
            _connection_pool = None
            logger.info("[DB Pool] 连接池已关闭")


@contextmanager
def get_db_cursor():
    """
    获取数据库游标（上下文管理器，推荐使用）

    使用方式:
        with get_db_cursor() as cursor:
            cursor.execute("SELECT * FROM files")
            rows = cursor.fetchall()

    特性:
    - 自动提交/回滚事务
    - 线程安全（使用连接池）
    - 自动归还连接

    Yields:
        sqlite3.Cursor: 数据库游标
    """
    global _connection_pool

    # 如果连接池未初始化，先初始化
    if _connection_pool is None:
        init_connection_pool()

    # 从连接池获取连接
    conn = _connection_pool.get_connection()
    cursor = conn.cursor()

    try:
        yield cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        # 归还连接到连接池
        _connection_pool.return_connection(conn)


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

    # 确保 data 目录存在
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # 创建临时连接（仅用于初始化）
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    try:
        # 启用 WAL 模式
        conn.execute("PRAGMA journal_mode=WAL")

        # 启用外键约束
        conn.execute("PRAGMA foreign_keys=ON")

        # 加载 sqlite-vec 扩展
        _load_sqlite_vec(conn)
        # 1. 创建 files 表（母表：文件物理元数据）
        # 主表记录工作文件（working/），新增字段记录原始文件（originals/）
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_hash TEXT UNIQUE NOT NULL,
                filename TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_size INTEGER,
                original_file_type TEXT,
                original_file_path TEXT,
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
    获取数据库信息（使用连接池）

    Returns:
        dict: 包含版本信息和表统计的字典
    """
    if db_path is None:
        db_path = get_db_path()

    with get_db_cursor() as cursor:
        sqlite_version = cursor.execute("SELECT sqlite_version()").fetchone()[0]
        vec_version = cursor.execute("SELECT vec_version()").fetchone()[0]

        # 检查表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        table_names = [t[0] for t in tables]

        file_count = 0
        chunk_count = 0
        vec_count = 0

        if "files" in table_names:
            cursor.execute("SELECT COUNT(*) FROM files")
            file_count = cursor.fetchone()[0]

        if "chunks" in table_names:
            cursor.execute("SELECT COUNT(*) FROM chunks")
            chunk_count = cursor.fetchone()[0]

        if "vec_chunks" in table_names:
            cursor.execute("SELECT COUNT(*) FROM vec_chunks")
            vec_count = cursor.fetchone()[0]

        return {
            "sqlite_version": sqlite_version,
            "vec_version": vec_version,
            "db_path": str(db_path),
            "file_count": file_count,
            "chunk_count": chunk_count,
            "vec_count": vec_count,
            "tables": table_names,
        }


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
