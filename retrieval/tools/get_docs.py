"""
文档获取工具：根据doc_title列表批量获取完整文档内容及元数据
"""
from typing import List, Dict, Optional, Any
from ..db import get_db_cursor


def get_docs(doc_titles: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
    """
    根据doc_title列表获取文档内容及元数据（使用连接池）

    Args:
        doc_titles: doc_title列表（如["传染病_百日咳", "糖尿病肾病_概述"]）

    Returns:
        doc_title到文档详情的字典映射
        {
            "传染病_百日咳": {
                "chunk_id": 123,
                "file_id": 45,
                "filename": "传染病知识手册.md",
                "doc_title": "传染病_百日咳",
                "chunk_text": "文档内容...",
                "total_chunks_in_file": 5,
                "chunk_index_in_file": 2
            },
            "糖尿病肾病_概述": {...},
            ...
        }

        未找到的doc_title会被设置为None
    """
    if not doc_titles:
        return {}

    # 使用连接池
    with get_db_cursor() as cursor:
        # 构建占位符
        placeholders = ",".join(["?" for _ in doc_titles])

        # 批量查询：使用窗口函数获取文件内切片统计信息
        query = f"""
            SELECT
                c.id AS chunk_id,
                c.file_id,
                c.doc_title,
                c.chunk_text,
                f.filename,
                COUNT(*) OVER (PARTITION BY c.file_id) AS total_chunks_in_file,
                ROW_NUMBER() OVER (PARTITION BY c.file_id ORDER BY c.id) AS chunk_index_in_file
            FROM chunks c
            JOIN files f ON c.file_id = f.id
            WHERE c.doc_title IN ({placeholders})
        """

        cursor.execute(query, doc_titles)
        rows = cursor.fetchall()

        # 构建doc_title到文档详情的映射
        result = {}
        for row in rows:
            result[row[2]] = {  # row[2] 是 doc_title
                "chunk_id": row[0],
                "file_id": row[1],
                "filename": row[4],
                "doc_title": row[2],
                "chunk_text": row[3],
                "total_chunks_in_file": row[5],
                "chunk_index_in_file": row[6]
            }

        # 对于未找到的doc_title，设置为None
        for title in doc_titles:
            if title not in result:
                result[title] = None

        return result

