"""
工具1: resolve-database-keywords
根据用户查询解析出相关的数据库关键词（doc_title）
使用 LangGraph 工作流实现两路检索 + RRF 重排序
"""
from typing import Dict, Any
from langgraph.graph import StateGraph, END

from ..nodes import (
    State,
    preprocess_node,
    vector_search_node,
    bm25_search_node,
    rrf_rerank_node,
    output_node,
)


def build_graph():
    """
    构建LangGraph工作流（两路检索架构）

    流程：
    1. preprocess_node - 查询预处理（清洗、jieba分词）
    2. bm25_search_node + vector_search_node - 并行两路检索
       - bm25_search_node: chunk_text字段FTS5 BM25词频检索
       - vector_search_node: embedding字段sqlite-vec余弦相似度
    3. rrf_rerank_node - RRF重排序融合（两路）
    4. output_node - 结果输出格式化

    Returns:
        编译后的工作流图
    """
    # 创建StateGraph
    workflow = StateGraph(State)

    # 添加节点
    workflow.add_node("preprocess", preprocess_node)
    workflow.add_node("bm25_search", bm25_search_node)
    workflow.add_node("vector_search", vector_search_node)
    workflow.add_node("rrf_rerank", rrf_rerank_node)
    workflow.add_node("output", output_node)

    # 设置入口点
    workflow.set_entry_point("preprocess")

    # 添加边：preprocess -> 并行执行两路检索
    workflow.add_edge("preprocess", "bm25_search")
    workflow.add_edge("preprocess", "vector_search")

    # 添加边：两路检索 -> RRF重排序
    workflow.add_edge("bm25_search", "rrf_rerank")
    workflow.add_edge("vector_search", "rrf_rerank")

    # 添加边：RRF重排序 -> 结果输出
    workflow.add_edge("rrf_rerank", "output")

    # 添加边：结果输出 -> END
    workflow.add_edge("output", END)

    # 编译图
    return workflow.compile()


async def resolve_database_keywords(query: str) -> Dict[str, Any]:
    """
    根据查询解析数据库关键词（两路检索架构）

    Args:
        query: 用户查询文本

    Returns:
        {
            "keywords": ["doc_title_1", "doc_title_2", ...],  # 精选的关键词列表
            "confidence_scores": {"doc_title_1": 0.95, ...},  # 置信度分数
            "stats": {  # 检索统计信息
                "query": "原始查询",
                "cleaned_query": "清洗后查询",
                "tokens": ["分词1", "分词2"],
                "bm25_recall_count": 10,     # BM25检索召回数
                "vector_recall_count": 10,   # 向量检索召回数
                "total_fused_results": 20    # RRF融合后总数
            }
        }
    """
    # 构建工作流
    graph = build_graph()

    # 初始化状态（两路检索架构）
    initial_state: State = {
        "query": query,
        "cleaned_query": None,
        "tokens": None,
        "query_embedding": None,
        "bm25_results": None,     # chunk_text BM25检索结果
        "vector_results": None,   # embedding向量检索结果
        "fused_results": None,
        "final_keywords": None,
        "confidence_scores": None,
        "stats": None,
        "error": None,
    }

    # 执行工作流
    final_state = await graph.ainvoke(initial_state)

    # 检查错误
    if final_state.get("error"):
        raise Exception(final_state["error"])

    # 返回结果
    return {
        "keywords": final_state.get("final_keywords", []),
        "confidence_scores": final_state.get("confidence_scores", {}),
        "stats": final_state.get("stats", {}),
    }
