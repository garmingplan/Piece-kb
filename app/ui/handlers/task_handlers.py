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

    def set_file_handlers(self, file_handlers):
        """设置文件处理器引用（用于解决循环依赖）"""
        self.file_handlers = file_handlers

    def add_task(self, task_id: int):
        """添加任务到监控列表"""
        self.pending_tasks.append(task_id)

    def check_pending_tasks(self):
        """检查所有待处理任务的状态"""
        if not self.pending_tasks:
            return

        completed_tasks = []
        for task_id in self.pending_tasks:
            task = task_service.get_task(task_id)
            if not task:
                completed_tasks.append(task_id)
                continue

            status = task["status"]
            if status == "completed":
                completed_tasks.append(task_id)
                ui.notify(t("task.completed"), type="positive")
                self._refresh_all()
            elif status == "failed":
                completed_tasks.append(task_id)
                error_msg = task.get("error_message", "")
                if error_msg and not error_msg.startswith("CHUNK_"):
                    ui.notify(f"{t('task.failed')}: {error_msg}", type="negative")
                else:
                    ui.notify(t("task.failed"), type="negative")

        for task_id in completed_tasks:
            self.pending_tasks.remove(task_id)

    def _refresh_all(self):
        """刷新所有数据和 UI"""
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
