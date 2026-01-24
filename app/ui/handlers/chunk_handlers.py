"""
切片操作处理器

职责:
- 切片编辑
- 切片删除
- 切片新增
"""

import asyncio

from nicegui import ui

from indexing.services import chunk_service, file_service
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

    async def handle_edit_chunk(self, chunk_id: int):
        """打开编辑切片对话框"""
        chunk = await asyncio.to_thread(chunk_service.get_chunk_by_id, chunk_id)
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

    async def _save_chunk_edit(self, chunk_id: int, new_title: str, new_text: str):
        """保存切片编辑"""
        chunk = await asyncio.to_thread(chunk_service.get_chunk_by_id, chunk_id)
        if not chunk:
            ui.notify(t("chunks.not_found"), type="negative")
            return

        title_changed = new_title != chunk["doc_title"]
        text_changed = new_text != chunk["chunk_text"]

        if not title_changed and not text_changed:
            ui.notify(t("chunks.no_change"), type="info")
            return

        if title_changed:
            await asyncio.to_thread(chunk_service.update_chunk_title, chunk_id, new_title)

        if text_changed:
            task_id = await asyncio.to_thread(
                chunk_service.create_chunk_update_task, chunk_id, new_text
            )
            ui.notify(t("chunks.update_task_created"), type="positive")
            self.on_task_created(task_id)
        elif title_changed:
            ui.notify(t("chunks.title_updated"), type="positive")

        await self._reload_chunks()

    def handle_delete_chunk(self, chunk_id: int):
        """确认删除切片"""
        confirm_dialog(
            title=t("chunks.delete_confirm_title"),
            message=t("chunks.delete_confirm_msg"),
            on_confirm=lambda: self._do_delete_chunk(chunk_id),
            confirm_text=t("confirm_dialog.btn_delete"),
            danger=True,
        )

    async def _do_delete_chunk(self, chunk_id: int):
        """执行删除切片"""
        result = await asyncio.to_thread(chunk_service.delete_chunk, chunk_id)
        if result["success"]:
            if result.get("file_deleted"):
                ui.notify(t("chunks.last_chunk_deleted"), type="positive")
                self.state["selected_file_id"] = None
                self.state["chunks_data"] = []
                await self.on_refresh_files()
                if self.ui_refs.get("chunk_inspector"):
                    self.ui_refs["chunk_inspector"].refresh()
            else:
                ui.notify(t("chunks.deleted"), type="positive")
                await self._reload_chunks()
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

    async def _save_new_chunk(self, file_id: int, doc_title: str, chunk_text: str):
        """保存新增切片"""
        if not doc_title.strip() or not chunk_text.strip():
            ui.notify(t("chunks.title_content_required"), type="warning")
            return

        task_id = await asyncio.to_thread(
            chunk_service.create_chunk_add_task,
            file_id=file_id,
            doc_title=doc_title.strip(),
            chunk_text=chunk_text.strip(),
        )
        ui.notify(t("chunks.add_task_created"), type="positive")
        self.on_task_created(task_id)
        await self.on_refresh_files()

    async def _reload_chunks(self):
        """重新加载当前文件的切片（异步 + 后端分页）"""
        if self.state["selected_file_id"]:
            # 异步加载第一页数据
            result = await asyncio.to_thread(
                file_service.get_chunks_paginated,
                self.state["selected_file_id"],
                page=1,
                page_size=self.state["chunk_page_size"]
            )

            # 更新状态
            if result:
                self.state["chunks_data"] = result["chunks"]
                self.state["total_chunks"] = result["total"]
                self.state["total_chunk_pages"] = result["total_pages"]
            else:
                self.state["chunks_data"] = []
                self.state["total_chunks"] = 0
                self.state["total_chunk_pages"] = 1

            # 重置分页到第一页
            self.state["chunk_page"] = 1

            if self.ui_refs.get("chunk_inspector"):
                self.ui_refs["chunk_inspector"].refresh()

    # ==================== 分页功能 ====================

    async def go_to_chunk_page(self, page: int):
        """跳转到指定页（异步加载）"""
        total_pages = self.get_total_chunk_pages()
        if page < 1:
            page = 1
        elif page > total_pages:
            page = total_pages

        # 更新页码
        self.state["chunk_page"] = page

        # 清空数据，显示加载状态
        self.state["chunks_data"] = []
        if self.ui_refs.get("chunk_inspector"):
            self.ui_refs["chunk_inspector"].refresh()

        # 异步加载新页数据
        result = await asyncio.to_thread(
            file_service.get_chunks_paginated,
            self.state["selected_file_id"],
            page=page,
            page_size=self.state["chunk_page_size"]
        )

        # 更新数据
        if result:
            self.state["chunks_data"] = result["chunks"]
        else:
            self.state["chunks_data"] = []

        # 刷新 UI
        if self.ui_refs.get("chunk_inspector"):
            self.ui_refs["chunk_inspector"].refresh()

    async def prev_chunk_page(self):
        """上一页（异步加载）"""
        if self.state["chunk_page"] > 1:
            await self.go_to_chunk_page(self.state["chunk_page"] - 1)

    async def next_chunk_page(self):
        """下一页（异步加载）"""
        total_pages = self.get_total_chunk_pages()
        if self.state["chunk_page"] < total_pages:
            await self.go_to_chunk_page(self.state["chunk_page"] + 1)

    def get_total_chunk_pages(self) -> int:
        """获取总页数（从状态中读取）"""
        return self.state.get("total_chunk_pages", 1)

    def get_visible_chunks(self) -> list:
        """获取当前页可见的切片（后端分页，直接返回）"""
        return self.state["chunks_data"]

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
        """全选/取消全选切片（仅当前页）"""
        visible_chunks = self.get_visible_chunks()
        visible_chunk_ids = {c["id"] for c in visible_chunks}
        if visible_chunk_ids.issubset(self.state["chunk_batch_selected_ids"]):
            # 当前页全部选中，取消选中
            self.state["chunk_batch_selected_ids"] -= visible_chunk_ids
        else:
            # 选中当前页所有切片
            self.state["chunk_batch_selected_ids"] |= visible_chunk_ids
        if self.ui_refs.get("chunk_toolbar_buttons"):
            self.ui_refs["chunk_toolbar_buttons"].refresh()
        if self.ui_refs.get("chunk_inspector"):
            self.ui_refs["chunk_inspector"].refresh()

    def is_all_chunks_selected(self) -> bool:
        """检查当前页是否全选"""
        visible_chunks = self.get_visible_chunks()
        if not visible_chunks:
            return False
        visible_chunk_ids = {c["id"] for c in visible_chunks}
        return visible_chunk_ids.issubset(self.state["chunk_batch_selected_ids"])

    async def confirm_chunk_batch_delete(self):
        """确认批量删除切片"""
        if not self.state["chunk_batch_selected_ids"]:
            ui.notify(t("chunks.batch_none_selected"), type="warning")
            return

        count = len(self.state["chunk_batch_selected_ids"])
        total_chunks = self.state.get("total_chunks", len(self.state["chunks_data"]))

        # 如果选中了所有切片，使用删除文件的警告
        if count >= total_chunks:
            file_info = await asyncio.to_thread(
                file_service.get_file_by_id, self.state["selected_file_id"]
            )
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

    async def _do_chunk_batch_delete(self):
        """执行批量删除切片"""
        ids_to_delete = list(self.state["chunk_batch_selected_ids"])

        # 使用批量删除服务（一次性处理，避免循环阻塞）
        result = await asyncio.to_thread(
            chunk_service.batch_delete_chunks, ids_to_delete
        )

        deleted_count = result["deleted_count"]
        file_deleted = len(result["deleted_files"]) > 0

        if file_deleted:
            self.state["selected_file_id"] = None
            self.state["chunks_data"] = []
            await self.on_refresh_files()

        # 退出批量模式
        self.state["chunk_batch_mode"] = False
        self.state["chunk_batch_selected_ids"] = set()

        if not file_deleted:
            await self._reload_chunks()

        if self.ui_refs.get("chunk_toolbar_buttons"):
            self.ui_refs["chunk_toolbar_buttons"].refresh()
        if self.ui_refs.get("chunk_inspector"):
            self.ui_refs["chunk_inspector"].refresh()

        ui.notify(t("chunks.batch_deleted", count=deleted_count), type="positive")
