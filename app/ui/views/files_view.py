"""
文件库视图

职责:
- 渲染文件库中栏（文件列表）
- 渲染文件库右栏（切片详情）
"""

from nicegui import ui

from app.i18n import t
from app.ui.components import status_badge, chunk_card


def render_files_middle(
    state: dict,
    ui_refs: dict,
    file_handlers,
):
    """
    渲染文件库中栏

    Args:
        state: 共享状态字典
        ui_refs: UI 组件引用字典
        file_handlers: 文件处理器实例
    """
    with ui.column().classes(
        "w-64 h-full flex flex-col overflow-hidden theme-panel"
    ).style("border-right: 1px solid var(--border-color)"):
        # 顶部标题栏
        with ui.row().classes(
            "w-full px-3 items-center justify-between"
        ).style("border-bottom: 1px solid var(--border-color); height: 49px"):
            ui.label(t("files.title")).classes("text-sm font-medium theme-text")

            @ui.refreshable
            def toolbar_buttons():
                if state.get("batch_mode"):
                    # 批量模式：显示全选、确认删除、取消按钮
                    with ui.row().classes("items-center gap-1"):
                        # 全选复选框
                        ui.checkbox(
                            t("files.batch_select_all"),
                            value=file_handlers.is_all_selected(),
                            on_change=lambda: file_handlers.toggle_select_all()
                        ).props("dense").classes("text-xs")
                        # 确认删除按钮
                        ui.button(
                            icon="delete",
                            on_click=file_handlers.confirm_batch_delete
                        ).props("flat dense round size=sm").classes("text-red-400").tooltip(t("files.batch_confirm"))
                        # 取消按钮
                        ui.button(
                            icon="close",
                            on_click=file_handlers.exit_batch_mode
                        ).props("flat dense round size=sm").classes("theme-text-muted").tooltip(t("files.batch_cancel"))
                else:
                    # 普通模式：显示常规按钮
                    with ui.row().classes("items-center gap-1"):
                        ui.button(icon="refresh", on_click=file_handlers.refresh_and_scan).props(
                            "flat dense round size=sm"
                        ).classes("theme-text-muted").tooltip(t("files.refresh"))
                        ui.button(
                            icon="note_add",
                            on_click=file_handlers.handle_create_file
                        ).props("flat dense round size=sm").classes("theme-text-accent").tooltip(t("files.create"))
                        ui.button(
                            icon="upload_file",
                            on_click=lambda: ui_refs["upload_input"].run_method('pickFiles')
                        ).props("flat dense round size=sm").classes("theme-text-accent").tooltip(t("files.upload"))
                        ui.button(
                            icon="delete_sweep",
                            on_click=file_handlers.enter_batch_mode
                        ).props("flat dense round size=sm").classes("text-red-400").tooltip(t("files.batch_delete"))

            ui_refs["toolbar_buttons"] = toolbar_buttons
            toolbar_buttons()

        # 隐藏的上传组件（支持批量上传）
        ui_refs["upload_input"] = ui.upload(
            on_upload=file_handlers.handle_upload,
            auto_upload=True,
            multiple=True,
        ).props("accept=.md,.pdf,.pptx,.xlsx,.docx,.txt").classes("hidden")

        # 搜索框
        with ui.row().classes("w-full px-2 py-2"):
            ui.input(placeholder=t("files.search")).props(
                "dense outlined rounded"
            ).classes("w-full text-sm").on("update:model-value", file_handlers.on_search_change)

        # 文件列表
        with ui.scroll_area().classes("flex-1"):
            @ui.refreshable
            def file_list_container():
                if not state["filtered_files"]:
                    with ui.element("div").classes("w-full h-32 flex flex-col items-center justify-center"):
                        ui.icon("folder_open", size="md").classes("theme-text-muted")
                        if state["search_keyword"]:
                            ui.label(t("files.not_found")).classes("text-xs theme-text-muted")
                        else:
                            ui.label(t("files.empty")).classes("text-xs theme-text-muted")
                    return

                batch_mode = state.get("batch_mode", False)
                batch_selected_ids = state.get("batch_selected_ids", set())

                for f in state["filtered_files"]:
                    file_id = f["id"]
                    is_selected = file_id == state["selected_file_id"]
                    is_batch_selected = file_id in batch_selected_ids

                    container_classes = "w-full px-3 py-2 cursor-pointer transition-colors border-l-4 "
                    if batch_mode and is_batch_selected:
                        container_classes += "theme-border-selected theme-selected"
                    elif is_selected and not batch_mode:
                        container_classes += "theme-border-selected theme-selected"
                    else:
                        container_classes += "border-l-transparent theme-hover"

                    # 批量模式下点击切换选中，普通模式下点击加载切片
                    if batch_mode:
                        click_handler = lambda _, fid=file_id: file_handlers.toggle_file_selection(fid)
                    else:
                        click_handler = lambda _, fid=file_id: file_handlers.load_chunks(fid)

                    with ui.element("div").classes(container_classes).style(
                        "border-bottom: 1px solid var(--border-color)"
                    ).on("click", click_handler):
                        if batch_mode:
                            # 批量模式：显示复选框
                            with ui.element("div").classes(
                                "grid items-center gap-2"
                            ).style("grid-template-columns: auto auto 1fr auto"):
                                ui.checkbox(
                                    value=is_batch_selected,
                                ).props("dense size=xs disable").style("pointer-events: none")
                                ui.icon("description", size="xs").classes(
                                    "theme-text-accent" if is_batch_selected else "theme-text-muted"
                                ).style("pointer-events: none")
                                ui.label(f["filename"]).classes(
                                    "text-sm truncate theme-text"
                                ).tooltip(f["filename"])
                                status_badge(f["status"])
                        else:
                            # 普通模式：原有布局
                            with ui.element("div").classes(
                                "grid items-center gap-2"
                            ).style("grid-template-columns: auto 1fr auto"):
                                ui.icon("description", size="xs").classes(
                                    "theme-text-accent" if is_selected else "theme-text-muted"
                                )
                                ui.label(f["filename"]).classes(
                                    "text-sm truncate theme-text"
                                ).tooltip(f["filename"])
                                status_badge(f["status"])

            # 保存引用以便外部刷新
            ui_refs["file_list_container"] = file_list_container
            file_list_container()


def render_files_right(
    state: dict,
    ui_refs: dict,
    chunk_handlers,
):
    """
    渲染文件库右栏

    Args:
        state: 共享状态字典
        ui_refs: UI 组件引用字典
        chunk_handlers: 切片处理器实例
    """
    with ui.column().classes("flex-1 h-full flex flex-col theme-content min-w-0"):
        # 顶部信息区
        with ui.row().classes(
            "w-full px-5 items-center justify-between theme-sidebar"
        ).style("border-bottom: 1px solid var(--border-color); height: 49px"):
            with ui.row().classes("items-center gap-2"):
                ui.icon("article", size="xs").classes("theme-text-accent")
                ui.label(t("chunks.title")).classes("text-sm font-medium theme-text")

            @ui.refreshable
            def chunk_toolbar_buttons():
                if state.get("chunk_batch_mode"):
                    # 批量模式：显示全选、确认删除、取消按钮
                    with ui.row().classes("items-center gap-1"):
                        ui.checkbox(
                            t("chunks.batch_select_all"),
                            value=chunk_handlers.is_all_chunks_selected(),
                            on_change=lambda: chunk_handlers.toggle_chunk_select_all()
                        ).props("dense").classes("text-xs")
                        ui.button(
                            icon="delete",
                            on_click=chunk_handlers.confirm_chunk_batch_delete
                        ).props("flat dense round size=sm").classes("text-red-400").tooltip(t("chunks.batch_confirm"))
                        ui.button(
                            icon="close",
                            on_click=chunk_handlers.exit_chunk_batch_mode
                        ).props("flat dense round size=sm").classes("theme-text-muted").tooltip(t("chunks.batch_cancel"))
                else:
                    # 普通模式：显示常规按钮
                    with ui.row().classes("items-center gap-1"):
                        ui.button(icon="add", on_click=chunk_handlers.handle_add_chunk).props(
                            "flat dense round size=sm"
                        ).classes("theme-text-accent").tooltip(t("chunks.add"))
                        ui.button(
                            icon="refresh",
                            on_click=lambda: chunk_handlers._reload_chunks() if state["selected_file_id"] else None
                        ).props("flat dense round size=sm").classes("theme-text-muted").tooltip(t("chunks.refresh"))
                        ui.button(
                            icon="delete_sweep",
                            on_click=chunk_handlers.enter_chunk_batch_mode
                        ).props("flat dense round size=sm").classes("text-red-400").tooltip(t("chunks.batch_delete"))

            ui_refs["chunk_toolbar_buttons"] = chunk_toolbar_buttons
            chunk_toolbar_buttons()

        # 切片内容区
        with ui.scroll_area().classes("flex-1 p-4 min-w-0"):
            @ui.refreshable
            def chunk_inspector():
                if state["selected_file_id"] is None:
                    with ui.column().classes(
                        "w-full h-full items-center justify-center"
                    ):
                        ui.icon("touch_app", size="lg").classes("theme-text-muted")
                        ui.label(t("chunks.select_file")).classes(
                            "text-sm mt-2 theme-text-muted"
                        )
                    return

                if not state["chunks_data"]:
                    with ui.column().classes(
                        "w-full h-full items-center justify-center"
                    ):
                        ui.icon("content_cut", size="lg").classes("theme-text-muted")
                        ui.label(t("chunks.empty")).classes(
                            "text-sm mt-2 theme-text-muted"
                        )
                    return

                chunk_batch_mode = state.get("chunk_batch_mode", False)
                chunk_batch_selected_ids = state.get("chunk_batch_selected_ids", set())

                # 获取当前页的切片
                visible_chunks = chunk_handlers.get_visible_chunks()

                with ui.column().classes("w-full min-w-0"):
                    for chunk in visible_chunks:
                        chunk_id = chunk["id"]
                        is_batch_selected = chunk_id in chunk_batch_selected_ids

                        if chunk_batch_mode:
                            # 批量模式：显示带复选框的卡片
                            with ui.row().classes("w-full mb-3 items-start gap-2 min-w-0"):
                                # 复选框
                                ui.checkbox(
                                    value=is_batch_selected,
                                    on_change=lambda _, cid=chunk_id: chunk_handlers.toggle_chunk_selection(cid)
                                ).props("dense")
                                # 卡片
                                with ui.column().classes("flex-1 min-w-0"):
                                    chunk_card(
                                        doc_title=chunk["doc_title"],
                                        chunk_text=chunk["chunk_text"],
                                        chunk_id=chunk["id"],
                                        on_edit=None,
                                        on_delete=None,
                                    )
                        else:
                            # 普通模式
                            chunk_card(
                                doc_title=chunk["doc_title"],
                                chunk_text=chunk["chunk_text"],
                                chunk_id=chunk["id"],
                                on_edit=chunk_handlers.handle_edit_chunk,
                                on_delete=chunk_handlers.handle_delete_chunk,
                            )

                    # 分页控件
                    total_chunks = len(state["chunks_data"])
                    if total_chunks > state["chunk_page_size"]:
                        current_page = state["chunk_page"]
                        total_pages = chunk_handlers.get_total_chunk_pages()
                        start_idx = (current_page - 1) * state["chunk_page_size"] + 1
                        end_idx = min(current_page * state["chunk_page_size"], total_chunks)

                        with ui.row().classes("w-full items-center justify-between mt-4 pt-4").style("border-top: 1px solid var(--border-color)"):
                            # 左侧：统计信息
                            ui.label(t("chunks.pagination_info", start=start_idx, end=end_idx, total=total_chunks)).classes("text-xs theme-text-muted")

                            # 右侧：分页按钮
                            with ui.row().classes("items-center gap-2"):
                                # 上一页按钮
                                ui.button(
                                    icon="chevron_left",
                                    on_click=chunk_handlers.prev_chunk_page
                                ).props("flat dense round size=sm").classes("theme-text-muted").props(
                                    "disable" if current_page == 1 else ""
                                )

                                # 页码显示
                                ui.label(t("chunks.pagination_page", current=current_page, total=total_pages)).classes("text-sm theme-text")

                                # 下一页按钮
                                ui.button(
                                    icon="chevron_right",
                                    on_click=chunk_handlers.next_chunk_page
                                ).props("flat dense round size=sm").classes("theme-text-muted").props(
                                    "disable" if current_page == total_pages else ""
                                )

            ui_refs["chunk_inspector"] = chunk_inspector
            chunk_inspector()
