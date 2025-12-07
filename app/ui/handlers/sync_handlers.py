"""
云同步操作处理器

职责:
- 处理同步操作
- 管理同步状态和日志
"""

from datetime import datetime
from nicegui import ui

from indexing.services.sync_service import get_sync_service
from app.i18n import t


def safe_notify(message: str, type: str = "info"):
    """安全的通知函数，忽略 UI 上下文错误"""
    try:
        ui.notify(message, type=type)
    except RuntimeError:
        # 页面已切换，忽略通知
        pass


class SyncHandlers:
    """云同步操作处理器"""

    def __init__(self, sync_state: dict, ui_refs: dict, on_pull_complete: callable = None):
        """
        初始化同步处理器

        Args:
            sync_state: 同步状态字典
            ui_refs: UI 组件引用字典
            on_pull_complete: sync 完成后的回调（用于触发文件扫描和索引）
        """
        self.sync_state = sync_state
        self.ui_refs = ui_refs
        self.sync_service = get_sync_service()
        self.on_pull_complete = on_pull_complete

    def is_enabled(self) -> bool:
        """检查云同步是否启用"""
        return self.sync_service.is_enabled()

    def _add_log(self, log_type: str, message: str):
        """添加日志"""
        if "logs" not in self.sync_state:
            self.sync_state["logs"] = []

        self.sync_state["logs"].append({
            "type": log_type,
            "message": message,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
        })

        # 限制日志数量
        if len(self.sync_state["logs"]) > 100:
            self.sync_state["logs"] = self.sync_state["logs"][-100:]

        # 刷新日志显示
        try:
            if self.ui_refs.get("sync_logs"):
                self.ui_refs["sync_logs"].refresh()
        except RuntimeError:
            pass

    def _update_sync_state(self, is_syncing: bool = None, last_sync: str = None):
        """更新同步状态"""
        if is_syncing is not None:
            self.sync_state["is_syncing"] = is_syncing
        if last_sync is not None:
            self.sync_state["last_sync"] = last_sync

        # 刷新 UI
        try:
            if self.ui_refs.get("sync_buttons"):
                self.ui_refs["sync_buttons"].refresh()
            if self.ui_refs.get("last_sync_info"):
                self.ui_refs["last_sync_info"].refresh()
        except RuntimeError:
            pass

    async def do_sync(self):
        """执行智能同步（首次同步 or 日常同步）"""
        if not self.is_enabled():
            safe_notify(t("cloud_sync.not_configured"), type="warning")
            return

        if self.sync_state.get("is_syncing"):
            safe_notify(t("cloud_sync.already_syncing"), type="warning")
            return

        self._update_sync_state(is_syncing=True)
        self._add_log("info", t("cloud_sync.sync_started"))

        try:
            import asyncio

            def progress_callback(current, total, filename):
                self._add_log("info", f"[{current}/{total}] {filename}")

            result = await asyncio.to_thread(
                self.sync_service.sync,
                progress_callback
            )

            if result.success:
                self._add_log("success", result.message)
                safe_notify(result.message, type="positive")

                # 记录详情
                for f in result.uploaded:
                    self._add_log("upload", f"↑ {f}")
                for f in result.downloaded:
                    self._add_log("download", f"↓ {f}")
            else:
                self._add_log("error", result.message)
                safe_notify(result.message, type="negative")

            # 记录错误
            for err in result.errors:
                self._add_log("error", err)

        except Exception as e:
            self._add_log("error", str(e))
            safe_notify(str(e), type="negative")

        finally:
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            self._update_sync_state(is_syncing=False, last_sync=now)

            # 同步完成后触发文件扫描和索引
            if self.on_pull_complete:
                self.on_pull_complete()
