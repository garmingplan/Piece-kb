"""
WebDAV 云同步服务模块

职责:
- 封装 WebDAV 客户端操作
- 实现文件上传/下载/双向同步
- 管理同步状态

同步内容:
- data/files/originals/ - 原始文件备份
- data/files/working/ - 工作文件

同步策略:
1. 首次同步（last_sync_time 为空）
   - 云端有文件 → 下载到本地（保护本地文件，不覆盖）
   - 本地有文件但云端没有 → 上传到云端（初始化云端）
   - 双方都有 → 跳过（保护数据）

2. 日常同步（已有同步记录）- 严格以本地为主
   - 本地有，云端没有 → 上传到云端
   - 本地没有，云端有 → 删除云端文件（同步本地的删除操作）
   - 本地和云端大小不同 → 以本地为准，上传覆盖云端
   - 大小相同 → 跳过

注意事项:
- config.json 不参与云同步（包含敏感信息）
- last_sync_time 记录在 config.json 中，用于判断是否首次同步
- 日常同步严格以本地为主，本地删除的文件会同步删除云端文件

实现说明:
- 使用 webdav4 库（比 webdavclient3 更现代、兼容性更好）
"""

import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable, Dict
from dataclasses import dataclass, field

from webdav4.client import Client as WebDAV4Client

from indexing.settings import get_settings, get_webdav_config, save_settings

logger = logging.getLogger(__name__)


@dataclass
class SyncStatus:
    """同步状态"""
    is_syncing: bool = False
    last_sync_time: Optional[datetime] = None
    last_error: Optional[str] = None
    uploaded_count: int = 0
    downloaded_count: int = 0
    skipped_count: int = 0


@dataclass
class SyncResult:
    """同步结果"""
    success: bool
    uploaded: list = field(default_factory=list)
    downloaded: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    message: str = ""


class SyncService:
    """WebDAV 云同步服务"""

    def __init__(self):
        self.status = SyncStatus()
        self._progress_callback: Optional[Callable] = None

    def _get_client(self) -> Optional[WebDAV4Client]:
        """获取 WebDAV 客户端"""
        settings = get_settings()
        webdav = settings.webdav

        if not webdav.enabled:
            return None

        if not webdav.hostname or not webdav.username or not webdav.password:
            return None

        # webdav4 使用 auth 元组
        return WebDAV4Client(
            webdav.hostname,
            auth=(webdav.username, webdav.password),
            timeout=60.0  # 设置超时时间
        )

    def _get_local_paths(self) -> dict:
        """获取本地同步目录"""
        settings = get_settings()
        data_path = settings.get_data_path()

        files_root = data_path / "files"
        return {
            "originals": files_root / "originals",
            "working": files_root / "working",
        }

    def is_enabled(self) -> bool:
        """检查云同步是否启用"""
        settings = get_settings()
        return settings.webdav.enabled and bool(settings.webdav.hostname)

    def is_first_sync(self) -> bool:
        """判断是否首次同步"""
        settings = get_settings()
        return settings.webdav.last_sync_time is None

    def _update_last_sync_time(self):
        """更新上次同步时间到配置文件"""
        try:
            settings = get_settings()
            sync_time = datetime.now().isoformat()
            settings.webdav.last_sync_time = sync_time

            if save_settings(settings):
                logger.info(f"[Sync] 已更新 last_sync_time: {sync_time}")
            else:
                logger.error("[Sync] 保存 last_sync_time 失败")
        except Exception as e:
            logger.error(f"[Sync] 更新 last_sync_time 时出错: {e}", exc_info=True)

    def check_connection(self) -> tuple[bool, str]:
        """检查 WebDAV 连接"""
        try:
            client = self._get_client()
            if not client:
                return False, "云同步未启用或配置不完整"

            # 使用 webdav4 的 exists 方法检查连接
            if client.exists("/"):
                return True, "连接成功"
            else:
                return False, "路径不存在，请检查服务器地址"

        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg:
                return False, "认证失败，请检查用户名和密码"
            elif "404" in error_msg:
                return False, "路径不存在，请检查服务器地址"
            elif "connect" in error_msg.lower():
                return False, "无法连接到服务器"
            else:
                return False, f"连接失败: {error_msg}"

    def _ensure_remote_dir(self, client: WebDAV4Client, path: str):
        """确保远程目录存在（递归创建）"""
        if not path:
            return

        parts = path.strip("/").split("/")
        current = ""
        for part in parts:
            current = f"{current}/{part}" if current else part
            try:
                if not client.exists(current):
                    client.mkdir(current)
                    logger.info(f"[Sync] 创建远程目录: {current}")
            except Exception as e:
                # 可能是已存在的错误，记录但继续
                logger.debug(f"[Sync] 创建目录 {current} 时出错（可能已存在）: {e}")

    def _ensure_remote_dirs(self, client: WebDAV4Client):
        """确保所有需要的远程目录存在"""
        self._ensure_remote_dir(client, "originals")
        self._ensure_remote_dir(client, "working")

    def _get_local_files(self, local_dir: Path) -> Dict[str, int]:
        """获取本地文件列表及其大小"""
        files = {}
        if not local_dir.exists():
            logger.warning(f"[Sync] 本地目录不存在: {local_dir}")
            return files

        logger.debug(f"[Sync] 开始扫描本地目录: {local_dir}")
        for file_path in local_dir.rglob("*"):
            if file_path.is_file():
                rel_path = file_path.relative_to(local_dir)
                size = file_path.stat().st_size
                files[str(rel_path)] = size
                logger.debug(f"[Sync] 发现本地文件: {rel_path} ({size} 字节)")

        logger.info(f"[Sync] 本地目录 {local_dir} 共有 {len(files)} 个文件")
        return files

    def _get_remote_files(self, client: WebDAV4Client, remote_dir: str) -> Dict[str, int]:
        """获取远程文件列表及其大小"""
        files = {}
        try:
            if not client.exists(remote_dir):
                logger.warning(f"[Sync] 远程目录不存在: {remote_dir}")
                return files

            logger.debug(f"[Sync] 开始获取远程文件列表: {remote_dir}")
            items = client.ls(remote_dir, detail=True)
            logger.debug(f"[Sync] client.ls() 返回 {len(items)} 项")

            for item in items:
                logger.debug(f"[Sync] 检查项目: {item}")

                # 跳过目录（webdav4 中目录的 type 可能是 "directory" 或 None，且 name 以 / 结尾）
                item_type = item.get("type")
                item_name = item.get("name", "")

                # 判断是否为目录：type 为 directory 或 name 以 / 结尾
                if item_type == "directory" or item_name.endswith("/"):
                    logger.debug(f"[Sync] 跳过目录: {item_name}")
                    continue

                # 使用 display_name 获取纯文件名，或从 name 中提取
                filename = item.get("display_name") or ""
                if not filename:
                    name = item.get("name", "")
                    filename = name.split("/")[-1] if "/" in name else name
                if not filename:
                    continue

                # 获取文件大小
                size = item.get("content_length", 0) or 0

                files[filename] = size
                logger.debug(f"[Sync] 发现远程文件: {filename} ({size} 字节)")

        except Exception as e:
            logger.error(f"[Sync] 获取远程文件列表失败 {remote_dir}: {e}", exc_info=True)

        logger.info(f"[Sync] 远程目录 {remote_dir} 共有 {len(files)} 个文件")
        return files

    def sync(self, progress_callback: Optional[Callable] = None) -> SyncResult:
        """双向同步"""
        result = SyncResult(success=True)

        if self.status.is_syncing:
            result.success = False
            result.message = "同步正在进行中"
            return result

        self.status.is_syncing = True
        self.status.last_error = None

        try:
            client = self._get_client()
            if not client:
                result.success = False
                result.message = "云同步未启用"
                return result

            local_paths = self._get_local_paths()

            # 确保远程目录存在
            self._ensure_remote_dirs(client)

            # 双向同步 originals 目录
            self._sync_directory(
                client, local_paths["originals"], "originals",
                result, progress_callback
            )

            # 双向同步 working 目录
            self._sync_directory(
                client, local_paths["working"], "working",
                result, progress_callback
            )

            self.status.last_sync_time = datetime.now()
            self.status.uploaded_count = len(result.uploaded)
            self.status.downloaded_count = len(result.downloaded)
            self.status.skipped_count = len(result.skipped)

            # 更新配置文件中的同步时间
            self._update_last_sync_time()

            result.message = f"同步完成: ↑{len(result.uploaded)} ↓{len(result.downloaded)}"
            logger.info(f"[Sync] 同步完成: {result.message}")

        except Exception as e:
            result.success = False
            result.message = str(e)
            self.status.last_error = str(e)
            logger.error(f"[Sync] 同步失败: {e}")

        finally:
            self.status.is_syncing = False

        return result

    def _sync_directory(
        self, client: WebDAV4Client, local_dir: Path, remote_dir: str,
        result: SyncResult, progress_callback: Optional[Callable] = None
    ):
        """
        双向同步单个目录（智能同步策略）

        首次同步：仅下载云端文件到本地
        日常同步：以本地为主，支持删除同步
        """
        local_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_remote_dir(client, remote_dir)

        local_files = self._get_local_files(local_dir)
        remote_files = self._get_remote_files(client, remote_dir)

        logger.info(f"[Sync] {remote_dir}: 本地文件数={len(local_files)}, 云端文件数={len(remote_files)}")

        # 判断是否首次同步
        is_first = self.is_first_sync()

        if is_first:
            # 首次同步：仅下载云端文件
            logger.info(f"[Sync] 首次同步 {remote_dir}，仅下载云端文件")
            self._first_sync_directory(
                client, local_dir, remote_dir,
                local_files, remote_files,
                result, progress_callback
            )
        else:
            # 日常同步：以本地为主，包括删除同步
            logger.info(f"[Sync] 日常同步 {remote_dir}，以本地为主")
            self._normal_sync_directory(
                client, local_dir, remote_dir,
                local_files, remote_files,
                result, progress_callback
            )

    def _first_sync_directory(
        self, client: WebDAV4Client, local_dir: Path, remote_dir: str,
        local_files: Dict[str, int], remote_files: Dict[str, int],
        result: SyncResult, progress_callback: Optional[Callable] = None
    ):
        """
        首次同步：智能双向同步

        策略：
        1. 云端有文件 -> 下载到本地（保护本地文件，不覆盖）
        2. 云端没有但本地有 -> 上传到云端（初始化云端）
        3. 双方都有 -> 跳过（保护数据）
        """
        all_files = set(local_files.keys()) | set(remote_files.keys())
        total = len(all_files)
        current = 0

        logger.info(f"[Sync] {remote_dir} 首次同步: 待处理文件数={total}")

        for rel_path in all_files:
            current += 1
            local_file = local_dir / rel_path
            remote_file = f"{remote_dir}/{rel_path}"

            if progress_callback:
                progress_callback(current, total, rel_path)

            local_size = local_files.get(rel_path, 0)
            remote_size = remote_files.get(rel_path, 0)

            try:
                if remote_size > 0 and local_size == 0:
                    # 云端有，本地没有 -> 下载
                    local_file.parent.mkdir(parents=True, exist_ok=True)
                    client.download_file(remote_file, str(local_file))
                    result.downloaded.append(rel_path)
                    logger.info(f"[Sync] 首次下载: {rel_path}")

                elif local_size > 0 and remote_size == 0:
                    # 本地有，云端没有 -> 上传（初始化云端）
                    logger.info(f"[Sync] 准备首次上传: {rel_path} (本地{local_size}字节)")
                    client.upload_file(str(local_file), remote_file, overwrite=True)
                    result.uploaded.append(rel_path)
                    logger.info(f"[Sync] 首次上传成功: {rel_path}")

                else:
                    # 双方都有 -> 跳过（保护数据，避免覆盖）
                    result.skipped.append(rel_path)
                    logger.info(f"[Sync] 跳过（双方都有）: {rel_path}")

            except Exception as e:
                result.errors.append(f"{rel_path}: {e}")
                logger.error(f"[Sync] 首次同步失败 {rel_path}: {e}")

    def _normal_sync_directory(
        self, client: WebDAV4Client, local_dir: Path, remote_dir: str,
        local_files: Dict[str, int], remote_files: Dict[str, int],
        result: SyncResult, progress_callback: Optional[Callable] = None
    ):
        """
        日常同步：严格以本地为主

        策略：
        - 本地有，云端没有 → 上传
        - 本地没有，云端有 → 删除云端（本地已删除）
        - 本地和云端大小不同 → 以本地为准，上传覆盖
        - 大小相同 → 跳过
        """
        all_files = set(local_files.keys()) | set(remote_files.keys())
        total = len(all_files)
        current = 0

        logger.info(f"[Sync] {remote_dir} 日常同步（以本地为主）: 待处理文件数={total}")

        for rel_path in all_files:
            current += 1
            local_file = local_dir / rel_path
            remote_file = f"{remote_dir}/{rel_path}"

            if progress_callback:
                progress_callback(current, total, rel_path)

            local_size = local_files.get(rel_path, 0)
            remote_size = remote_files.get(rel_path, 0)

            try:
                if local_size > 0 and remote_size == 0:
                    # 本地有，云端没有 → 上传（本地新增）
                    logger.info(f"[Sync] 准备上传: {rel_path} (本地{local_size}字节)")
                    client.upload_file(str(local_file), remote_file, overwrite=True)
                    result.uploaded.append(rel_path)
                    logger.info(f"[Sync] 上传成功: {rel_path}")

                elif local_size == 0 and remote_size > 0:
                    # 本地没有，云端有 → 删除云端文件（以本地为主）
                    logger.info(f"[Sync] 本地已删除，删除云端文件: {rel_path}")
                    client.remove(remote_file)
                    result.uploaded.append(f"[删除] {rel_path}")
                    logger.info(f"[Sync] 删除云端文件成功: {rel_path}")

                elif local_size != remote_size:
                    # 大小不同 → 以本地为准，上传覆盖云端
                    logger.info(f"[Sync] 准备更新: {rel_path} (本地{local_size}字节, 云端{remote_size}字节)")
                    client.upload_file(str(local_file), remote_file, overwrite=True)
                    result.uploaded.append(rel_path)
                    logger.info(f"[Sync] 更新成功: {rel_path}")

                else:
                    # 大小相同 → 跳过
                    result.skipped.append(rel_path)

            except Exception as e:
                result.errors.append(f"{rel_path}: {e}")
                logger.error(f"[Sync] 同步文件失败 {rel_path}: {e}")


# 全局同步服务实例
_sync_service: Optional[SyncService] = None


def get_sync_service() -> SyncService:
    """获取全局同步服务实例"""
    global _sync_service
    if _sync_service is None:
        _sync_service = SyncService()
    return _sync_service
