"""
日志 API 路由

职责:
- 提供日志查询接口
- 提供日志清空接口
"""

from typing import Optional
from nicegui import app as nicegui_app
from app.logging_config import get_log_buffer, clear_log_buffer
from app.api.models import ApiResponse


def register_log_routes(app: nicegui_app):
    """注册日志 API 路由"""

    @app.get("/api/logs")
    def get_logs(level: Optional[str] = None, limit: int = 500) -> ApiResponse:
        """
        获取日志列表

        Query参数:
            level: 日志级别过滤（可选，如 'ERROR', 'WARNING', 'INFO', 'DEBUG'）
            limit: 返回的最大日志数量（默认 500）

        Returns:
            ApiResponse: 包含日志列表的响应
        """
        try:
            logs = get_log_buffer(level=level, limit=limit)
            return ApiResponse(
                success=True,
                data={
                    "logs": logs,
                    "total": len(logs),
                    "level_filter": level,
                },
                message="日志获取成功",
            )
        except Exception as e:
            return ApiResponse(success=False, message=f"获取日志失败: {e}")

    @app.post("/api/logs/clear")
    def clear_logs() -> ApiResponse:
        """
        清空日志缓冲区

        Returns:
            ApiResponse: 清空结果
        """
        try:
            clear_log_buffer()
            return ApiResponse(success=True, message="日志已清空")
        except Exception as e:
            return ApiResponse(success=False, message=f"清空日志失败: {e}")
