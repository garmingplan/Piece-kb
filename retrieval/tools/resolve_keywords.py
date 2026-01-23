"""
工具1: resolve-database-keywords
根据用户查询解析出相关的数据库关键词（doc_title）
使用 LangGraph 工作流实现三路检索 + RRF 重排序
"""
from typing import Dict, Any, List, Optional
from langgraph.graph import StateGraph, END

from ..nodes import (
    State,
    preprocess_node,
    exact_match_node,
    vector_search_node,
    bm25_search_node,
    rrf_rerank_node,
    output_node,
)


def build_graph():
    """
    构建LangGraph工作流（三路检索架构）

    流程：
    1. preprocess_node - 查询预处理（清洗、jieba分词）
    2. exact_match_node + bm25_search_node + vector_search_node - 并行三路检索
       - exact_match_node: doc_title字段LIKE精确匹配
       - bm25_search_node: chunk_text字段FTS5 BM25词频检索
       - vector_search_node: embedding字段sqlite-vec余弦相似度
    3. rrf_rerank_node - RRF重排序融合（三路）
    4. output_node - 结果输出格式化

    Returns:
        编译后的工作流图
    """
    # 创建StateGraph
    workflow = StateGraph(State)

    # 添加节点
    workflow.add_node("preprocess", preprocess_node)
    workflow.add_node("exact_match", exact_match_node)
    workflow.add_node("bm25_search", bm25_search_node)
    workflow.add_node("vector_search", vector_search_node)
    workflow.add_node("rrf_rerank", rrf_rerank_node)
    workflow.add_node("output", output_node)

    # 设置入口点
    workflow.set_entry_point("preprocess")

    # 添加边：preprocess -> 并行执行三路检索
    workflow.add_edge("preprocess", "exact_match")
    workflow.add_edge("preprocess", "bm25_search")
    workflow.add_edge("preprocess", "vector_search")

    # 添加边：三路检索 -> RRF重排序
    workflow.add_edge("exact_match", "rrf_rerank")
    workflow.add_edge("bm25_search", "rrf_rerank")
    workflow.add_edge("vector_search", "rrf_rerank")

    # 添加边：RRF重排序 -> 结果输出
    workflow.add_edge("rrf_rerank", "output")

    # 添加边：结果输出 -> END
    workflow.add_edge("output", END)

    # 编译图
    return workflow.compile()


async def resolve_database_keywords(
    query: str,
    filenames: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    根据查询解析数据库关键词（三路检索架构）

    Args:
        query: 用户查询文本
        filenames: 限定检索的文件名列表（可选，模糊匹配）

    Returns:
        {
            "keywords": ["doc_title_1", "doc_title_2", ...],  # 精选的关键词列表
            "confidence_scores": {"doc_title_1": 0.95, ...},  # 置信度分数
            "stats": {  # 精简的统计信息
                "total_fused_results": 20,   # RRF融合后总数
                "final_top_k": 20,           # 最终返回数量
            },
            "debug_stats": {  # 调试信息（不返回给 AI 客户端）
                "query": "原始查询",
                "cleaned_query": "清洗后查询",
                "tokens": ["分词1", "分词2"],
                "exact_recall_count": 5,
                "bm25_recall_count": 10,
                "vector_recall_count": 10,
                "file_ids_filter": [1, 2],
            }
        }
    """
    # 构建工作流
    graph = build_graph()

    # 初始化状态（三路检索架构）
    initial_state: State = {
        "query": query,
        "filenames": filenames,  # 可选的文件名过滤
        "cleaned_query": None,
        "tokens": None,
        "file_ids": None,  # 由 preprocess_node 解析
        "query_embedding": None,
        "exact_results": None,    # 精确匹配检索结果
        "bm25_results": None,     # chunk_text BM25检索结果
        "vector_results": None,   # embedding向量检索结果
        "fused_results": None,
        "final_keywords": None,
        "confidence_scores": None,
        "stats": None,
        "debug_stats": None,
        "error": None,
    }

    # 执行工作流
    final_state = await graph.ainvoke(initial_state)

    # 检查错误
    if final_state.get("error"):
        raise Exception(final_state["error"])

    # 返回结果（精简版，调试信息由 server.py 通过 ctx.info() 输出）
    return {
        "keywords": final_state.get("final_keywords", []),
        "confidence_scores": final_state.get("confidence_scores", {}),
        "stats": final_state.get("stats", {}),
        "debug_stats": final_state.get("debug_stats", {}),  # 调试信息，由 server.py 处理
    }
