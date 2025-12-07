"""
数据库连接模块：为 retrieval 模块提供统一的数据库连接
"""

import sqlite3
import sqlite_vec

from .config import get_db_path


def get_connection() -> sqlite3.Connection:
    """
    获取数据库连接，自动加载 sqlite-vec 扩展

    Returns:
        sqlite3.Connection: 已加载扩展的数据库连接
    """
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
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)

    return conn
