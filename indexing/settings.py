"""
用户设置管理模块

职责:
- 配置文件读写（config.json）
- 提供统一的配置访问接口
- 支持云同步（仅同步 data_path 目录下的 files/ 子目录）

配置文件位置: 始终在 {应用目录}/data/config.json（不随 data_path 变化）
数据存储位置: 由 data_path 配置指定
"""

import sys
import json
import logging
import secrets
from pathlib import Path
from typing import Optional
from pydantic import BaseModel

logger = logging.getLogger(__name__)


def generate_api_key(length: int = 32) -> str:
    """
    生成随机 API 密钥

    Args:
        length: 密钥长度（默认 32 字符）

    Returns:
        str: 随机生成的 API 密钥（十六进制字符串）
    """
    return secrets.token_hex(length // 2)


def _get_app_root() -> Path:
    """
    获取应用根目录

    开发环境: 项目根目录（Piece/）
    打包环境: Piece.exe 所在目录（Piece/）
    """
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后，sys.executable 是 Piece.exe 的路径
        return Path(sys.executable).parent
    else:
        # 开发环境，indexing/settings.py 的上级目录
        return Path(__file__).parent.parent


# 应用根目录
APP_ROOT = _get_app_root()

# 默认数据目录
DEFAULT_DATA_PATH = APP_ROOT / "data"


class EmbeddingSettings(BaseModel):
    """嵌入模型配置"""
    base_url: str = "https://api.siliconflow.cn/v1"
    api_key: str = ""
    model: str = "BAAI/bge-m3"
    vector_dim: int = 1024
    max_tokens: int = 8192  # 模型最大上下文长度


class McpSettings(BaseModel):
    """MCP 服务配置"""
    port: int = 8686
    api_key: str = ""  # MCP 访问密钥（为空时禁用认证）
    auth_enabled: bool = True  # 是否启用密钥验证


class AppearanceSettings(BaseModel):
    """外观设置"""
    theme: str = "light"  # "dark" | "light" | "pink"
    language: str = "zh"  # "zh" | "en"


class WebDAVSettings(BaseModel):
    """WebDAV 云同步配置"""
    enabled: bool = False  # 是否启用云同步
    hostname: str = ""  # WebDAV 服务器完整地址，如 https://dav.jianguoyun.com/dav/Piece/
    username: str = ""  # 用户名（坚果云为邮箱）
    password: str = ""  # 密码（坚果云需要应用密码）
    last_sync_time: Optional[str] = None  # 上次同步时间（ISO格式字符串）


class AppSettings(BaseModel):
    """应用设置"""
    embedding: EmbeddingSettings = EmbeddingSettings()
    mcp: McpSettings = McpSettings()
    appearance: AppearanceSettings = AppearanceSettings()
    webdav: WebDAVSettings = WebDAVSettings()
    data_path: str = str(DEFAULT_DATA_PATH)

    def get_data_path(self) -> Path:
        """获取数据目录路径"""
        return Path(self.data_path)

    def get_db_path(self) -> Path:
        """获取数据库路径"""
        return self.get_data_path() / "kb.db"

    def get_files_path(self) -> Path:
        """获取文件存储路径"""
        return self.get_data_path() / "files"


def _get_config_file_path() -> Path:
    """获取配置文件路径（首次启动时使用默认路径）"""
    return DEFAULT_DATA_PATH / "config.json"


def load_settings() -> AppSettings:
    """
    加载用户设置

    优先从 config.json 读取，不存在则创建默认配置文件
    """
    config_path = _get_config_file_path()

    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return AppSettings(**data)
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"[Settings] 配置文件读取失败，使用默认配置: {e}")
            return AppSettings()

    # 配置文件不存在，创建默认配置
    logger.info(f"[Settings] 配置文件不存在，创建默认配置: {config_path}")
    default_settings = AppSettings()

    # 首次启动时自动生成 MCP API 密钥
    default_settings.mcp.api_key = generate_api_key()
    logger.info(f"[Settings] 已自动生成 MCP API 密钥")

    # 确保目录存在
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # 写入默认配置
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(default_settings.model_dump(), f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"[Settings] 默认配置创建失败: {e}")

    return default_settings


def save_settings(settings: AppSettings) -> bool:
    """
    保存用户设置到 config.json

    注意：config.json 始终保存在默认数据目录，不随 data_path 变化
    这样确保应用重启后能正确读取配置

    保存成功后会自动刷新全局配置缓存

    Args:
        settings: 应用设置对象

    Returns:
        bool: 保存成功返回 True
    """
    # 确保默认数据目录存在（config.json 的位置）
    DEFAULT_DATA_PATH.mkdir(parents=True, exist_ok=True)

    # 确保用户指定的数据目录存在
    data_path = settings.get_data_path()
    data_path.mkdir(parents=True, exist_ok=True)

    # 同时确保 files 目录存在
    files_path = settings.get_files_path()
    files_path.mkdir(parents=True, exist_ok=True)

    # config.json 始终保存在默认位置
    config_path = _get_config_file_path()

    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(settings.model_dump(), f, indent=2, ensure_ascii=False)
        logger.info(f"[Settings] 配置已保存: {config_path}")

        # 自动刷新全局缓存
        global _settings
        _settings = settings

        return True
    except Exception as e:
        logger.error(f"[Settings] 配置保存失败: {e}", exc_info=True)
        return False


def get_embedding_config() -> dict:
    """
    获取嵌入模型配置（兼容 OpenAIEmbeddings 参数格式）

    Returns:
        dict: 包含 base_url, api_key, model, check_embedding_ctx_length
    """
    settings = get_settings()  # 使用缓存
    return {
        "base_url": settings.embedding.base_url,
        "api_key": settings.embedding.api_key,
        "model": settings.embedding.model,
        "check_embedding_ctx_length": False,
    }


def get_vector_dim() -> int:
    """获取向量维度"""
    settings = get_settings()  # 使用缓存
    return settings.embedding.vector_dim


def get_mcp_port() -> int:
    """获取 MCP 服务端口"""
    settings = get_settings()  # 使用缓存
    return settings.mcp.port


def get_mcp_api_key() -> str:
    """获取 MCP API 密钥"""
    settings = get_settings()  # 使用缓存
    return settings.mcp.api_key


def is_mcp_auth_enabled() -> bool:
    """检查 MCP 认证是否启用"""
    settings = get_settings()  # 使用缓存
    return settings.mcp.auth_enabled and bool(settings.mcp.api_key)


def get_db_path() -> Path:
    """获取数据库路径"""
    settings = get_settings()  # 使用缓存
    return settings.get_db_path()


def get_files_path() -> Path:
    """获取文件存储路径"""
    settings = get_settings()  # 使用缓存
    return settings.get_files_path()


# 全局设置实例（延迟加载）
_settings: Optional[AppSettings] = None


def get_settings() -> AppSettings:
    """获取全局设置实例"""
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings


def reload_settings() -> AppSettings:
    """重新加载设置"""
    global _settings
    _settings = load_settings()
    return _settings


def get_webdav_config() -> dict:
    """
    获取 WebDAV 配置

    Returns:
        dict: 包含 enabled, hostname, username, password, last_sync_time
    """
    settings = get_settings()  # 使用缓存
    return {
        "enabled": settings.webdav.enabled,
        "hostname": settings.webdav.hostname,
        "username": settings.webdav.username,
        "password": settings.webdav.password,
        "last_sync_time": settings.webdav.last_sync_time,
    }


def get_chunking_config() -> dict:
    """
    获取分块配置

    根据嵌入模型的 max_tokens 自动计算最大分块大小。
    公式：max_chunk_size = max_tokens * 0.8 / 1.5
    - 0.8 是安全系数（使用 80% 容量）
    - 1.5 是字符→Token 转换系数（保守估计）

    Returns:
        dict: 包含 max_chunk_size（字符数）
    """
    settings = get_settings()  # 使用缓存
    max_chunk_size = int(settings.embedding.max_tokens * 0.8 / 1.5)
    return {
        "max_chunk_size": max_chunk_size,
    }
