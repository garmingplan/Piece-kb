"""
统一日志配置模块

提供控制台和内存缓冲的日志处理器，支持前端实时查看日志。
"""

import logging
from collections import deque
from typing import Dict, List, Optional
from datetime import datetime


# 全局日志缓冲区（最多保存 500 条）
_log_buffer: deque = deque(maxlen=500)

# 缓冲区锁（线程安全）
import threading
_buffer_lock = threading.Lock()


class BufferedHandler(logging.Handler):
    """内存缓冲日志处理器，将日志保存到 deque 中供 API 读取"""

    def emit(self, record: logging.LogRecord):
        """处理日志记录"""
        try:
            # 格式化日志记录
            log_entry = {
                "timestamp": datetime.fromtimestamp(record.created).isoformat(),
                "level": record.levelname,
                "module": record.name,
                "message": self.format(record),
                "line": record.lineno,
                "function": record.funcName,
            }

            # 线程安全地添加到缓冲区
            with _buffer_lock:
                _log_buffer.append(log_entry)
        except Exception:
            # 避免日志系统自身出错影响主程序
            self.handleError(record)


def setup_logging(level: str = "INFO"):
    """
    配置全局日志系统

    Args:
        level: 日志级别（DEBUG, INFO, WARNING, ERROR, CRITICAL）
    """
    # 获取根 logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # 清除已有的 handlers（避免重复配置）
    root_logger.handlers.clear()

    # 1. 控制台 Handler（简洁格式）
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # 2. 内存缓冲 Handler（结构化数据）
    buffer_handler = BufferedHandler()
    buffer_handler.setLevel(logging.DEBUG)
    buffer_formatter = logging.Formatter(
        fmt="%(message)s"  # 内存缓冲只保存 message，其他信息在 emit 中提取
    )
    buffer_handler.setFormatter(buffer_formatter)
    root_logger.addHandler(buffer_handler)

    # 记录初始化日志
    root_logger.info("日志系统初始化成功")


def get_log_buffer(level: Optional[str] = None, limit: int = 500) -> List[Dict]:
    """
    获取日志缓冲区内容

    Args:
        level: 过滤级别（可选，如 "ERROR", "WARNING"）
        limit: 返回的最大日志数量

    Returns:
        日志列表（时间倒序）
    """
    with _buffer_lock:
        logs = list(_log_buffer)

    # 按级别过滤
    if level:
        logs = [log for log in logs if log["level"] == level.upper()]

    # 倒序（最新的在前）
    logs.reverse()

    # 限制数量
    return logs[:limit]


def clear_log_buffer():
    """清空日志缓冲区"""
    with _buffer_lock:
        _log_buffer.clear()

    # 记录清空操作
    logger = logging.getLogger(__name__)
    logger.info("日志缓冲区已清空")
