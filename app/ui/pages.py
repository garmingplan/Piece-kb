"""
页面定义模块

职责:
- 定义所有 NiceGUI 页面路由
- 三栏式主从视图布局（支持文件库/设置视图切换）
"""

from nicegui import ui

from indexing.settings import get_settings
from app.ui.styles import inject_theme_css, init_theme, apply_theme
from app.ui.handlers import FileHandlers, ChunkHandlers, TaskHandlers, SettingsHandlers, SyncHandlers
from app.ui.views import (
    render_sidebar,
    render_files_middle,
    render_files_right,
    render_settings_middle,
    render_settings_right,
    render_mcp_config_middle,
    render_mcp_config_right,
    render_cloud_sync_middle,
    render_cloud_sync_right,
    render_logs_middle,
    render_logs_right,
)


def register_pages():
    """注册所有页面路由"""

    @ui.page("/")
    def main_page():
        """主页面 - 三栏式文件管理界面"""

        # ========== 状态管理 ==========
        # 视图状态
        current_view = {"value": "files"}  # 'files' | 'cloud_sync' | 'mcp_config' | 'logs' | 'settings'
        selected_setting = {"value": None}  # 'appearance' | 'embedding' | 'mcp' | 'storage' | 'webdav'
        selected_client = {"value": None}  # MCP 客户端 ID

        # 文件库状态
        state = {
            "selected_file_id": None,
            "search_keyword": "",
            "files_data": [],
            "filtered_files": [],
            "chunks_data": [],
            # 切片分页状态
            "chunk_page": 1,
            "chunk_page_size": 50,
        }

        # 云同步状态
        # 从配置文件读取上次同步时间
        from datetime import datetime
        settings = get_settings()
        last_sync_time = settings.webdav.last_sync_time
        last_sync_display = None
        if last_sync_time:
            try:
                # 将 ISO 格式转为显示格式
                dt = datetime.fromisoformat(last_sync_time)
                last_sync_display = dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                pass

        sync_state = {
            "is_syncing": False,
            "last_sync": last_sync_display,
            "last_result": None,
            "logs": [],
        }

        # 设置表单数据
        settings_form = {}

        # UI 组件引用（用于跨函数刷新）
        ui_refs = {
            "upload_input": None,
            "file_list_container": None,
            "settings_list": None,
            "client_list": None,
            "chunk_inspector": None,
            "stats_label": None,
        }

        # ========== 初始化处理器 ==========
        task_handlers = TaskHandlers(state, ui_refs)
        settings_handlers = SettingsHandlers(settings_form)

        file_handlers = FileHandlers(
            state=state,
            ui_refs=ui_refs,
            on_task_created=task_handlers.add_task,
        )

        # 设置 file_handlers 引用以便复用 apply_filter
        task_handlers.set_file_handlers(file_handlers)

        # sync_handlers 需要在 file_handlers 之后初始化，以便传入回调
        sync_handlers = SyncHandlers(
            sync_state,
            ui_refs,
            on_pull_complete=file_handlers.refresh_and_scan
        )

        chunk_handlers = ChunkHandlers(
            state=state,
            ui_refs=ui_refs,
            on_task_created=task_handlers.add_task,
            on_refresh_files=file_handlers.load_files,
        )

        # ========== 视图切换 ==========

        def switch_to_files():
            """切换到文件库视图"""
            current_view["value"] = "files"
            selected_setting["value"] = None
            selected_client["value"] = None
            sidebar_nav.refresh()
            middle_column.refresh()
            right_column.refresh()

        def switch_to_cloud_sync():
            """切换到云同步视图"""
            current_view["value"] = "cloud_sync"
            selected_setting["value"] = None
            selected_client["value"] = None
            sidebar_nav.refresh()
            middle_column.refresh()
            right_column.refresh()

        def switch_to_mcp_config():
            """切换到 MCP 配置视图"""
            current_view["value"] = "mcp_config"
            selected_setting["value"] = None
            selected_client["value"] = None
            sidebar_nav.refresh()
            middle_column.refresh()
            right_column.refresh()

        def switch_to_logs():
            """切换到日志视图"""
            current_view["value"] = "logs"
            selected_setting["value"] = None
            selected_client["value"] = None
            sidebar_nav.refresh()
            middle_column.refresh()
            right_column.refresh()

        def switch_to_settings():
            """切换到设置视图"""
            current_view["value"] = "settings"
            selected_setting["value"] = None
            selected_client["value"] = None
            settings_handlers.init_settings_form()
            sidebar_nav.refresh()
            middle_column.refresh()
            right_column.refresh()

        def select_setting(setting_key: str):
            """选择设置分类"""
            selected_setting["value"] = setting_key
            if ui_refs["settings_list"]:
                ui_refs["settings_list"].refresh()
            right_column.refresh()

        def select_client(client_id: str):
            """选择 MCP 客户端"""
            selected_client["value"] = client_id
            if ui_refs["client_list"]:
                ui_refs["client_list"].refresh()
            right_column.refresh()

        # ========== 主题初始化 ==========
        dark_mode = ui.dark_mode()
        settings = get_settings()
        current_theme_value = settings.appearance.theme

        def on_apply_theme(theme: str):
            """应用主题回调"""
            apply_theme(dark_mode, theme)

        # 初始化主题
        init_theme(dark_mode, current_theme_value)

        # 注入主题 CSS
        inject_theme_css()

        # ========== 页面布局 ==========
        with ui.row().classes("w-full h-screen overflow-hidden gap-0"):

            # ========== 左栏: 侧边栏导航 ==========
            sidebar_nav = render_sidebar(
                current_view=current_view,
                switch_to_files=switch_to_files,
                switch_to_cloud_sync=switch_to_cloud_sync,
                switch_to_mcp_config=switch_to_mcp_config,
                switch_to_logs=switch_to_logs,
                switch_to_settings=switch_to_settings,
                ui_refs=ui_refs,
            )

            # ========== 中栏 ==========
            @ui.refreshable
            def middle_column():
                if current_view["value"] == "files":
                    render_files_middle(
                        state=state,
                        ui_refs=ui_refs,
                        file_handlers=file_handlers,
                    )
                elif current_view["value"] == "cloud_sync":
                    render_cloud_sync_middle(
                        sync_state=sync_state,
                        ui_refs=ui_refs,
                        sync_handlers=sync_handlers,
                    )
                elif current_view["value"] == "mcp_config":
                    render_mcp_config_middle(
                        selected_client=selected_client,
                        ui_refs=ui_refs,
                        on_select_client=select_client,
                    )
                elif current_view["value"] == "logs":
                    render_logs_middle(ui_refs=ui_refs)
                else:
                    render_settings_middle(
                        selected_setting=selected_setting,
                        ui_refs=ui_refs,
                        on_select_setting=select_setting,
                    )

            middle_column()

            # ========== 右栏 ==========
            @ui.refreshable
            def right_column():
                if current_view["value"] == "files":
                    render_files_right(
                        state=state,
                        ui_refs=ui_refs,
                        chunk_handlers=chunk_handlers,
                    )
                elif current_view["value"] == "cloud_sync":
                    render_cloud_sync_right(
                        sync_state=sync_state,
                        ui_refs=ui_refs,
                    )
                elif current_view["value"] == "mcp_config":
                    render_mcp_config_right(
                        selected_client=selected_client,
                    )
                elif current_view["value"] == "logs":
                    render_logs_right(ui_refs=ui_refs)
                else:
                    render_settings_right(
                        selected_setting=selected_setting,
                        settings_form=settings_form,
                        settings_handlers=settings_handlers,
                        apply_theme_callback=on_apply_theme,
                    )

            right_column()

        # ========== 初始化 ==========
        file_handlers.load_files()
        file_handlers.load_stats()

        ui.timer(1.0, task_handlers.check_pending_tasks)
