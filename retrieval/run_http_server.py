"""
HTTP服务器启动脚本
使用Streamable HTTP协议运行FastMCP服务

启动方式：
    cd retrieval
    python run_http_server.py

环境变量：
    - MCP_HOST: 监听地址（默认：0.0.0.0）
    - MCP_PORT: 监听端口（默认：8686）

CherryStudio配置：
    - 类型：可流式传输的 HTTP (StreamableHttp)
    - URL：http://127.0.0.1:8686/mcp
"""

import os
import sys
import logging
from pathlib import Path

# 设置环境变量，确保控制台输出支持 UTF-8（修复 Windows GBK 编码问题）
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')

# 在导入任何模块前，强制设置标准输出编码为 UTF-8
if sys.platform == 'win32':
    import io
    # 重定向 stdout 和 stderr 到 UTF-8 编码的流
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 添加项目根目录到 Python 路径，以支持包导入
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 配置日志
from app.logging_config import setup_logging
setup_logging(level="INFO")

from retrieval.server import mcp

logger = logging.getLogger(__name__)

if __name__ == "__main__":
    # 从环境变量读取配置，支持Docker部署
    host = os.getenv("MCP_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_PORT", "8686"))

    # 使用FastMCP内置的run方法启动HTTP服务器
    logger.info(f"[MCP] Starting server - {host}:{port}/mcp")
    mcp.run(
        transport="streamable-http",  # Streamable HTTP传输协议
        host=host,                     # 监听地址（Docker中使用0.0.0.0）
        port=port,                     # 端口号
        path="/mcp"                    # 端点路径，匹配CherryStudio URL
    )
