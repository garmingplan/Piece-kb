"""
结果输出节点：格式化关键词列表、置信度分数和检索统计
"""
from typing import List, Dict, Any
from .state import State
from ..config import config


def output_node(state: State) -> State:
    """
    结果输出节点（三路检索架构）

    功能：
    1. 从融合结果中提取Top-K关键词
    2. 标记精确匹配命中的 doc_title
    3. 生成置信度分数字典
    4. 生成三路检索统计信息

    Args:
        state: 当前状态

    Returns:
        更新后的状态
    """
    # 检查是否有错误
    if state.get("error"):
        return {}

    fused_results = state.get("fused_results")
    if not fused_results:
        return {
            "error": "缺少融合结果",
        }

    # 取Top-K结果
    top_k_results = fused_results[: config.search.final_top_k]

    # 提取关键词列表（doc_title）
    final_keywords: List[str] = [result["doc_title"] for result in top_k_results]

    # 标记标题检索路径命中的 doc_title（exact_rank 不为 None 的结果）
    title_matches: List[str] = [
        result["doc_title"]
        for result in top_k_results
        if result.get("exact_rank") is not None
    ]

    # 生成置信度分数字典（归一化到 0-1 范围，裁剪到 4 位小数）
    # RRF 理论最大值 = 1 / (k + 1)，归一化后分数更直观
    max_rrf = 1.0 / (config.search.rrf_k + 1)
    confidence_scores: Dict[str, float] = {
        result["doc_title"]: round(result["rrf_score"] / max_rrf, 4)
        for result in top_k_results
    }

    # 生成三路检索统计信息
    exact_results = state.get("exact_results", [])
    bm25_results = state.get("bm25_results", [])
    vector_results = state.get("vector_results", [])

    stats: Dict[str, Any] = {
        "total_fused_results": len(fused_results),
        "final_top_k": len(final_keywords),
        "exact_recall_count": len(exact_results),     # 精确匹配召回数
        "bm25_recall_count": len(bm25_results),       # chunk_text BM25召回数
        "vector_recall_count": len(vector_results),   # embedding向量召回数
        "query": state.get("query", ""),
        "cleaned_query": state.get("cleaned_query", ""),
        "tokens": state.get("tokens", []),
        "file_ids_filter": state.get("file_ids"),     # 实际生效的文件ID过滤（None表示全局检索）
    }

    return {
        "final_keywords": final_keywords,
        "title_matches": title_matches,
        "confidence_scores": confidence_scores,
        "stats": stats,
    }
