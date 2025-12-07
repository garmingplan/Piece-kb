"""
SQLite检索MCP服务 - 主入口文件
基于FastMCP实现的智能知识检索服务，提供两个核心工具：
1. resolve-keywords: 智能关键词解析（两路检索+RRF重排，返回20个关键词）
2. get-docs: 精确文档获取（最多接受3个关键词）
"""

from fastmcp import FastMCP, Context
from typing import List, Annotated
from pydantic import Field

from .tools import resolve_database_keywords, get_docs

# 创建FastMCP服务实例
mcp = FastMCP(
    name="piece-kb",
    instructions="Piece - Personal knowledge base retrieval service. First call resolve-keywords to find relevant documents, then call get-docs with selected keywords to retrieve content.",
)


@mcp.tool(
    name="resolve-keywords",
    description="Resolves queries to relevant document keywords (doc_title). Returns up to 20 keyword candidates with confidence scores. Select keywords based on relevance to user's specific question, not solely by score ranking.",
    tags={"retrieval", "keywords"},
)
async def resolve_keywords_tool(
    ctx: Context,
    query: Annotated[str, Field(description="Query text to search for relevant documents")],
    max_results: Annotated[int, Field(description="Maximum number of keywords to return (default: 20, range: 1-50)")] = 20
) -> dict:
    await ctx.info(f"[工具1] 开始解析查询: {query}, max_results: {max_results}")

    try:
        # 调用核心工作流
        result = await resolve_database_keywords(query)

        keywords = result.get("keywords", [])
        # 如果需要，可以根据max_results截断结果
        if max_results and max_results < len(keywords):
            keywords = keywords[:max_results]
            result["keywords"] = keywords
            await ctx.info(f"[工具1] 已根据max_results={max_results}截断结果")

        await ctx.info(f"[工具1] 解析完成，返回 {len(keywords)} 个关键词")

        # 输出关键统计信息
        stats = result.get("stats", {})
        await ctx.info(
            f"[工具1] 检索统计 - BM25召回: {stats.get('bm25_recall_count', 0)}, "
            f"向量召回: {stats.get('vector_recall_count', 0)}, "
            f"融合后: {stats.get('total_fused_results', 0)}"
        )

        # 直接返回纯数据，让FastMCP自动序列化为结构化JSON
        return result

    except Exception as e:
        await ctx.error(f"[工具1] 解析失败: {str(e)}")
        raise


@mcp.tool(
    name="get-docs",
    description="Retrieves full document content for specified doc_titles (up to 3). Input exact doc_title strings from resolve-keywords results.",
    tags={"docs", "retrieval"},
)
async def get_docs_tool(
    ctx: Context,
    doc_titles: Annotated[List[str], Field(description="List of doc_titles to retrieve (max 3)")],
    include_metadata: Annotated[bool, Field(description="Include document metadata in response (default: false)")] = False,
    max_docs: Annotated[int, Field(description="Maximum number of documents to retrieve (default: 3, max: 3)")] = 3
) -> dict:
    # 限制最多3个doc_title
    limit = min(max_docs, 3) if max_docs else 3
    if len(doc_titles) > limit:
        await ctx.warning(f"[工具2] 传入了 {len(doc_titles)} 个doc_title，已自动截断为前{limit}个")
        doc_titles = doc_titles[:limit]

    await ctx.info(f"[工具2] 开始获取 {len(doc_titles)} 个文档, include_metadata: {include_metadata}")

    try:
        # 调用文档获取函数（同步函数）
        docs_mapping = get_docs(doc_titles)

        # 分离找到的和未找到的
        documents = {}
        not_found = []

        for title in doc_titles:
            content = docs_mapping.get(title)
            if content is not None:
                documents[title] = content
            else:
                not_found.append(title)

        await ctx.info(
            f"[工具2] 获取完成 - 成功: {len(documents)}, 未找到: {len(not_found)}"
        )

        if not_found:
            await ctx.warning(f"[工具2] 以下doc_title未找到文档: {', '.join(not_found)}")

        result = {"documents": documents, "not_found": not_found}

        # 如果需要元数据，可以在这里添加
        if include_metadata:
            result["metadata"] = {
                "total_requested": len(doc_titles),
                "total_found": len(documents),
                "total_not_found": len(not_found)
            }
            await ctx.info(f"[工具2] 已添加元数据信息")

        # 直接返回纯数据，让FastMCP自动序列化为结构化JSON
        return result

    except Exception as e:
        await ctx.error(f"[工具2] 获取文档失败: {str(e)}")
        raise


# 服务启动入口
if __name__ == "__main__":
    """
    运行MCP服务

    支持的传输方式：
    - "stdio": 标准输入输出（Claude Desktop）
    - "streamable-http": Streamable HTTP（推荐，支持双向流式通信）
    - "sse": Server-Sent Events（兼容模式）

    CherryStudio配置：
    - 类型：可流式传输的 HTTP (StreamableHttp)
    - URL：http://127.0.0.1:8000/mcp

    注意：推荐使用 run_http_server.py 启动HTTP服务
    """
    # 使用Streamable HTTP传输模式
    mcp.run(
        transport="streamable-http",
        host="127.0.0.1",
        port=8000,
        path="/mcp",
    )
