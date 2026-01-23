"""
RRF重排序节点：使用RRF算法融合两路检索结果
"""
from typing import List, Dict, Any
from .state import State, SearchResult
from ..config import config


def rrf_fusion_two_way(
    bm25_results: List[SearchResult],
    vector_results: List[SearchResult],
    k: int = 60,
    bm25_weight: float = 0.5,
    vector_weight: float = 0.5,
) -> List[Dict[str, Any]]:
    """
    RRF (Reciprocal Rank Fusion) 算法融合两路检索结果

    Args:
        bm25_results: BM25检索结果（chunk_text词频）
        vector_results: 向量检索结果（embedding余弦相似度）
        k: RRF常数，控制排名影响的平滑程度
        bm25_weight: BM25检索权重
        vector_weight: 向量检索权重

    Returns:
        融合后的结果列表，按rrf_score降序排序
    """
    # 构建排名字典
    bm25_ranks = {
        item["doc_title"]: (rank + 1) for rank, item in enumerate(bm25_results)
    }
    vector_ranks = {
        item["doc_title"]: (rank + 1) for rank, item in enumerate(vector_results)
    }

    # 构建原始分数字典
    bm25_scores = {item["doc_title"]: item["score"] for item in bm25_results}
    vector_scores = {item["doc_title"]: item["score"] for item in vector_results}

    # 获取所有唯一的doc_title
    all_doc_titles = set(bm25_ranks.keys()) | set(vector_ranks.keys())

    # 计算RRF分数
    fused_results = []
    for doc_title in all_doc_titles:
        # RRF公式: 1/(k + rank)
        bm25_rrf = (
            (1.0 / (k + bm25_ranks[doc_title])) * bm25_weight
            if doc_title in bm25_ranks
            else 0
        )
        vector_rrf = (
            (1.0 / (k + vector_ranks[doc_title])) * vector_weight
            if doc_title in vector_ranks
            else 0
        )

        rrf_score = bm25_rrf + vector_rrf

        fused_results.append(
            {
                "doc_title": doc_title,
                "rrf_score": rrf_score,
                "bm25_rank": bm25_ranks.get(doc_title, None),
                "vector_rank": vector_ranks.get(doc_title, None),
                "bm25_score": bm25_scores.get(doc_title, None),
                "vector_score": vector_scores.get(doc_title, None),
            }
        )

    # 按rrf_score降序排序
    fused_results.sort(key=lambda x: x["rrf_score"], reverse=True)

    return fused_results


def rrf_rerank_node(state: State) -> State:
    """
    RRF重排序节点（两路融合）

    功能：
    1. 使用RRF算法融合两路检索结果：
       - bm25_results（chunk_text BM25）
       - vector_results（embedding余弦相似度）
    2. 去重（通过filename）
    3. 按RRF分数降序排序

    Args:
        state: 当前状态

    Returns:
        更新后的状态，包含fused_results
    """
    # 检查是否有错误
    if state.get("error"):
        return {}

    bm25_results = state.get("bm25_results", [])
    vector_results = state.get("vector_results", [])

    # 确保至少有一路检索结果
    if not bm25_results and not vector_results:
        return {
            "error": "缺少检索结果",
        }

    # 如果只有一路检索结果，也使用 RRF 公式保持分数量纲一致
    k = config.search.rrf_k

    if bm25_results and not vector_results:
        fused_results = [
            {
                "doc_title": item["doc_title"],
                "rrf_score": (1.0 / (k + i + 1)) * config.search.bm25_weight,
                "bm25_rank": i + 1,
                "vector_rank": None,
                "bm25_score": item["score"],
                "vector_score": None,
            }
            for i, item in enumerate(bm25_results)
        ]
        return {"fused_results": fused_results}

    if vector_results and not bm25_results:
        fused_results = [
            {
                "doc_title": item["doc_title"],
                "rrf_score": (1.0 / (k + i + 1)) * config.search.vector_weight,
                "bm25_rank": None,
                "vector_rank": i + 1,
                "bm25_score": None,
                "vector_score": item["score"],
            }
            for i, item in enumerate(vector_results)
        ]
        return {"fused_results": fused_results}

    # 使用RRF算法融合两路结果
    fused_results = rrf_fusion_two_way(
        bm25_results,
        vector_results,
        k=config.search.rrf_k,
        bm25_weight=config.search.bm25_weight,
        vector_weight=config.search.vector_weight,
    )

    return {"fused_results": fused_results}
