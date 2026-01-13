"""
文件操作处理器

职责:
- 文件列表加载和搜索
- 文件上传处理（支持批量）
- 文件删除
- 统计信息加载
"""

from nicegui import ui, events

from indexing.services import file_service, task_service
from indexing.services.chunking import ChunkerFactory
from app.i18n import t
from app.ui.components import confirm_dialog, file_create_dialog
from app.utils import format_size, MAX_FILE_SIZE


class FileHandlers:
    """文件操作处理器"""

    def __init__(self, state: dict, ui_refs: dict, on_task_created: callable):
        """
        初始化文件处理器

        Args:
            state: 共享状态字典，包含 files_data, filtered_files, selected_file_id 等
            ui_refs: UI 组件引用字典
            on_task_created: 任务创建后的回调（用于启动监控）
        """
        self.state = state
        self.ui_refs = ui_refs
        self.on_task_created = on_task_created
        # 批量删除模式状态
        self.state["batch_mode"] = False
        self.state["batch_selected_ids"] = set()

    def load_files(self):
        """加载文件列表"""
        self.state["files_data"] = file_service.get_files_list()
        self.apply_filter()
        self.load_stats()

    def apply_filter(self):
        """应用搜索过滤"""
        keyword = self.state.get("search_keyword", "").strip().lower()
        if keyword:
            self.state["filtered_files"] = [
                f for f in self.state["files_data"]
                if keyword in f["filename"].lower()
            ]
        else:
            self.state["filtered_files"] = self.state["files_data"]

        if self.ui_refs.get("file_list_container"):
            self.ui_refs["file_list_container"].refresh()

    def on_search_change(self, e):
        """搜索框内容变化时触发"""
        self.state["search_keyword"] = e.args
        self.apply_filter()

    def load_stats(self):
        """加载统计信息"""
        stats = file_service.get_storage_stats()
        total = stats["total_files"]
        indexed = stats["indexed_files"]
        size_str = format_size(stats["total_size"])

        if self.ui_refs.get("stats_label"):
            self.ui_refs["stats_label"].set_text(
                t("stats.indexed", size=size_str, indexed=indexed, total=total)
            )
            self.ui_refs["stats_label"].update()

    async def load_chunks(self, file_id: int):
        """加载选中文件的切片（异步 + 后端分页）"""
        import asyncio

        # 1. 立即更新选中状态
        self.state["selected_file_id"] = file_id

        # 2. 清空旧数据，显示加载状态
        self.state["chunks_data"] = []
        self.state["chunk_page"] = 1
        self.state["total_chunks"] = 0
        self.state["total_chunk_pages"] = 1

        # 3. 立即刷新 UI（显示"加载中"）
        if self.ui_refs.get("file_list_container"):
            self.ui_refs["file_list_container"].refresh()
        if self.ui_refs.get("chunk_inspector"):
            self.ui_refs["chunk_inspector"].refresh()

        # 4. 异步加载第一页数据
        result = await asyncio.to_thread(
            file_service.get_chunks_paginated,
            file_id,
            page=1,
            page_size=self.state["chunk_page_size"]
        )

        # 5. 更新状态
        if result:
            self.state["chunks_data"] = result["chunks"]
            self.state["total_chunks"] = result["total"]
            self.state["total_chunk_pages"] = result["total_pages"]
        else:
            self.state["chunks_data"] = []
            self.state["total_chunks"] = 0
            self.state["total_chunk_pages"] = 1

        # 6. 刷新 UI（显示数据）
        if self.ui_refs.get("chunk_inspector"):
            self.ui_refs["chunk_inspector"].refresh()

    async def handle_upload(self, e: events.UploadEventArguments):
        """
        处理单个文件上传

        批量上传时，每个文件都会触发此回调
        """
        filename = e.file.name
        filename_lower = filename.lower()

        # 获取文件扩展名
        file_ext = None
        for ext in [".pptx", ".xlsx", ".docx", ".pdf", ".txt", ".md"]:
            if filename_lower.endswith(ext):
                file_ext = ext
                break

        # 检查格式 - 使用 ChunkerFactory 支持的扩展名
        supported_extensions = ChunkerFactory.get_supported_extensions()
        if file_ext not in supported_extensions:
            supported_str = ", ".join(supported_extensions)
            ui.notify(t("files.upload_unsupported", formats=supported_str), type="negative")
            return

        content = await e.file.read()

        # 检查大小
        if len(content) > MAX_FILE_SIZE:
            size_mb = len(content) / (1024 * 1024)
            ui.notify(t("files.upload_too_large", size=f"{size_mb:.1f}"), type="negative")
            return

        # 检查重复
        file_hash = file_service.calculate_file_hash(content)
        existing_id = file_service.check_file_hash_exists(file_hash)
        if existing_id:
            ui.notify(t("files.upload_exists"), type="warning")
            return

        # 保存文件
        save_result = await file_service.save_file(filename, content)

        file_id = file_service.insert_file_record(
            file_hash=save_result["file_hash"],
            filename=save_result["filename"],
            file_path=save_result["file_path"],
            file_size=save_result["file_size"],
            original_file_type=save_result["original_file_type"],
            original_file_path=save_result["original_file_path"],
            status="pending"
        )

        task_id = task_service.create_task(save_result["filename"])
        task_service.update_task_status(task_id, "pending", file_id=file_id)

        ui.notify(t("files.upload_processing"), type="positive")
        self.load_files()
        self.load_stats()
        self.on_task_created(task_id)

    def on_upload_rejected(self, e):
        """处理被拒绝的文件（格式不符）"""
        ui.notify(t("files.upload_only_md"), type="negative")

    def delete_selected_file(self):
        """删除选中的文件"""
        if self.state["selected_file_id"] is None:
            ui.notify(t("files.select_first"), type="warning")
            return

        file_info = file_service.get_file_by_id(self.state["selected_file_id"])
        filename = file_info["filename"] if file_info else ""

        confirm_dialog(
            title=t("files.delete_confirm_title"),
            message=t("files.delete_confirm_msg", filename=filename),
            on_confirm=self._do_delete_file,
            confirm_text=t("confirm_dialog.btn_delete"),
            danger=True,
        )

    def _do_delete_file(self):
        """执行删除文件"""
        success = file_service.delete_file(self.state["selected_file_id"])
        if success:
            ui.notify(t("files.deleted"), type="positive")
            self.state["selected_file_id"] = None
            self.state["chunks_data"] = []
            self.load_files()
            self.load_stats()
            if self.ui_refs.get("chunk_inspector"):
                self.ui_refs["chunk_inspector"].refresh()
        else:
            ui.notify(t("files.delete_failed"), type="negative")

    def handle_create_file(self):
        """处理新建文件"""
        file_create_dialog(
            on_create=self._do_create_file,
        )

    def _do_create_file(self, filename: str):
        """执行创建文件"""
        if not filename or not filename.strip():
            ui.notify(t("files.create_name_empty"), type="warning")
            return

        try:
            result = file_service.create_empty_file(filename)
            ui.notify(t("files.created", filename=result["filename"]), type="positive")

            # 刷新文件列表
            self.load_files()
            self.load_stats()

            # 自动选中新创建的文件
            self.load_chunks(result["file_id"])

        except ValueError as e:
            ui.notify(str(e), type="negative")
        except Exception as e:
            ui.notify(t("files.create_failed", error=str(e)), type="negative")

    # ==================== 批量删除功能 ====================

    def enter_batch_mode(self):
        """进入批量删除模式"""
        self.state["batch_mode"] = True
        self.state["batch_selected_ids"] = set()
        if self.ui_refs.get("toolbar_buttons"):
            self.ui_refs["toolbar_buttons"].refresh()
        if self.ui_refs.get("file_list_container"):
            self.ui_refs["file_list_container"].refresh()

    def exit_batch_mode(self):
        """退出批量删除模式"""
        self.state["batch_mode"] = False
        self.state["batch_selected_ids"] = set()
        if self.ui_refs.get("toolbar_buttons"):
            self.ui_refs["toolbar_buttons"].refresh()
        if self.ui_refs.get("file_list_container"):
            self.ui_refs["file_list_container"].refresh()

    def toggle_file_selection(self, file_id: int):
        """切换单个文件的选中状态"""
        if file_id in self.state["batch_selected_ids"]:
            self.state["batch_selected_ids"].discard(file_id)
        else:
            self.state["batch_selected_ids"].add(file_id)
        if self.ui_refs.get("toolbar_buttons"):
            self.ui_refs["toolbar_buttons"].refresh()
        if self.ui_refs.get("file_list_container"):
            self.ui_refs["file_list_container"].refresh()

    def toggle_select_all(self):
        """全选/取消全选"""
        filtered_ids = {f["id"] for f in self.state["filtered_files"]}
        if self.state["batch_selected_ids"] == filtered_ids:
            # 已全选，取消全选
            self.state["batch_selected_ids"] = set()
        else:
            # 未全选，执行全选
            self.state["batch_selected_ids"] = filtered_ids
        if self.ui_refs.get("toolbar_buttons"):
            self.ui_refs["toolbar_buttons"].refresh()
        if self.ui_refs.get("file_list_container"):
            self.ui_refs["file_list_container"].refresh()

    def is_all_selected(self) -> bool:
        """检查是否全选"""
        if not self.state["filtered_files"]:
            return False
        filtered_ids = {f["id"] for f in self.state["filtered_files"]}
        return self.state["batch_selected_ids"] == filtered_ids

    def confirm_batch_delete(self):
        """确认批量删除"""
        if not self.state["batch_selected_ids"]:
            ui.notify(t("files.batch_none_selected"), type="warning")
            return

        count = len(self.state["batch_selected_ids"])
        confirm_dialog(
            title=t("files.batch_delete_confirm_title"),
            message=t("files.batch_delete_confirm_msg", count=count),
            on_confirm=self._do_batch_delete,
            confirm_text=t("confirm_dialog.btn_delete"),
            danger=True,
        )

    async def _do_batch_delete(self):
        """执行批量删除（异步优化，避免阻塞界面）"""
        import asyncio

        deleted_count = 0
        ids_to_delete = list(self.state["batch_selected_ids"])

        # 异步批量删除，避免阻塞界面
        for file_id in ids_to_delete:
            success = await asyncio.to_thread(file_service.delete_file, file_id)
            if success:
                deleted_count += 1

        # 如果当前选中的文件被删除了，清空右栏
        if self.state["selected_file_id"] in ids_to_delete:
            self.state["selected_file_id"] = None
            self.state["chunks_data"] = []
            if self.ui_refs.get("chunk_inspector"):
                self.ui_refs["chunk_inspector"].refresh()

        # 退出批量模式并刷新
        self.exit_batch_mode()
        self.load_files()
        self.load_stats()

        ui.notify(t("files.batch_deleted", count=deleted_count), type="positive")

    # ==================== 扫描并索引新文件 ====================

    async def scan_and_index_new_files(self) -> int:
        """
        扫描物理目录，为云同步下载的新文件创建索引任务（异步优化，避免阻塞界面）

        扫描 originals/ 目录，为每个未被跟踪的原始文件：
        1. 异步读取原始文件计算哈希
        2. 创建对应的工作文件（初始为空）
        3. 写入数据库记录（包含双文件信息）
        4. 创建索引任务（由 processor 转换并填充工作文件）

        Returns:
            新创建的任务数量
        """
        import logging
        import asyncio
        import aiofiles
        from pathlib import Path

        logger = logging.getLogger(__name__)

        # 异步扫描未跟踪文件
        untracked_files = await asyncio.to_thread(file_service.scan_untracked_files)

        if not untracked_files:
            return 0

        task_count = 0
        for file_info in untracked_files:
            # 读取原始文件内容计算哈希
            original_file_path = file_info["original_file_path"]
            try:
                # 异步读取文件（避免阻塞界面）
                async with aiofiles.open(original_file_path, "rb") as f:
                    content = await f.read()

                # 在线程池中计算哈希（CPU 密集型操作）
                file_hash = await asyncio.to_thread(
                    file_service.calculate_file_hash, content
                )

                # 检查哈希是否已存在（避免重复）
                existing_id = await asyncio.to_thread(
                    file_service.check_file_hash_exists, file_hash
                )
                if existing_id:
                    logger.info(f"[Scan] 跳过已存在文件: {file_info['original_filename']}")
                    continue

                # 创建空的工作文件（如果不存在）
                working_file_path = Path(file_info["working_file_path"])
                if not working_file_path.exists():
                    working_file_path.parent.mkdir(parents=True, exist_ok=True)
                    async with aiofiles.open(working_file_path, "wb") as f:
                        await f.write(b"")
                    logger.info(f"[Scan] 创建工作文件: {working_file_path}")

                # 插入文件记录（包含完整的双文件信息）
                file_id = await asyncio.to_thread(
                    file_service.insert_file_record,
                    file_hash=file_hash,
                    filename=file_info["working_filename"],              # 工作文件名（.md）
                    file_path=file_info["working_file_path"],            # 工作文件路径
                    file_size=file_info["original_file_size"],           # 原始文件大小
                    original_file_type=file_info["original_file_type"],  # 原始文件类型（不带点号）
                    original_file_path=file_info["original_file_path"],  # 原始文件路径
                    status="pending"
                )

                # 创建索引任务
                task_id = await asyncio.to_thread(
                    task_service.create_task, file_info["original_filename"]
                )
                await asyncio.to_thread(
                    task_service.update_task_status, task_id, "pending", file_id=file_id
                )

                # 通知任务监控
                self.on_task_created(task_id)
                task_count += 1

                logger.info(f"[Scan] 成功创建索引任务: {file_info['original_filename']}")

            except Exception as e:
                # 单个文件失败不影响其他文件
                logger.error(f"[Scan] 索引失败: {file_info['original_filename']}: {e}", exc_info=True)
                ui.notify(f"索引失败: {file_info['original_filename']}: {e}", type="negative")
                continue

        return task_count

    async def refresh_and_scan(self):
        """刷新文件列表并扫描新文件（异步优化）"""
        # 先扫描并索引新文件（异步）
        new_count = await self.scan_and_index_new_files()

        # 刷新文件列表
        self.load_files()

        if new_count > 0:
            ui.notify(t("files.scan_found_new", count=new_count), type="positive")
