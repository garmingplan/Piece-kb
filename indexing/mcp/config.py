"""
索引 MCP 配置模块
"""
import os
from pathlib import Path

# 默认配置
DEFAULT_PORT = 8687
DEFAULT_HOST = "0.0.0.0"

# 项目根目录
ROOT_DIR = Path(__file__).parent.parent.parent.absolute()

def get_mcp_port() -> int:
    """
    获取索引 MCP 服务端口

    优先级：环境变量 > config.json > 默认值
    """
    # 1. 环境变量
    port_str = os.getenv("PIECE_INDEX_MCP_PORT")
    if port_str:
        try:
            return int(port_str)
        except ValueError:
            pass

    # 2. config.json
    try:
        from indexing.settings import get_settings
        settings = get_settings()
        mcp_config = settings.get("mcp", {})
        if "indexing_port" in mcp_config:
            return mcp_config["indexing_port"]
    except Exception:
        pass

    # 3. 默认值
    return DEFAULT_PORT


def get_mcp_host() -> str:
    """获取索引 MCP 服务主机地址"""
    return os.getenv("PIECE_INDEX_MCP_HOST", DEFAULT_HOST)
