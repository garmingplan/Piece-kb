"""
异步任务监控处理器

职责:
- 管理待处理任务列表
- 定期检查任务状态
- 任务完成后刷新 UI
"""

from nicegui import ui

from indexing.services import task_service, file_service
from app.i18n import t
from app.utils import format_size


class TaskHandlers:
    """异步任务监控处理器"""

    def __init__(self, state: dict, ui_refs: dict, file_handlers=None):
        """
        初始化任务处理器

        Args:
            state: 共享状态字典
            ui_refs: UI 组件引用字典
            file_handlers: 文件处理器实例（用于复用 apply_filter）
        """
        self.state = state
        self.ui_refs = ui_refs
        self.file_handlers = file_handlers
        self.pending_tasks = []
        # 任务进度缓存 {task_id: {"file_id": int, "filename": str, "progress": int, "status": str}}
        self.state["task_progress"] = {}

    def init_active_tasks(self):
        """
        初始化活跃任务（页面加载时调用）

        恢复所有进行中的任务到监控列表
        """
        active_tasks = task_service.get_active_tasks()
        for task in active_tasks:
            task_id = task["id"]
            if task_id not in self.pending_tasks:
                self.pending_tasks.append(task_id)
                self.state["task_progress"][task_id] = {
                    "file_id": task.get("file_id"),
                    "filename": task.get("original_filename", ""),
                    "progress": task.get("progress", 0),
                    "status": task.get("status", "pending"),
                }

        # 如果有活跃任务，刷新文件列表
        if active_tasks and self.ui_refs.get("file_list_container"):
            self.ui_refs["file_list_container"].refresh()

    def set_file_handlers(self, file_handlers):
        """设置文件处理器引用（用于解决循环依赖）"""
        self.file_handlers = file_handlers

    def add_task(self, task_id: int):
        """添加任务到监控列表"""
        self.pending_tasks.append(task_id)
        # 初始化进度信息
        task = task_service.get_task(task_id)
        if task:
            self.state["task_progress"][task_id] = {
                "file_id": task.get("file_id"),  # 使用 file_id 而不是 filename
                "filename": task.get("original_filename", ""),
                "progress": task.get("progress", 0),
                "status": task.get("status", "pending"),
            }
            # 刷新文件列表以显示进度
            if self.ui_refs.get("file_list_container"):
                self.ui_refs["file_list_container"].refresh()

    async def check_pending_tasks(self):
        """检查所有待处理任务的状态（异步优化，避免阻塞界面）"""
        if not self.pending_tasks:
            return

        import asyncio

        completed_tasks = []
        progress_updated = False

        for task_id in self.pending_tasks:
            # 异步查询任务状态，避免阻塞界面
            task = await asyncio.to_thread(task_service.get_task, task_id)
            if not task:
                completed_tasks.append(task_id)
                if task_id in self.state["task_progress"]:
                    del self.state["task_progress"][task_id]
                continue

            status = task["status"]
            progress = task.get("progress", 0)

            # 更新进度缓存
            if task_id in self.state["task_progress"]:
                old_progress = self.state["task_progress"][task_id]["progress"]
                if progress != old_progress:
                    self.state["task_progress"][task_id]["progress"] = progress
                    self.state["task_progress"][task_id]["status"] = status
                    progress_updated = True
            else:
                # 如果缓存中没有，添加进去（处理页面刷新等情况）
                self.state["task_progress"][task_id] = {
                    "file_id": task.get("file_id"),
                    "filename": task.get("original_filename", ""),
                    "progress": progress,
                    "status": status,
                }
                progress_updated = True

            if status == "completed":
                completed_tasks.append(task_id)
                if task_id in self.state["task_progress"]:
                    del self.state["task_progress"][task_id]
                ui.notify(t("task.completed"), type="positive")
                await self._refresh_all_async()
            elif status == "failed":
                completed_tasks.append(task_id)
                if task_id in self.state["task_progress"]:
                    del self.state["task_progress"][task_id]
                error_msg = task.get("error_message", "")
                if error_msg and not error_msg.startswith("CHUNK_"):
                    ui.notify(f"{t('task.failed')}: {error_msg}", type="negative")
                else:
                    ui.notify(t("task.failed"), type="negative")

        for task_id in completed_tasks:
            self.pending_tasks.remove(task_id)

        # 如果有进度更新，刷新文件列表
        if progress_updated and self.ui_refs.get("file_list_container"):
            self.ui_refs["file_list_container"].refresh()

    async def _refresh_all_async(self):
        """刷新所有数据和 UI（异步优化，避免阻塞界面）"""
        import asyncio

        # 异步获取文件列表
        self.state["files_data"] = await asyncio.to_thread(file_service.get_files_list)

        # 复用 file_handlers 的过滤逻辑
        if self.file_handlers:
            self.file_handlers.apply_filter()
        else:
            # 降级处理：直接应用过滤
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

        # 异步刷新统计信息
        if self.ui_refs.get("stats_label"):
            stats = await asyncio.to_thread(file_service.get_storage_stats)
            total = stats["total_files"]
            indexed = stats["indexed_files"]
            size_str = format_size(stats["total_size"])

            self.ui_refs["stats_label"].set_text(
                t("stats.indexed", size=size_str, indexed=indexed, total=total)
            )
            self.ui_refs["stats_label"].update()

        # 异步刷新切片
        if self.state.get("selected_file_id"):
            self.state["chunks_data"] = await asyncio.to_thread(
                file_service.get_chunks_by_file_id,
                self.state["selected_file_id"]
            ) or []
            if self.ui_refs.get("chunk_inspector"):
                self.ui_refs["chunk_inspector"].refresh()

    def _refresh_all(self):
        """刷新所有数据和 UI（同步版本，保持向后兼容）"""
        self.state["files_data"] = file_service.get_files_list()

        # 复用 file_handlers 的过滤逻辑
        if self.file_handlers:
            self.file_handlers.apply_filter()
        else:
            # 降级处理：直接应用过滤
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

        # 刷新统计信息
        if self.ui_refs.get("stats_label"):
            stats = file_service.get_storage_stats()
            total = stats["total_files"]
            indexed = stats["indexed_files"]
            size_str = format_size(stats["total_size"])

            self.ui_refs["stats_label"].set_text(
                t("stats.indexed", size=size_str, indexed=indexed, total=total)
            )
            self.ui_refs["stats_label"].update()

        # 刷新切片
        if self.state.get("selected_file_id"):
            self.state["chunks_data"] = file_service.get_chunks_by_file_id(
                self.state["selected_file_id"]
            ) or []
            if self.ui_refs.get("chunk_inspector"):
                self.ui_refs["chunk_inspector"].refresh()
