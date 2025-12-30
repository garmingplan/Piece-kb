"""
数据库连接模块：为 retrieval 模块提供统一的数据库连接池
"""

import sqlite3
import sqlite_vec
import threading
from contextlib import contextmanager

from .config import get_db_path

# 全局连接池（线程安全）- retrieval 专用
_retrieval_connection_pool = None
_retrieval_pool_lock = threading.Lock()


def init_retrieval_connection_pool() -> None:
    """
    初始化 retrieval 模块的数据库连接池

    注意：retrieval 是只读查询模块，使用独立连接池
    """
    global _retrieval_connection_pool

    with _retrieval_pool_lock:
        if _retrieval_connection_pool is not None:
            return

        db_path = get_db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)

        # 创建长连接（只读优化）
        _retrieval_connection_pool = sqlite3.connect(
            str(db_path),
            check_same_thread=False,
            timeout=30.0
        )
        _retrieval_connection_pool.row_factory = sqlite3.Row

        # 启用 WAL 模式（支持并发读）
        _retrieval_connection_pool.execute("PRAGMA journal_mode=WAL")

        # 启用外键约束
        _retrieval_connection_pool.execute("PRAGMA foreign_keys=ON")

        # 只读优化
        _retrieval_connection_pool.execute("PRAGMA query_only=ON")  # 只读模式
        _retrieval_connection_pool.execute("PRAGMA cache_size=-64000")  # 64MB 缓存

        # 加载 sqlite-vec 扩展
        _retrieval_connection_pool.enable_load_extension(True)
        sqlite_vec.load(_retrieval_connection_pool)
        _retrieval_connection_pool.enable_load_extension(False)


def close_retrieval_connection_pool() -> None:
    """关闭 retrieval 连接池"""
    global _retrieval_connection_pool

    with _retrieval_pool_lock:
        if _retrieval_connection_pool is not None:
            _retrieval_connection_pool.close()
            _retrieval_connection_pool = None


@contextmanager
def get_db_cursor():
    """
    获取数据库游标（retrieval 专用，只读）

    使用方式:
        with get_db_cursor() as cursor:
            cursor.execute("SELECT * FROM chunks")
            rows = cursor.fetchall()

    Yields:
        sqlite3.Cursor: 数据库游标
    """
    global _retrieval_connection_pool

    # 如果连接池未初始化，先初始化
    if _retrieval_connection_pool is None:
        init_retrieval_connection_pool()

    with _retrieval_pool_lock:
        cursor = _retrieval_connection_pool.cursor()
        try:
            yield cursor
            # 只读操作，无需 commit
        finally:
            cursor.close()

