"""
Indexing 公共工具函数

职责:
- 提供可复用的工具函数
- 向量序列化等底层操作
"""

import struct
from typing import List


def serialize_float32(vector: List[float]) -> bytes:
    """
    将浮点数列表序列化为 sqlite-vec 需要的二进制格式

    Args:
        vector: 浮点数列表（如 embedding 向量）

    Returns:
        二进制格式的向量数据
    """
    return struct.pack(f"{len(vector)}f", *vector)
