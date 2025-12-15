"""
API 路由模块
"""

from app.api.routes import register_routes
from app.api.chunk_routes import register_chunk_routes

__all__ = ["register_routes", "register_chunk_routes"]
