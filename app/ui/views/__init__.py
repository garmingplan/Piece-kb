"""
Views 包初始化

提供页面视图渲染函数
"""

from app.ui.views.sidebar import render_sidebar
from app.ui.views.files_view import render_files_middle, render_files_right
from app.ui.views.settings_view import render_settings_middle, render_settings_right
from app.ui.views.mcp_config_view import render_mcp_config_middle, render_mcp_config_right
from app.ui.views.cloud_sync_view import render_cloud_sync_middle, render_cloud_sync_right
from app.ui.views.logs_view import render_logs_middle, render_logs_right

__all__ = [
    "render_sidebar",
    "render_files_middle",
    "render_files_right",
    "render_settings_middle",
    "render_settings_right",
    "render_mcp_config_middle",
    "render_mcp_config_right",
    "render_cloud_sync_middle",
    "render_cloud_sync_right",
    "render_logs_middle",
    "render_logs_right",
]
