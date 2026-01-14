"""
LangGraph状态管理类：管理查询文本、向量、检索结果等数据
"""
from typing import List, Optional, Dict, Any, Annotated
from typing_extensions import TypedDict


class SearchResult(TypedDict):
    """检索结果"""
    doc_title: str
    score: float


class State(TypedDict):
    """LangGraph工作流状态 - 两路检索架构"""
    # 输入
    query: str  # 用户查询文本
    filenames: Optional[List[str]]  # 限定检索的文件名列表（可选，模糊匹配）

    # 预处理
    cleaned_query: Optional[str]  # 清洗后的查询文本
    tokens: Optional[List[str]]  # 分词结果
    file_ids: Optional[List[int]]  # 解析后的文件ID列表（用于过滤检索）

    # 向量化
    query_embedding: Optional[List[float]]  # 查询向量

    # 两路检索结果（使用Annotated处理并行更新）
    bm25_results: Annotated[Optional[List[SearchResult]], lambda x, y: y if y is not None else x]  # BM25检索结果（chunk_text词频）
    vector_results: Annotated[Optional[List[SearchResult]], lambda x, y: y if y is not None else x]  # 向量检索结果（embedding余弦相似度）

    # 重排序结果
    fused_results: Optional[List[Dict[str, Any]]]  # RRF融合后的结果（两路）

    # 最终输出
    final_keywords: Optional[List[str]]  # 最终关键词列表（doc_title）
    confidence_scores: Optional[Dict[str, float]]  # 置信度分数
    stats: Optional[Dict[str, Any]]  # 检索统计信息

    # 错误信息
    error: Annotated[Optional[str], lambda x, y: y if y is not None else x]  # 错误信息
