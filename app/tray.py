"""
系统托盘管理模块

职责:
- 创建系统托盘图标
- 处理托盘菜单事件
- 管理窗口显示/隐藏
"""

import threading
import logging
from pathlib import Path
from typing import Callable, Optional

import pystray
from PIL import Image

logger = logging.getLogger(__name__)


# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent

# 图标路径
ICON_PATH = PROJECT_ROOT / "doc" / "icon.ico"


class TrayManager:
    """系统托盘管理器"""

    def __init__(
        self,
        on_show_window: Callable[[], None],
        on_quit: Callable[[], None],
    ):
        """
        初始化托盘管理器

        Args:
            on_show_window: 显示窗口的回调函数
            on_quit: 退出应用的回调函数
        """
        self.on_show_window = on_show_window
        self.on_quit = on_quit
        self.icon: Optional[pystray.Icon] = None
        self._thread: Optional[threading.Thread] = None

    def _load_icon(self) -> Image.Image:
        """加载托盘图标"""
        if ICON_PATH.exists():
            return Image.open(ICON_PATH)
        else:
            # 创建一个简单的占位图标
            img = Image.new("RGB", (64, 64), color=(66, 133, 244))
            return img

    def _create_menu(self) -> pystray.Menu:
        """创建托盘右键菜单"""
        return pystray.Menu(
            pystray.MenuItem(
                "显示主界面",
                self._on_show_click,
                default=True,  # 双击托盘图标时触发
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "MCP 服务: 运行中",
                None,
                enabled=False,  # 仅显示状态，不可点击
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "退出",
                self._on_quit_click,
            ),
        )

    def _on_show_click(self, icon, item):
        """点击显示主界面"""
        if self.on_show_window:
            self.on_show_window()

    def _on_quit_click(self, icon, item):
        """点击退出"""
        self.stop()
        if self.on_quit:
            self.on_quit()

    def start(self):
        """启动托盘图标（在新线程中运行）"""
        if self.icon is not None:
            return

        image = self._load_icon()
        menu = self._create_menu()

        self.icon = pystray.Icon(
            name="Piece",
            icon=image,
            title="Piece - 个人知识库",
            menu=menu,
        )

        # 在新线程中运行托盘
        self._thread = threading.Thread(target=self.icon.run, daemon=True)
        self._thread.start()
        logger.info("[Tray] 系统托盘已启动")

    def stop(self):
        """停止托盘图标"""
        if self.icon is not None:
            self.icon.stop()
            self.icon = None
            logger.info("[Tray] 系统托盘已停止")
