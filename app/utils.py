"""
公共工具函数

职责:
- 提供可复用的工具函数
- 定义公共常量
"""

# 文件大小限制（100MB）
MAX_FILE_SIZE = 100 * 1024 * 1024


def format_size(size_bytes: int) -> str:
    """
    格式化文件大小为人类可读的字符串

    Args:
        size_bytes: 文件大小（字节）

    Returns:
        格式化后的字符串，如 "1.2 MB"
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
