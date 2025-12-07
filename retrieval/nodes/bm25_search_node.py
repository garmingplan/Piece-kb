"""
BM25检索节点：使用SQLite FTS5对chunk_text字段进行全文检索
专门用于长文本内容的词频检索
"""
from typing import List
from .state import State, SearchResult
from ..db import get_connection
from ..config import config


def bm25_search_node(state: State) -> dict:
    """
    BM25检索节点（SQLite FTS5）

    功能：
    1. 使用预处理节点生成的tokens
    2. 使用SQLite FTS5对chunk_text字段进行全文检索
    3. 利用FTS5内置的BM25算法计算相关性分数
    4. 返回按BM25分数排序的Top-K结果

    适用场景：长文本内容的词频检索

    Args:
        state: 当前状态

    Returns:
        更新后的状态，包含bm25_results
    """
    # 检查是否有错误
    if state.get("error"):
        return {}

    tokens = state.get("tokens")
    if not tokens:
        return {
            "error": "缺少分词结果",
        }

    try:
        # 连接数据库
        conn = get_connection()

        try:
            # 构建FTS5查询语句
            # 使用OR连接多个词，实现宽松匹配
            query_str = " OR ".join(tokens)

            # 使用FTS5的bm25()函数获取相关性分数
            # bm25()返回负值，值越小表示相关性越高，所以取负数变为正值
            # 注意：chunks_fts的rowid对应chunks表的id
            query_sql = """
                SELECT DISTINCT
                    c.doc_title,
                    -bm25(chunks_fts) AS bm25_score
                FROM chunks_fts
                JOIN chunks c ON chunks_fts.rowid = c.id
                WHERE chunks_fts MATCH ?
                ORDER BY bm25_score DESC
                LIMIT ?
            """

            # 执行查询
            cursor = conn.execute(query_sql, (query_str, config.search.bm25_top_k))
            rows = cursor.fetchall()

            # 转换为SearchResult列表
            bm25_results: List[SearchResult] = [
                {"doc_title": row[0], "score": float(row[1])}
                for row in rows
            ]

            return {
                "bm25_results": bm25_results,
            }

        finally:
            conn.close()

    except Exception as e:
        return {
            "error": f"BM25检索失败: {str(e)}",
        }
