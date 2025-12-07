"""
Indexing 后台服务入口（无 UI）

职责:
- 初始化数据库
- 启动后台任务处理器

注意: 完整的应用（包含 UI 和 API）请使用 app/server.py

启动方式:
- 项目根目录运行: python -m indexing.server
- 或直接运行本文件: python indexing/server.py
"""

import asyncio
import sys
import logging
from pathlib import Path

# 支持直接运行本文件
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    __package__ = "indexing"

# 配置日志
from app.logging_config import setup_logging
setup_logging(level="INFO")

from .database import init_database
from .services.processor import processor

logger = logging.getLogger(__name__)


async def main():
    """启动后台服务"""
    # 初始化数据库
    init_database()

    logger.info("=" * 50)
    logger.info("Indexing 后台服务已启动")
    logger.info("按 Ctrl+C 停止服务")
    logger.info("=" * 50)

    # 启动处理器
    await processor.start()

    try:
        # 保持运行
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("\n正在停止服务...")
    finally:
        await processor.stop()
        logger.info("服务已停止")


if __name__ == "__main__":
    asyncio.run(main())
