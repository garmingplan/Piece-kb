"""
Piece 应用主入口

职责:
- 初始化数据库
- 注册 API 路由和 UI 页面
- 启动后台任务处理器
- 启动检索 MCP 服务（后台线程，端口 8686）
- 启动索引 MCP 服务（后台线程，端口 8687）
- 启动 NiceGUI 桌面应用（native mode，端口 9888）

启动方式:
- 项目根目录运行: python -m app.server
- 或直接运行本文件: python app/server.py
"""

import asyncio
import sys
import os
import threading
import multiprocessing
import logging
from pathlib import Path

# 支持直接运行本文件，确保项目根目录在 sys.path 中
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 配置日志（在 sys.path 修改后导入）
from app.logging_config import setup_logging
setup_logging(level="INFO")

# 使用绝对导入（解决 Windows multiprocessing spawn 问题）
from nicegui import app, ui

from indexing.database import init_database, init_connection_pool, close_connection_pool
from retrieval.db import close_retrieval_connection_pool
from indexing.services.processor import processor
from indexing.settings import get_settings
from app.api import register_routes, register_chunk_routes
from app.api.log_routes import register_log_routes
from app.ui import register_pages


# MCP 服务配置
MCP_HOST = os.getenv("MCP_HOST", "127.0.0.1")

# 标记是否是主进程（用于避免子进程重复初始化）
_is_main_process = multiprocessing.current_process().name == "MainProcess"

# 获取日志记录器
logger = logging.getLogger(__name__)


def start_mcp_server():
    """在后台线程中启动检索 MCP 服务"""
    try:
        # 设置环境变量，确保控制台输出支持 UTF-8
        os.environ.setdefault('PYTHONIOENCODING', 'utf-8')

        # Windows 平台强制设置 stdout/stderr 编码为 UTF-8
        if sys.platform == 'win32':
            import io
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

        from retrieval.server import mcp

        settings = get_settings()
        mcp_port = settings.mcp.port

        logger.info(f"[MCP Retrieval] Starting Piece Retrieval MCP service - http://{MCP_HOST}:{mcp_port}/mcp")
        mcp.run(
            transport="streamable-http",
            host=MCP_HOST,
            port=mcp_port,
            path="/mcp",
        )
    except Exception as e:
        logger.error(f"[MCP Retrieval] Failed to start: {e}", exc_info=True)


def start_index_mcp_server():
    """在后台线程中启动索引 MCP 服务"""
    try:
        from indexing.mcp.server import mcp
        from indexing.mcp.config import get_mcp_port

        index_mcp_port = get_mcp_port()

        logger.info(f"[MCP Index] Starting Piece Index MCP service - http://{MCP_HOST}:{index_mcp_port}/mcp")
        mcp.run(
            transport="streamable-http",
            host=MCP_HOST,
            port=index_mcp_port,
            path="/mcp",
        )
    except Exception as e:
        logger.error(f"[MCP Index] Failed to start: {e}", exc_info=True)


def setup():
    """初始化服务（注册路由、页面、生命周期钩子）"""
    # 生命周期钩子
    app.on_startup(lambda: asyncio.create_task(processor.start()))

    # 关闭时清理资源（按依赖顺序：先停止任务，再关闭连接池）
    async def shutdown_processor():
        logger.info("[Shutdown] 正在停止任务处理器...")
        await processor.stop()
        logger.info("[Shutdown] 任务处理器已停止")

    def shutdown_indexing_pool():
        logger.info("[Shutdown] 正在关闭 indexing 数据库连接池...")
        close_connection_pool()
        logger.info("[Shutdown] indexing 连接池已关闭")

    def shutdown_retrieval_pool():
        logger.info("[Shutdown] 正在关闭 retrieval 数据库连接池...")
        close_retrieval_connection_pool()
        logger.info("[Shutdown] retrieval 连接池已关闭")

    app.on_shutdown(shutdown_processor)
    app.on_shutdown(shutdown_indexing_pool)
    app.on_shutdown(shutdown_retrieval_pool)

    # 关闭完成日志
    def log_shutdown_complete():
        logger.info("[Shutdown] 应用已安全关闭")
    app.on_shutdown(log_shutdown_complete)

    # 启动 MCP 服务（后台线程）
    if _is_main_process:
        retrieval_mcp_thread = threading.Thread(
            target=start_mcp_server,
            daemon=True,
            name="RetrievalMCP"
        )
        retrieval_mcp_thread.start()

        index_mcp_thread = threading.Thread(
            target=start_index_mcp_server,
            daemon=True,
            name="IndexMCP"
        )
        index_mcp_thread.start()

        logger.info("[App] MCP 服务已启动")

    # 注册 API 路由
    register_routes(app)
    register_chunk_routes(app)
    register_log_routes(app)

    # 注册 UI 页面
    register_pages()


def main():
    """启动应用"""
    # 只在主进程中初始化数据库和连接池
    if _is_main_process:
        # 1. 初始化数据库
        init_database()

        # 2. 初始化数据库连接池（性能优化：复用连接）
        init_connection_pool()
        logger.info("[App] 数据库连接池已初始化")
        logger.info("[App] MCP 服务将在 UI 完全启动后自动启动")

    # 初始化服务（主进程和子进程都需要）
    setup()

    # 获取图标路径（支持打包环境）
    if getattr(sys, 'frozen', False):
        # 打包环境：使用 _MEIPASS
        icon_path = Path(sys._MEIPASS) / "assets" / "icon.ico"
    else:
        # 开发环境
        icon_path = PROJECT_ROOT / "assets" / "icon.ico"

    # 启动 NiceGUI（native 模式，独立桌面窗口）
    ui.run(
        title="Piece - 个人知识库",
        host="127.0.0.1",
        port=9888,
        reload=False,
        show=True,
        native=True,  # 启用原生窗口模式
        window_size=(1100, 700),  # 窗口大小
        fullscreen=False,
        favicon=str(icon_path) if icon_path.exists() else None,  # 设置图标（文件存在时）
        # NiceGUI 连接配置（支持长时间操作）
        reconnect_timeout=30.0,  # 重连超时：30 秒（默认 3 秒）
        # Uvicorn 超时配置（支持大文件上传）
        timeout_keep_alive=300,  # Keep-alive 超时：5 分钟
        ws_ping_timeout=300,     # WebSocket ping 超时：5 分钟
        timeout_notify=300,      # 通知超时：5 分钟
    )


if __name__ == "__main__":
    # PyInstaller 打包支持
    multiprocessing.freeze_support()
    main()
