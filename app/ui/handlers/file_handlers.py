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

    def load_chunks(self, file_id: int):
        """加载选中文件的切片"""
        self.state["selected_file_id"] = file_id
        self.state["chunks_data"] = file_service.get_chunks_by_file_id(file_id) or []

        if self.ui_refs.get("file_list_container"):
            self.ui_refs["file_list_container"].refresh()
        if self.ui_refs.get("chunk_inspector"):
            self.ui_refs["chunk_inspector"].refresh()

    async def handle_upload(self, e: events.UploadEventArguments):
        """
        处理单个文件上传

        批量上传时，每个文件都会触发此回调
        """
        filename = e.file.name
        filename_lower = filename.lower()

        # 检查格式
        if not (filename_lower.endswith(".md") or filename_lower.endswith(".pdf")):
            ui.notify(t("files.upload_only_md"), type="negative")
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

    def _do_batch_delete(self):
        """执行批量删除"""
        deleted_count = 0
        ids_to_delete = list(self.state["batch_selected_ids"])

        for file_id in ids_to_delete:
            success = file_service.delete_file(file_id)
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

    def scan_and_index_new_files(self) -> int:
        """
        扫描物理目录，为云同步下载的新文件创建索引任务

        Returns:
            新创建的任务数量
        """
        untracked_files = file_service.scan_untracked_files()

        if not untracked_files:
            return 0

        task_count = 0
        for file_info in untracked_files:
            # 读取文件内容计算哈希
            file_path = file_info["file_path"]
            try:
                with open(file_path, "rb") as f:
                    content = f.read()
                file_hash = file_service.calculate_file_hash(content)

                # 检查哈希是否已存在（避免重复）
                if file_service.check_file_hash_exists(file_hash):
                    continue

                # 插入文件记录
                file_id = file_service.insert_file_record(
                    file_hash=file_hash,
                    filename=file_info["filename"],
                    file_path=file_path,
                    file_size=file_info["file_size"],
                    status="pending"
                )

                # 创建索引任务
                task_id = task_service.create_task(file_info["filename"])
                task_service.update_task_status(task_id, "pending", file_id=file_id)

                # 通知任务监控
                self.on_task_created(task_id)
                task_count += 1

            except Exception as e:
                # 单个文件失败不影响其他文件
                ui.notify(f"索引失败: {file_info['filename']}: {e}", type="negative")
                continue

        return task_count

    def refresh_and_scan(self):
        """刷新文件列表并扫描新文件"""
        # 先扫描并索引新文件
        new_count = self.scan_and_index_new_files()

        # 刷新文件列表
        self.load_files()

        if new_count > 0:
            ui.notify(t("files.scan_found_new", count=new_count), type="positive")
