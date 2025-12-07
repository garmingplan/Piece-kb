"""
设置视图

职责:
- 渲染设置中栏（设置分类列表）
- 渲染设置右栏（各类设置表单）
"""

from nicegui import ui

from app.i18n import t, SUPPORTED_LANGUAGES


def render_settings_middle(
    selected_setting: dict,
    ui_refs: dict,
    on_select_setting: callable,
):
    """
    渲染设置中栏

    Args:
        selected_setting: 选中的设置分类 {"value": str | None}
        ui_refs: UI 组件引用字典
        on_select_setting: 选择设置分类的回调
    """
    with ui.column().classes(
        "w-64 h-full flex flex-col overflow-hidden theme-panel"
    ).style("border-right: 1px solid var(--border-color)"):
        # 顶部标题栏
        with ui.row().classes(
            "w-full px-3 items-center justify-between"
        ).style("border-bottom: 1px solid var(--border-color); height: 49px"):
            ui.label(t("settings.title")).classes("text-sm font-medium theme-text")

        # 设置分类列表
        with ui.scroll_area().classes("flex-1"):
            @ui.refreshable
            def settings_list():
                settings_items = [
                    ("appearance", "palette", t("settings.appearance")),
                    ("embedding", "smart_toy", t("settings.embedding")),
                    ("mcp", "hub", t("settings.mcp")),
                    ("storage", "folder_open", t("settings.storage")),
                    ("webdav", "cloud_sync", t("settings.webdav")),
                ]

                for key, icon, label in settings_items:
                    is_selected = selected_setting["value"] == key
                    container_classes = "w-full px-3 py-3 cursor-pointer transition-colors border-l-4 "
                    if is_selected:
                        container_classes += "theme-border-selected theme-selected"
                    else:
                        container_classes += "border-l-transparent theme-hover"

                    with ui.element("div").classes(container_classes).style(
                        "border-bottom: 1px solid var(--border-color)"
                    ).on("click", lambda _, k=key: on_select_setting(k)):
                        with ui.row().classes("items-center gap-2"):
                            ui.icon(icon, size="xs").classes(
                                "theme-text-accent" if is_selected else "theme-text-muted"
                            )
                            ui.label(label).classes("text-sm theme-text")

            ui_refs["settings_list"] = settings_list
            settings_list()


def render_settings_right(
    selected_setting: dict,
    settings_form: dict,
    settings_handlers,
    apply_theme_callback: callable,
):
    """
    渲染设置右栏

    Args:
        selected_setting: 选中的设置分类
        settings_form: 设置表单数据
        settings_handlers: 设置处理器实例
        apply_theme_callback: 应用主题的回调
    """
    with ui.column().classes("flex-1 h-full flex flex-col theme-content"):
        # 顶部信息区
        setting_titles = {
            "appearance": ("palette", t("settings_appearance.title")),
            "embedding": ("smart_toy", t("settings_embedding.title")),
            "mcp": ("hub", t("settings_mcp.title")),
            "storage": ("folder_open", t("settings_storage.title")),
            "webdav": ("cloud_sync", t("settings_webdav.title")),
        }

        if selected_setting["value"] and selected_setting["value"] in setting_titles:
            icon, title = setting_titles[selected_setting["value"]]
        else:
            icon, title = "settings", t("settings.title")

        with ui.row().classes(
            "w-full px-5 items-center justify-between theme-sidebar"
        ).style("border-bottom: 1px solid var(--border-color); height: 49px"):
            with ui.row().classes("items-center gap-2"):
                ui.icon(icon, size="xs").classes("theme-text-accent")
                ui.label(title).classes("text-sm font-medium theme-text")

        # 设置内容区
        with ui.scroll_area().classes("flex-1 p-4"):
            if selected_setting["value"] is None:
                with ui.column().classes("w-full h-full items-center justify-center"):
                    ui.icon("tune", size="lg").classes("theme-text-muted")
                    ui.label(t("settings.select_item")).classes("text-sm mt-2 theme-text-muted")
            elif selected_setting["value"] == "appearance":
                _render_appearance_settings(settings_form, settings_handlers, apply_theme_callback)
            elif selected_setting["value"] == "embedding":
                _render_embedding_settings(settings_form, settings_handlers)
            elif selected_setting["value"] == "mcp":
                _render_mcp_settings(settings_form, settings_handlers)
            elif selected_setting["value"] == "storage":
                _render_storage_settings(settings_form, settings_handlers)
            elif selected_setting["value"] == "webdav":
                _render_webdav_settings(settings_form, settings_handlers)


def _render_appearance_settings(settings_form: dict, settings_handlers, apply_theme_callback: callable):
    """渲染基础设置表单"""
    with ui.card().classes("w-full max-w-lg theme-card").style("border: 1px solid var(--border-color)"):
        with ui.column().classes("w-full gap-4 p-4"):
            # 主题设置
            ui.label(t("settings_appearance.theme")).classes("text-sm font-medium theme-text")

            current_theme = settings_form.get("theme", "light")

            def on_theme_change(e):
                settings_form["theme"] = e.value
                # 立即应用主题
                apply_theme_callback(e.value)

            ui.toggle(
                options={
                    "light": t("settings_appearance.theme_light"),
                    "dark": t("settings_appearance.theme_dark"),
                    "pink": t("settings_appearance.theme_pink")
                },
                value=current_theme,
                on_change=on_theme_change,
            ).classes("theme-text")

            ui.separator()

            # 语言设置
            ui.label(t("settings_appearance.language")).classes("text-sm font-medium theme-text")

            current_language = settings_form.get("language", "zh")

            def on_language_change(e):
                settings_form["language"] = e.value

            ui.toggle(
                options=SUPPORTED_LANGUAGES,
                value=current_language,
                on_change=on_language_change,
            ).classes("theme-text")

            ui.label(t("settings_appearance.language_hint")).classes("text-xs theme-text-muted")

            ui.separator()

            # 启动时最小化设置
            ui.label(t("settings_appearance.start_minimized")).classes("text-sm font-medium theme-text")

            current_start_minimized = settings_form.get("start_minimized", False)

            def on_start_minimized_change(e):
                settings_form["start_minimized"] = e.value

            ui.switch(
                value=current_start_minimized,
                on_change=on_start_minimized_change,
            ).classes("theme-text")

            ui.label(t("settings_appearance.start_minimized_hint")).classes("text-xs theme-text-muted")

            ui.separator()

            with ui.row().classes("w-full justify-end"):
                ui.button(t("settings.btn_save"), on_click=settings_handlers.save_settings_form).props("color=primary")


def _render_embedding_settings(settings_form: dict, settings_handlers):
    """渲染嵌入模型设置表单"""
    with ui.card().classes("w-full max-w-lg theme-card").style("border: 1px solid var(--border-color)"):
        with ui.column().classes("w-full gap-4 p-4"):
            ui.input(
                label=t("settings_embedding.base_url"),
                value=settings_form.get("base_url", ""),
                on_change=lambda e: settings_form.update({"base_url": e.value}),
            ).props("dense outlined").classes("w-full")

            ui.input(
                label=t("settings_embedding.api_key"),
                value=settings_form.get("api_key", ""),
                password=True,
                password_toggle_button=True,
                on_change=lambda e: settings_form.update({"api_key": e.value}),
            ).props("dense outlined").classes("w-full")

            ui.input(
                label=t("settings_embedding.model"),
                value=settings_form.get("model", ""),
                on_change=lambda e: settings_form.update({"model": e.value}),
            ).props("dense outlined").classes("w-full")

            ui.number(
                label=t("settings_embedding.vector_dim"),
                value=settings_form.get("vector_dim", 1024),
                min=1,
                max=4096,
                on_change=lambda e: settings_form.update({"vector_dim": e.value}),
            ).props("dense outlined").classes("w-full")

            # 测试连接
            with ui.row().classes("w-full items-center justify-between"):
                test_result = ui.label("").classes("text-xs flex-1 theme-text-muted")
                test_btn = ui.button(
                    t("settings_embedding.test_btn"),
                    on_click=lambda: settings_handlers.test_embedding_connection(test_result, test_btn)
                ).props("dense outline size=sm").classes("theme-text-accent")

            ui.separator()

            with ui.row().classes("w-full justify-end"):
                ui.button(t("settings.btn_save"), on_click=settings_handlers.save_settings_form).props("color=primary")


def _render_mcp_settings(settings_form: dict, settings_handlers):
    """渲染 MCP 服务设置表单"""
    with ui.card().classes("w-full max-w-lg theme-card").style("border: 1px solid var(--border-color)"):
        with ui.column().classes("w-full gap-4 p-4"):
            ui.number(
                label=t("settings_mcp.port"),
                value=settings_form.get("mcp_port", 8686),
                min=1024,
                max=65535,
                on_change=lambda e: settings_form.update({"mcp_port": e.value}),
            ).props("dense outlined").classes("w-full")

            ui.label(t("settings_mcp.port_hint")).classes("text-xs theme-text-muted")

            ui.separator()

            with ui.row().classes("w-full justify-end"):
                ui.button(t("settings.btn_save"), on_click=settings_handlers.save_settings_form).props("color=primary")


def _render_storage_settings(settings_form: dict, settings_handlers):
    """渲染数据存储设置表单"""
    with ui.card().classes("w-full max-w-lg theme-card").style("border: 1px solid var(--border-color)"):
        with ui.column().classes("w-full gap-4 p-4"):
            ui.input(
                label=t("settings_storage.data_path"),
                value=settings_form.get("data_path", "./data"),
                on_change=lambda e: settings_form.update({"data_path": e.value}),
            ).props("dense outlined").classes("w-full")

            ui.label(t("settings_storage.data_path_hint")).classes("text-xs theme-text-muted")

            ui.separator()

            with ui.row().classes("w-full justify-end"):
                ui.button(t("settings.btn_save"), on_click=settings_handlers.save_settings_form).props("color=primary")


def _render_webdav_settings(settings_form: dict, settings_handlers):
    """渲染 WebDAV 云同步设置表单"""
    with ui.card().classes("w-full max-w-lg theme-card").style("border: 1px solid var(--border-color)"):
        with ui.column().classes("w-full gap-4 p-4"):
            # 启用开关
            ui.label(t("settings_webdav.enabled")).classes("text-sm font-medium theme-text")

            current_enabled = settings_form.get("webdav_enabled", False)

            def on_enabled_change(e):
                settings_form["webdav_enabled"] = e.value

            ui.switch(
                value=current_enabled,
                on_change=on_enabled_change,
            ).classes("theme-text")

            ui.separator()

            # WebDAV 服务器地址
            ui.input(
                label=t("settings_webdav.hostname"),
                value=settings_form.get("webdav_hostname", ""),
                on_change=lambda e: settings_form.update({"webdav_hostname": e.value}),
            ).props("dense outlined").classes("w-full")

            ui.label(t("settings_webdav.hostname_hint")).classes("text-xs theme-text-muted")

            # 用户名
            ui.input(
                label=t("settings_webdav.username"),
                value=settings_form.get("webdav_username", ""),
                on_change=lambda e: settings_form.update({"webdav_username": e.value}),
            ).props("dense outlined").classes("w-full")

            # 密码
            ui.input(
                label=t("settings_webdav.password"),
                value=settings_form.get("webdav_password", ""),
                password=True,
                password_toggle_button=True,
                on_change=lambda e: settings_form.update({"webdav_password": e.value}),
            ).props("dense outlined").classes("w-full")

            ui.label(t("settings_webdav.password_hint")).classes("text-xs theme-text-muted")

            # 测试连接
            with ui.row().classes("w-full items-center justify-between"):
                test_result = ui.label("").classes("text-xs flex-1 theme-text-muted")
                test_btn = ui.button(
                    t("settings_webdav.test_btn"),
                    on_click=lambda: settings_handlers.test_webdav_connection(test_result, test_btn)
                ).props("dense outline size=sm").classes("theme-text-accent")

            ui.separator()

            with ui.row().classes("w-full justify-end"):
                ui.button(t("settings.btn_save"), on_click=settings_handlers.save_settings_form).props("color=primary")
