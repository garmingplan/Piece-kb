"""
请求速率限制模块

职责:
- 控制 API 请求频率，避免超过服务商限制
- 支持 RPM (Requests Per Minute) 和最小请求间隔
- 使用令牌桶算法控制请求速率
"""

import asyncio
import time
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    速率限制器（简化版：只控制请求间隔）

    特点:
    - 强制最小请求间隔（基于 RPM）
    - 线程安全（asyncio 兼容）
    """

    def __init__(self, rpm: int = 300):
        """
        初始化速率限制器

        Args:
            rpm: 每分钟最大请求数（默认 300）
        """
        self.rpm = rpm
        self.min_interval = 60.0 / rpm  # 最小请求间隔（秒）

        # 最后一次请求的时间
        self.last_request_time: Optional[float] = None

        # 互斥锁
        self._lock = asyncio.Lock()

        logger.info(
            f"[RateLimiter] 初始化: RPM={rpm}, 最小间隔={self.min_interval:.3f}s"
        )

    async def acquire(self, tokens: int = 1) -> None:
        """
        请求一个 API 调用的许可（如果超限则等待）

        Args:
            tokens: 本次请求消耗的令牌数（默认 1）
        """
        async with self._lock:
            # 强制最小间隔（基于 RPM 计算）
            min_wait = 60.0 / self.rpm  # 平均请求间隔

            if self.last_request_time is not None:
                elapsed_since_last = time.time() - self.last_request_time
                logger.info(f"[RateLimiter] 距上次请求 {elapsed_since_last:.3f}秒，最小间隔 {min_wait:.3f}秒")

                if elapsed_since_last < min_wait:
                    interval_wait = min_wait - elapsed_since_last
                    logger.warning(f"[RateLimiter] 强制等待 {interval_wait:.3f}秒（确保 {self.rpm} RPM）")
                    await asyncio.sleep(interval_wait)

            # 更新最后请求时间
            self.last_request_time = time.time()
            logger.info(f"[RateLimiter] 许可已授予，当前 RPM 目标: {self.rpm}")

    def get_stats(self) -> dict:
        """
        获取当前速率统计

        Returns:
            {"rpm": int, "min_interval": float}
        """
        return {
            "rpm": self.rpm,
            "min_interval": self.min_interval,
        }


# 全局单例
_rate_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """获取全局速率限制器实例"""
    global _rate_limiter
    if _rate_limiter is None:
        # 硅基流动实名认证后限制：RPM=2000, TPM=500,000
        #
        # 计算依据：
        # - TPM 限制：500,000 tokens/分钟（真正的瓶颈）
        # - 平均切片大小：约 2000 tokens（考虑中英文混合）
        # - 批次大小：10 个切片/请求（processor.py 中配置）
        # - 每请求 tokens：10 × 2000 = 20,000 tokens
        # - 理论最大 RPM：500,000 ÷ 20,000 = 25 RPM
        # - 安全配置：20 RPM（400,000 TPM，80% 利用率）
        #
        # 实际吞吐量：20 RPM × 10 切片 = 200 切片/分钟
        _rate_limiter = RateLimiter(rpm=20)
    return _rate_limiter
