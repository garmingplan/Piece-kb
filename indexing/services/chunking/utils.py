"""
分块工具函数

提供递归切分、表格/公式保护等通用功能。
"""

import re
from typing import List, Tuple


# 分隔符优先级列表（从高到低）
SEPARATORS = [
    "\n\n",  # 段落边界
    "\n",  # 换行
    "。",
    "！",
    "？",
    ".",
    "!",
    "?",  # 句子边界
    "；",
    ";",  # 分号
    "，",
    ",",  # 逗号
    " ",  # 空格
]


def find_table_boundaries(text: str) -> List[Tuple[int, int]]:
    """
    查找文本中所有 Markdown 表格的起始和结束位置

    Markdown 表格格式:
    | 列1 | 列2 |
    |-----|-----|
    | 数据1 | 数据2 |

    Returns:
        [(start_pos, end_pos), ...] 表格边界列表
    """
    boundaries = []
    lines = text.split('\n')
    in_table = False
    table_start = 0
    line_pos = 0

    for i, line in enumerate(lines):
        # 判断是否为表格行（以|开头和结尾，且包含至少2个|）
        stripped = line.strip()
        is_table_line = (
            stripped.startswith('|') and
            stripped.endswith('|') and
            stripped.count('|') >= 2
        )

        if is_table_line and not in_table:
            # 表格开始
            in_table = True
            table_start = line_pos
        elif not is_table_line and in_table:
            # 表格结束（当前行不是表格行）
            table_end = line_pos
            boundaries.append((table_start, table_end))
            in_table = False

        # 更新位置（+1 是换行符）
        line_pos += len(lines[i]) + 1

    # 处理文本末尾的表格
    if in_table:
        boundaries.append((table_start, len(text)))

    return boundaries


def find_formula_boundaries(text: str) -> List[Tuple[int, int]]:
    """
    查找文本中所有 LaTeX 公式的起始和结束位置

    支持:
    - 块级公式: $$...$$
    - 行内公式: $...$

    Returns:
        [(start_pos, end_pos), ...] 公式边界列表
    """
    boundaries = []

    # 匹配块级公式 $$...$$ (非贪婪模式，支持多行)
    for match in re.finditer(r'\$\$[\s\S]+?\$\$', text):
        boundaries.append((match.start(), match.end()))

    # 匹配行内公式 $...$ (排除 $$，单行模式)
    # 使用负向前瞻和负向后顾排除 $$
    for match in re.finditer(r'(?<!\$)\$(?!\$)([^\$\n]+?)\$(?!\$)', text):
        boundaries.append((match.start(), match.end()))

    return boundaries


def is_safe_split_point(pos: int, boundaries: List[Tuple[int, int]]) -> bool:
    """
    检查某个位置是否可以安全切分（不在受保护区域内部）

    Args:
        pos: 待检查的切分位置
        boundaries: 受保护区域列表 [(start, end), ...]

    Returns:
        True 表示可以安全切分，False 表示在受保护区域内
    """
    for start, end in boundaries:
        if start < pos < end:
            return False
    return True


def recursive_split(
    text: str,
    chunk_size: int = 800,
    overlap: int = 150,
) -> List[str]:
    """
    递归字符切分器

    分层尝试分隔符，优先在语义边界处切分，并添加重叠窗口。
    保护表格和公式不被截断。

    Args:
        text: 待切分文本
        chunk_size: 目标切片大小（默认 800）
        overlap: 重叠窗口大小（默认 150）

    Returns:
        切分后的文本列表
    """
    text = text.strip()
    if not text:
        return []

    # 文本足够短，直接返回
    if len(text) <= chunk_size:
        return [text]

    # 查找受保护区域（表格和公式）
    protected_boundaries = []
    protected_boundaries.extend(find_table_boundaries(text))
    protected_boundaries.extend(find_formula_boundaries(text))
    # 按起始位置排序，便于后续处理
    protected_boundaries.sort(key=lambda x: x[0])

    # 尝试找到最佳分隔符
    def find_split_point(text: str, target_size: int, offset: int = 0) -> int:
        """
        在目标位置之前找到最佳切分点，避开受保护区域

        Args:
            text: 当前文本片段
            target_size: 目标切分位置（相对于text）
            offset: text在原始完整文本中的偏移量

        Returns:
            切分点位置（相对于text）
        """
        # 在 target_size 之前寻找分隔符
        search_start = max(0, target_size - 200)
        search_end = target_size
        search_range = text[search_start:search_end]

        # 收集所有分隔符的位置和优先级
        candidates = []
        for priority, sep in enumerate(SEPARATORS):
            pos = search_range.rfind(sep)
            if pos != -1:
                actual_pos = search_start + pos + len(sep)
                if actual_pos > 0 and actual_pos < len(text):
                    # 转换为在原始文本中的绝对位置
                    absolute_pos = offset + actual_pos
                    # 检查是否在受保护区域内
                    if is_safe_split_point(absolute_pos, protected_boundaries):
                        # 计算距离 target_size 的远近（越近越好）
                        distance = target_size - actual_pos
                        candidates.append((priority, distance, actual_pos))

        if candidates:
            # 排序：优先级高的分隔符，如果距离差不多（<50字符）则选优先级高的
            # 否则选距离更近的
            def score(item):
                priority, distance, pos = item
                # 距离很近（<50）时，优先考虑分隔符优先级
                # 距离较远时，位置更重要
                if distance < 50:
                    return (0, priority, distance)
                else:
                    return (1, distance, priority)

            candidates.sort(key=score)
            return candidates[0][2]

        # 没找到安全的分隔符，向前查找安全点
        for offset_pos in range(target_size, max(0, target_size - 400), -10):
            absolute_pos = offset + offset_pos
            if is_safe_split_point(absolute_pos, protected_boundaries):
                return offset_pos

        # 实在找不到，强制在 target_size 处切分
        return target_size

    # 切分文本
    chunks = []
    start = 0

    while start < len(text):
        # 计算本次切片的结束位置
        end = start + chunk_size

        if end >= len(text):
            # 剩余文本不足一个切片，直接添加
            remaining = text[start:].strip()
            if remaining:
                chunks.append(remaining)
            break

        # 找到最佳切分点（传入offset，以便在原始文本中查找受保护区域）
        split_point = find_split_point(text[start:], chunk_size, offset=start)
        actual_end = start + split_point

        # 提取切片
        chunk = text[start:actual_end].strip()
        if chunk:
            chunks.append(chunk)

        # 下一个切片的起始位置（考虑重叠）
        start = actual_end - overlap
        if start < 0:
            start = 0
        # 避免死循环：确保向前推进
        if start <= (actual_end - chunk_size) and actual_end < len(text):
            start = actual_end

    return chunks


def clean_heading(heading: str) -> str:
    """清理标题中的特殊字符，保留中文、英文、数字、括号、空格"""
    heading = heading.lstrip("#").strip()
    heading = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9()\（\）\s]", "", heading)
    return heading.strip()
