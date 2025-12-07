"""
Piece 应用主入口

职责:
- 初始化数据库
- 注册 API 路由和 UI 页面
- 启动后台任务处理器
- 启动 MCP 检索服务（后台线程）
- 启动系统托盘（支持最小化到托盘）
- 启动 NiceGUI 桌面应用（native mode）

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

from indexing.database import init_database
from indexing.services.processor import processor
from indexing.settings import get_settings
from app.api import register_routes, register_chunk_routes, register_export_routes
from app.api.log_routes import register_log_routes
from app.ui import register_pages
from app.tray import TrayManager


# MCP 服务配置
MCP_HOST = os.getenv("MCP_HOST", "127.0.0.1")

# 全局托盘管理器
_tray_manager: TrayManager = None

# 全局窗口引用（用于显示/隐藏）
_webview_window = None

# 标记是否是主进程（用于避免子进程重复初始化）
_is_main_process = multiprocessing.current_process().name == "MainProcess"

# 获取日志记录器
logger = logging.getLogger(__name__)


def start_mcp_server():
    """在后台线程中启动 MCP 服务"""
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

        logger.info(f"[MCP] Starting Piece MCP service - http://{MCP_HOST}:{mcp_port}/mcp")
        mcp.run(
            transport="streamable-http",
            host=MCP_HOST,
            port=mcp_port,
            path="/mcp",
        )
    except Exception as e:
        logger.error(f"[MCP] Failed to start: {e}", exc_info=True)


def _show_window():
    """显示主窗口"""
    global _webview_window
    if _webview_window is not None:
        try:
            _webview_window.show()
            _webview_window.restore()  # 从最小化恢复
        except Exception as e:
            logger.error(f"[Tray] 显示窗口失败: {e}", exc_info=True)


def _quit_app():
    """退出应用"""
    logger.info("[App] 正在退出...")
    # 停止 NiceGUI
    app.shutdown()


def _on_window_close():
    """
    窗口关闭事件处理

    返回 False 阻止窗口关闭,改为隐藏到托盘
    """
    global _webview_window
    if _webview_window is not None:
        try:
            _webview_window.hide()
            logger.info("[Tray] 窗口已最小化到托盘")
        except Exception as e:
            logger.error(f"[Tray] 隐藏窗口失败: {e}", exc_info=True)
    return False  # 阻止窗口关闭


def setup():
    """初始化服务（注册路由、页面、生命周期钩子）"""
    # 生命周期钩子
    app.on_startup(lambda: asyncio.create_task(processor.start()))
    app.on_shutdown(processor.stop)

    # 注册 API 路由
    register_routes(app)
    register_chunk_routes(app)
    register_export_routes(app)
    register_log_routes(app)

    # 注册 UI 页面
    register_pages()


def main():
    """启动应用"""
    global _tray_manager, _webview_window

    # 只在主进程中初始化数据库、MCP服务和托盘
    if _is_main_process:
        # 初始化数据库
        init_database()

        # 获取设置
        settings = get_settings()
        start_minimized = settings.appearance.start_minimized

        # 在后台线程启动 MCP 服务
        mcp_thread = threading.Thread(target=start_mcp_server, daemon=True)
        mcp_thread.start()

        # 创建托盘管理器
        _tray_manager = TrayManager(
            on_show_window=_show_window,
            on_quit=_quit_app,
        )
        _tray_manager.start()

        # 配置 pywebview 窗口事件
        def on_webview_ready():
            """pywebview 窗口就绪后的回调"""
            global _webview_window
            import webview

            # 获取窗口引用
            windows = webview.windows
            if windows:
                _webview_window = windows[0]

                # 设置关闭事件处理器（最小化到托盘）
                _webview_window.events.closing += _on_window_close

                # 如果配置了启动时最小化，则隐藏窗口
                if start_minimized:
                    # 延迟隐藏，确保窗口已完全显示
                    import time
                    time.sleep(0.5)
                    _webview_window.hide()
                    logger.info("[App] 启动时最小化到托盘")

        # 在新线程中等待 webview 就绪
        def wait_for_webview():
            import time
            # 等待 webview 初始化
            time.sleep(1)
            on_webview_ready()

        webview_thread = threading.Thread(target=wait_for_webview, daemon=True)
        webview_thread.start()

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
    )


if __name__ == "__main__":
    # PyInstaller 打包支持
    multiprocessing.freeze_support()
    main()
