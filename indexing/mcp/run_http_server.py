"""
索引 MCP HTTP 服务启动脚本

通过 HTTP 协议提供 MCP 服务，支持 Claude Desktop 等客户端连接。
"""
import sys
import asyncio
import logging
import threading
from pathlib import Path

# 添加项目根目录到 Python 路径
ROOT_DIR = Path(__file__).parent.parent.parent.absolute()
sys.path.insert(0, str(ROOT_DIR))

from app.logging_config import setup_logging
from indexing.mcp.config import get_mcp_port, get_mcp_host
from indexing.mcp.server import mcp
from indexing.services.processor import processor

# 配置日志
setup_logging(level="INFO")
logger = logging.getLogger(__name__)


def start_processor_in_background():
    """在后台线程中启动任务处理器"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    logger.info("[Processor] 启动后台任务处理器...")
    loop.run_until_complete(processor.start())

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        loop.run_until_complete(processor.stop())
        loop.close()


def main():
    """启动 HTTP 服务"""
    host = get_mcp_host()
    port = get_mcp_port()

    logger.info("=" * 50)
    logger.info(f"启动 Piece 索引 MCP 服务 (piece-index)")
    logger.info(f"监听地址: {host}:{port}")
    logger.info(f"MCP 端点: http://{host}:{port}/mcp")
    logger.info(f"协议: Streamable HTTP")
    logger.info("=" * 50)

    # 在后台线程启动任务处理器
    processor_thread = threading.Thread(
        target=start_processor_in_background,
        daemon=True,
        name="TaskProcessor"
    )
    processor_thread.start()

    try:
        # 运行 HTTP 服务
        mcp.run(transport="streamable-http", host=host, port=port)
    except KeyboardInterrupt:
        logger.info("\n[MCP] 服务已停止 (用户中断)")
    except Exception as e:
        logger.error(f"[MCP] 服务异常: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
