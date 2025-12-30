"""
Indexing 模块 - 文件索引服务

职责:
- 数据库管理
- 文件存储和 CRUD
- 文档分块处理
- 向量生成和入库
- 异步任务管理

注意: 前端 UI 和 API 路由已迁移至 app/ 模块
"""

from .database import (
    init_database,
    get_db_info,
    init_connection_pool,
    close_connection_pool,
    get_db_cursor,
)

__all__ = [
    "init_database",
    "get_db_info",
    "init_connection_pool",
    "close_connection_pool",
    "get_db_cursor",
]
