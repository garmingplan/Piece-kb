"""
切片操作处理器

职责:
- 切片编辑
- 切片删除
- 切片新增
"""

from nicegui import ui

from indexing.services import chunk_service
from app.i18n import t
from app.ui.components import chunk_edit_dialog, chunk_add_dialog, confirm_dialog


class ChunkHandlers:
    """切片操作处理器"""

    def __init__(self, state: dict, ui_refs: dict, on_task_created: callable, on_refresh_files: callable):
        """
        初始化切片处理器

        Args:
            state: 共享状态字典
            ui_refs: UI 组件引用字典
            on_task_created: 任务创建后的回调
            on_refresh_files: 刷新文件列表的回调
        """
        self.state = state
        self.ui_refs = ui_refs
        self.on_task_created = on_task_created
        self.on_refresh_files = on_refresh_files
        # 批量删除模式状态
        self.state["chunk_batch_mode"] = False
        self.state["chunk_batch_selected_ids"] = set()

    def handle_edit_chunk(self, chunk_id: int):
        """打开编辑切片对话框"""
        chunk = chunk_service.get_chunk_by_id(chunk_id)
        if not chunk:
            ui.notify(t("chunks.not_found"), type="negative")
            return

        chunk_edit_dialog(
            chunk_id=chunk_id,
            doc_title=chunk["doc_title"],
            chunk_text=chunk["chunk_text"],
            on_save=self._save_chunk_edit,
            on_close=lambda: None,
        )

    def _save_chunk_edit(self, chunk_id: int, new_title: str, new_text: str):
        """保存切片编辑"""
        chunk = chunk_service.get_chunk_by_id(chunk_id)
        if not chunk:
            ui.notify(t("chunks.not_found"), type="negative")
            return

        title_changed = new_title != chunk["doc_title"]
        text_changed = new_text != chunk["chunk_text"]

        if not title_changed and not text_changed:
            ui.notify(t("chunks.no_change"), type="info")
            return

        if title_changed:
            chunk_service.update_chunk_title(chunk_id, new_title)

        if text_changed:
            task_id = chunk_service.create_chunk_update_task(chunk_id, new_text)
            ui.notify(t("chunks.update_task_created"), type="positive")
            self.on_task_created(task_id)
        elif title_changed:
            ui.notify(t("chunks.title_updated"), type="positive")

        self._reload_chunks()

    def handle_delete_chunk(self, chunk_id: int):
        """确认删除切片"""
        confirm_dialog(
            title=t("chunks.delete_confirm_title"),
            message=t("chunks.delete_confirm_msg"),
            on_confirm=lambda: self._do_delete_chunk(chunk_id),
            confirm_text=t("confirm_dialog.btn_delete"),
            danger=True,
        )

    def _do_delete_chunk(self, chunk_id: int):
        """执行删除切片"""
        result = chunk_service.delete_chunk(chunk_id)
        if result["success"]:
            if result.get("file_deleted"):
                ui.notify(t("chunks.last_chunk_deleted"), type="positive")
                self.state["selected_file_id"] = None
                self.state["chunks_data"] = []
                self.on_refresh_files()
                if self.ui_refs.get("chunk_inspector"):
                    self.ui_refs["chunk_inspector"].refresh()
            else:
                ui.notify(t("chunks.deleted"), type="positive")
                self._reload_chunks()
        else:
            ui.notify(result.get("error", t("chunks.delete_failed")), type="negative")

    def handle_add_chunk(self):
        """打开新增切片对话框"""
        if self.state["selected_file_id"] is None:
            ui.notify(t("chunks.select_file_first"), type="warning")
            return

        chunk_add_dialog(
            file_id=self.state["selected_file_id"],
            on_save=self._save_new_chunk,
            on_close=lambda: None,
        )

    def _save_new_chunk(self, file_id: int, doc_title: str, chunk_text: str):
        """保存新增切片"""
        if not doc_title.strip() or not chunk_text.strip():
            ui.notify(t("chunks.title_content_required"), type="warning")
            return

        task_id = chunk_service.create_chunk_add_task(
            file_id=file_id,
            doc_title=doc_title.strip(),
            chunk_text=chunk_text.strip(),
        )
        ui.notify(t("chunks.add_task_created"), type="positive")
        self.on_task_created(task_id)
        self.on_refresh_files()

    def _reload_chunks(self):
        """重新加载当前文件的切片"""
        from indexing.services import file_service
        if self.state["selected_file_id"]:
            self.state["chunks_data"] = file_service.get_chunks_by_file_id(
                self.state["selected_file_id"]
            ) or []
            if self.ui_refs.get("chunk_inspector"):
                self.ui_refs["chunk_inspector"].refresh()

    # ==================== 批量删除功能 ====================

    def enter_chunk_batch_mode(self):
        """进入切片批量删除模式"""
        if self.state["selected_file_id"] is None:
            ui.notify(t("chunks.select_file_first"), type="warning")
            return
        self.state["chunk_batch_mode"] = True
        self.state["chunk_batch_selected_ids"] = set()
        if self.ui_refs.get("chunk_toolbar_buttons"):
            self.ui_refs["chunk_toolbar_buttons"].refresh()
        if self.ui_refs.get("chunk_inspector"):
            self.ui_refs["chunk_inspector"].refresh()

    def exit_chunk_batch_mode(self):
        """退出切片批量删除模式"""
        self.state["chunk_batch_mode"] = False
        self.state["chunk_batch_selected_ids"] = set()
        if self.ui_refs.get("chunk_toolbar_buttons"):
            self.ui_refs["chunk_toolbar_buttons"].refresh()
        if self.ui_refs.get("chunk_inspector"):
            self.ui_refs["chunk_inspector"].refresh()

    def toggle_chunk_selection(self, chunk_id: int):
        """切换单个切片的选中状态"""
        if chunk_id in self.state["chunk_batch_selected_ids"]:
            self.state["chunk_batch_selected_ids"].discard(chunk_id)
        else:
            self.state["chunk_batch_selected_ids"].add(chunk_id)
        if self.ui_refs.get("chunk_toolbar_buttons"):
            self.ui_refs["chunk_toolbar_buttons"].refresh()
        if self.ui_refs.get("chunk_inspector"):
            self.ui_refs["chunk_inspector"].refresh()

    def toggle_chunk_select_all(self):
        """全选/取消全选切片"""
        chunk_ids = {c["id"] for c in self.state["chunks_data"]}
        if self.state["chunk_batch_selected_ids"] == chunk_ids:
            self.state["chunk_batch_selected_ids"] = set()
        else:
            self.state["chunk_batch_selected_ids"] = chunk_ids
        if self.ui_refs.get("chunk_toolbar_buttons"):
            self.ui_refs["chunk_toolbar_buttons"].refresh()
        if self.ui_refs.get("chunk_inspector"):
            self.ui_refs["chunk_inspector"].refresh()

    def is_all_chunks_selected(self) -> bool:
        """检查是否全选切片"""
        if not self.state["chunks_data"]:
            return False
        chunk_ids = {c["id"] for c in self.state["chunks_data"]}
        return self.state["chunk_batch_selected_ids"] == chunk_ids

    def confirm_chunk_batch_delete(self):
        """确认批量删除切片"""
        if not self.state["chunk_batch_selected_ids"]:
            ui.notify(t("chunks.batch_none_selected"), type="warning")
            return

        count = len(self.state["chunk_batch_selected_ids"])
        total_chunks = len(self.state["chunks_data"])

        # 如果选中了所有切片，使用删除文件的警告
        if count == total_chunks:
            from indexing.services import file_service
            file_info = file_service.get_file_by_id(self.state["selected_file_id"])
            filename = file_info["filename"] if file_info else ""
            confirm_dialog(
                title=t("files.delete_confirm_title"),
                message=t("files.delete_confirm_msg", filename=filename),
                on_confirm=self._do_chunk_batch_delete,
                confirm_text=t("confirm_dialog.btn_delete"),
                danger=True,
            )
        else:
            confirm_dialog(
                title=t("chunks.batch_delete_confirm_title"),
                message=t("chunks.batch_delete_confirm_msg", count=count),
                on_confirm=self._do_chunk_batch_delete,
                confirm_text=t("confirm_dialog.btn_delete"),
                danger=True,
            )

    def _do_chunk_batch_delete(self):
        """执行批量删除切片"""
        deleted_count = 0
        file_deleted = False
        ids_to_delete = list(self.state["chunk_batch_selected_ids"])

        for chunk_id in ids_to_delete:
            result = chunk_service.delete_chunk(chunk_id)
            if result["success"]:
                deleted_count += 1
                if result.get("file_deleted"):
                    file_deleted = True

        if file_deleted:
            self.state["selected_file_id"] = None
            self.state["chunks_data"] = []
            self.on_refresh_files()

        # 退出批量模式
        self.state["chunk_batch_mode"] = False
        self.state["chunk_batch_selected_ids"] = set()

        if not file_deleted:
            self._reload_chunks()

        if self.ui_refs.get("chunk_toolbar_buttons"):
            self.ui_refs["chunk_toolbar_buttons"].refresh()
        if self.ui_refs.get("chunk_inspector"):
            self.ui_refs["chunk_inspector"].refresh()

        ui.notify(t("chunks.batch_deleted", count=deleted_count), type="positive")
