"""
文档获取工具：根据doc_title列表批量获取完整文档内容
"""
from typing import List, Dict, Optional
from ..db import get_db_cursor


def get_docs(doc_titles: List[str]) -> Dict[str, Optional[str]]:
    """
    根据doc_title列表获取文档内容（使用连接池）

    Args:
        doc_titles: doc_title列表（如["传染病_百日咳", "糖尿病肾病_概述"]）

    Returns:
        doc_title到文档内容的字典映射
        {
            "传染病_百日咳": "文档内容...",
            "糖尿病肾病_概述": "文档内容...",
            ...
        }
    """
    if not doc_titles:
        return {}

    # 使用连接池
    with get_db_cursor() as cursor:
        # 构建占位符
        placeholders = ",".join(["?" for _ in doc_titles])

        # 批量查询：使用IN精确匹配doc_title
        query = f"""
            SELECT doc_title, chunk_text
            FROM chunks
            WHERE doc_title IN ({placeholders})
        """

        cursor.execute(query, doc_titles)
        rows = cursor.fetchall()

        # 构建doc_title到文档内容的映射
        result = {}
        for row in rows:
            result[row[0]] = row[1]

        # 对于未找到的doc_title，设置为None
        for title in doc_titles:
            if title not in result:
                result[title] = None

        return result

