"""
查询预处理节点：文本清洗、格式验证、分词、状态初始化
"""
import jieba
from .state import State
from ..config import config


def tokenize_query(query: str) -> list[str]:
    """
    使用jieba分词提取关键词

    Args:
        query: 用户输入的查询问题

    Returns:
        分词后的token列表
    """
    # 使用jieba搜索引擎模式分词（会额外切分长词）
    tokens = list(jieba.cut_for_search(query))

    # 过滤停用词和单字符
    tokens = [
        t.strip()
        for t in tokens
        if len(t.strip()) > 1 and t.strip() not in config.search.stopwords
    ]

    # 去重并按长度降序排序（优先匹配长词）
    tokens = sorted(list(set(tokens)), key=len, reverse=True)

    return tokens


def preprocess_node(state: State) -> State:
    """
    查询预处理节点

    功能：
    1. 文本清洗（去除多余空白）
    2. 格式验证（检查是否为空）
    3. jieba分词
    4. 状态初始化

    Args:
        state: 当前状态

    Returns:
        更新后的状态
    """
    query = state["query"]

    # 文本清洗：去除多余空白
    cleaned_query = " ".join(query.strip().split())

    # 格式验证
    if not cleaned_query:
        return {
            "error": "查询文本不能为空",
        }

    # jieba分词
    tokens = tokenize_query(cleaned_query)

    if not tokens:
        return {
            "error": "未提取到有效关键词",
            "cleaned_query": cleaned_query,
        }

    # 更新状态
    return {
        "cleaned_query": cleaned_query,
        "tokens": tokens,
    }
