"""
可复用 UI 组件

职责:
- 定义可在多个页面复用的组件
- 保持 UI 风格一致性
"""

from typing import Callable, Optional
from nicegui import ui
from app.i18n import t


def status_badge(status: str):
    """状态徽章组件（紧凑样式）"""
    color_map = {
        "pending": "orange",
        "processing": "blue",
        "completed": "green",
        "indexed": "green",
        "failed": "red",
        "error": "red",
        "empty": "grey",
    }
    color = color_map.get(status, "gray")
    ui.badge(status, color=color).props("dense")


def chunk_card(
    doc_title: str,
    chunk_text: str,
    chunk_id: int = None,
    on_edit: Optional[Callable] = None,
    on_delete: Optional[Callable] = None,
):
    """
    切片卡片组件（支持编辑/删除）

    Args:
        doc_title: 文档标题
        chunk_text: 切片文本内容（支持Markdown格式）
        chunk_id: 切片 ID
        on_edit: 编辑回调函数，传入 chunk_id
        on_delete: 删除回调函数，传入 chunk_id
    """
    with ui.card().props("flat bordered").classes("w-full mb-3 theme-card overflow-hidden").style("border: 1px solid var(--border-color)"):
        with ui.card_section().classes("py-3 px-4 min-w-0"):
            # 标题行：标题 + 操作按钮 + 序号
            with ui.row().classes("items-center justify-between mb-2"):
                ui.label(doc_title).classes("font-semibold text-base theme-text-accent")
                with ui.row().classes("items-center gap-1"):
                    # 编辑按钮
                    if on_edit:
                        ui.button(
                            icon="edit",
                            on_click=lambda: on_edit(chunk_id)
                        ).props("flat dense round size=xs").classes("theme-text-muted")
                    # 删除按钮
                    if on_delete:
                        ui.button(
                            icon="delete",
                            on_click=lambda: on_delete(chunk_id)
                        ).props("flat dense round size=xs").classes("theme-text-muted")
                    # ID 徽章
                    if chunk_id:
                        ui.badge(f"#{chunk_id}", color="grey").props(
                            "dense outline"
                        ).classes("text-xs")

            # 正文内容（Markdown渲染）
            ui.markdown(chunk_text).classes(
                "chunk-content text-sm leading-relaxed"
            )


def chunk_edit_dialog(
    chunk_id: int,
    doc_title: str,
    chunk_text: str,
    on_save: Callable,
    on_close: Callable,
):
    """
    切片编辑对话框

    Args:
        chunk_id: 切片 ID
        doc_title: 当前标题
        chunk_text: 当前内容
        on_save: 保存回调，传入 (chunk_id, new_title, new_text)
        on_close: 关闭回调
    """
    form_data = {
        "doc_title": doc_title,
        "chunk_text": chunk_text,
    }

    with ui.dialog() as dialog, ui.card().classes("w-[600px] theme-card"):
        # 标题栏
        with ui.row().classes(
            "w-full items-center justify-between pb-2"
        ).style("border-bottom: 1px solid var(--border-color)"):
            ui.label(t("chunk_dialog.edit_title", id=chunk_id)).classes("text-lg font-semibold theme-text")
            ui.button(icon="close", on_click=dialog.close).props("flat dense round").classes("theme-text-muted")

        # 编辑内容
        with ui.column().classes("w-full gap-4 py-4"):
            ui.input(
                label=t("chunk_dialog.label_title"),
                value=form_data["doc_title"],
                on_change=lambda e: form_data.update({"doc_title": e.value}),
            ).props("dense outlined").classes("w-full")

            ui.textarea(
                label=t("chunk_dialog.label_content"),
                value=form_data["chunk_text"],
                on_change=lambda e: form_data.update({"chunk_text": e.value}),
            ).props("outlined rows=12").classes("w-full")

            ui.label(t("chunk_dialog.edit_hint")).classes(
                "text-xs theme-text-muted"
            )

        # 底部按钮
        with ui.row().classes("w-full justify-end gap-2 pt-2").style("border-top: 1px solid var(--border-color)"):
            ui.button(t("chunk_dialog.btn_cancel"), on_click=dialog.close).props("flat").classes("theme-text-muted")
            ui.button(
                t("chunk_dialog.btn_save"),
                on_click=lambda: [
                    on_save(
                        chunk_id,
                        form_data["doc_title"],
                        form_data["chunk_text"],
                    ),
                    dialog.close(),
                ],
            ).props("color=primary")

    dialog.on("close", on_close)
    dialog.open()
    return dialog


def chunk_add_dialog(
    file_id: int,
    on_save: Callable,
    on_close: Callable,
):
    """
    新增切片对话框

    Args:
        file_id: 所属文件 ID
        on_save: 保存回调，传入 (file_id, doc_title, chunk_text)
        on_close: 关闭回调
    """
    form_data = {
        "doc_title": "",
        "chunk_text": "",
    }

    with ui.dialog() as dialog, ui.card().classes("w-[600px] theme-card"):
        # 标题栏
        with ui.row().classes(
            "w-full items-center justify-between pb-2"
        ).style("border-bottom: 1px solid var(--border-color)"):
            ui.label(t("chunk_dialog.add_title")).classes("text-lg font-semibold theme-text")
            ui.button(icon="close", on_click=dialog.close).props("flat dense round").classes("theme-text-muted")

        # 表单内容
        with ui.column().classes("w-full gap-4 py-4"):
            ui.input(
                label=t("chunk_dialog.label_title"),
                placeholder=t("chunk_dialog.placeholder_title"),
                on_change=lambda e: form_data.update({"doc_title": e.value}),
            ).props("dense outlined").classes("w-full")

            ui.textarea(
                label=t("chunk_dialog.label_content"),
                placeholder=t("chunk_dialog.placeholder_content"),
                on_change=lambda e: form_data.update({"chunk_text": e.value}),
            ).props("outlined rows=12").classes("w-full")

            ui.label(t("chunk_dialog.add_hint")).classes(
                "text-xs theme-text-muted"
            )

        # 底部按钮
        with ui.row().classes("w-full justify-end gap-2 pt-2").style("border-top: 1px solid var(--border-color)"):
            ui.button(t("chunk_dialog.btn_cancel"), on_click=dialog.close).props("flat").classes("theme-text-muted")
            ui.button(
                t("chunk_dialog.btn_add"),
                on_click=lambda: [
                    on_save(
                        file_id,
                        form_data["doc_title"],
                        form_data["chunk_text"],
                    ),
                    dialog.close(),
                ],
            ).props("color=primary")

    dialog.on("close", on_close)
    dialog.open()
    return dialog


def confirm_dialog(
    title: str,
    message: str,
    on_confirm: Callable,
    confirm_text: str = None,
    cancel_text: str = None,
    danger: bool = False,
):
    """
    确认对话框

    Args:
        title: 对话框标题
        message: 提示信息
        on_confirm: 确认回调
        confirm_text: 确认按钮文字
        cancel_text: 取消按钮文字
        danger: 是否为危险操作（红色按钮）
    """
    # 使用默认翻译文本
    if confirm_text is None:
        confirm_text = t("confirm_dialog.btn_confirm")
    if cancel_text is None:
        cancel_text = t("confirm_dialog.btn_cancel")
    with ui.dialog() as dialog, ui.card().classes("w-[400px] theme-card"):
        with ui.row().classes(
            "w-full items-center justify-between pb-2"
        ).style("border-bottom: 1px solid var(--border-color)"):
            ui.label(title).classes("text-lg font-semibold theme-text")
            ui.button(icon="close", on_click=dialog.close).props("flat dense round").classes("theme-text-muted")

        with ui.column().classes("w-full py-4"):
            ui.label(message).classes("theme-text-secondary")

        with ui.row().classes("w-full justify-end gap-2 pt-2").style("border-top: 1px solid var(--border-color)"):
            ui.button(cancel_text, on_click=dialog.close).props("flat").classes("theme-text-muted")
            btn_props = "color=red" if danger else "color=primary"
            ui.button(
                confirm_text,
                on_click=lambda: [on_confirm(), dialog.close()],
            ).props(btn_props)

    dialog.open()
    return dialog


def file_create_dialog(
    on_create: Callable,
    on_close: Callable = None,
):
    """
    新建文件对话框

    Args:
        on_create: 创建回调，传入 filename
        on_close: 关闭回调
    """
    form_data = {"filename": ""}

    with ui.dialog() as dialog, ui.card().classes("w-[400px] theme-card"):
        # 标题栏
        with ui.row().classes(
            "w-full items-center justify-between pb-2"
        ).style("border-bottom: 1px solid var(--border-color)"):
            ui.label(t("file_dialog.create_title")).classes("text-lg font-semibold theme-text")
            ui.button(icon="close", on_click=dialog.close).props("flat dense round").classes("theme-text-muted")

        # 表单内容
        with ui.column().classes("w-full gap-4 py-4"):
            ui.input(
                label=t("file_dialog.label_filename"),
                placeholder=t("file_dialog.placeholder_filename"),
                on_change=lambda e: form_data.update({"filename": e.value}),
            ).props("dense outlined").classes("w-full")

            ui.label(t("file_dialog.create_hint")).classes(
                "text-xs theme-text-muted"
            )

        # 底部按钮
        with ui.row().classes("w-full justify-end gap-2 pt-2").style("border-top: 1px solid var(--border-color)"):
            ui.button(t("file_dialog.btn_cancel"), on_click=dialog.close).props("flat").classes("theme-text-muted")
            ui.button(
                t("file_dialog.btn_create"),
                on_click=lambda: [
                    on_create(form_data["filename"]),
                    dialog.close(),
                ],
            ).props("color=primary")

    if on_close:
        dialog.on("close", on_close)
    dialog.open()
    return dialog
