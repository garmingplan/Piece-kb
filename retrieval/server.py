"""
SQLite检索MCP服务 - 主入口文件
基于FastMCP实现的智能知识检索服务，提供两个核心工具：
1. resolve-keywords: 智能关键词解析（三路检索+RRF重排，返回20个关键词）
2. get-docs: 精确文档获取（最多接受3个关键词）
"""

import json
from fastmcp import FastMCP, Context
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.server.dependencies import get_http_headers
from fastmcp.exceptions import ToolError
from typing import List, Annotated, Union, Optional
from pydantic import Field

from .tools import resolve_database_keywords, get_docs
from indexing.settings import get_mcp_api_key, is_mcp_auth_enabled


class BearerAuthMiddleware(Middleware):
    """Bearer Token 认证中间件"""

    def __init__(self, valid_token: str):
        self.valid_token = valid_token

    def _verify_token(self) -> bool:
        """验证 Bearer Token"""
        headers = get_http_headers() or {}
        auth_header = headers.get("authorization", "")

        if not auth_header.startswith("Bearer "):
            return False

        token = auth_header[7:]  # 去掉 "Bearer " 前缀
        return token == self.valid_token

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        if not self._verify_token():
            raise ToolError("Unauthorized: Invalid or missing API key")
        return await call_next(context)

    async def on_list_tools(self, context: MiddlewareContext, call_next):
        if not self._verify_token():
            raise ToolError("Unauthorized: Invalid or missing API key")
        return await call_next(context)


# 创建FastMCP服务实例
# FastMCP 2.14.0+ 支持 strict_input_validation 参数
# 设置为 False 启用灵活验证模式，自动转换字符串参数（如 "5" -> 5）
mcp = FastMCP(
    name="piece-kb",
    instructions="Piece searches user's personal documents. Call resolve-keywords to find relevant documents, then get-docs to retrieve content.",
    strict_input_validation=False,
)

# 如果启用认证，添加认证中间件
if is_mcp_auth_enabled():
    api_key = get_mcp_api_key()
    mcp.add_middleware(BearerAuthMiddleware(valid_token=api_key))


@mcp.tool(
    name="resolve-keywords",
    description="Resolves queries to relevant document keywords (doc_title). Returns up to 20 keyword candidates with confidence scores. IMPORTANT: When user mentions a specific book, document, or file name (e.g., 'find in the Python book', 'from my ML notes'), you SHOULD use the filenames parameter to narrow search scope for more accurate results.",
    tags={"retrieval", "keywords"},
)
async def resolve_keywords_tool(
    ctx: Context,
    query: Annotated[
        str, Field(description="Query text to search for relevant documents")
    ],
    filenames: Annotated[
        Optional[Union[List[str], str]],
        Field(description="Filter search to specific files. USE THIS when user mentions a book/document name. Supports fuzzy match - no need for exact filename or extension. Example: 'machine learning' matches 'machine learning.md', 'machine learning notes.md', etc. Just extract the key name from user's query.")
    ] = None,
    max_results: Annotated[
        int,
        Field(
            description="Maximum number of keywords to return (default: 20, range: 1-50)"
        ),
    ] = 20,
) -> dict:
    # 处理字符串形式的列表（某些模型会传递 '["name1","name2"]' 而不是 ["name1","name2"]）
    if isinstance(filenames, str):
        try:
            filenames = json.loads(filenames)
        except json.JSONDecodeError:
            # 单个文件名字符串，转为列表
            filenames = [filenames] if filenames else None

    await ctx.info(f"[Tool 1] Resolving query: {query}, max_results: {max_results}, filenames: {filenames}")

    try:
        # 调用核心工作流（传递可选的文件名过滤）
        result = await resolve_database_keywords(query, filenames=filenames)

        keywords = result.get("keywords", [])
        # 如果需要，可以根据max_results截断结果
        if max_results and max_results < len(keywords):
            keywords = keywords[:max_results]
            result["keywords"] = keywords
            await ctx.info(f"[Tool 1] Truncated to max_results={max_results}")

        await ctx.info(f"[Tool 1] Resolved {len(keywords)} keywords")

        # 通过 ctx.info() 输出调试信息（不返回给 AI 客户端）
        debug_stats = result.pop("debug_stats", {})
        file_ids_filter = debug_stats.get("file_ids_filter")
        await ctx.info(
            f"[Tool 1] Debug - Query: {debug_stats.get('query', '')}, "
            f"Cleaned: {debug_stats.get('cleaned_query', '')}, "
            f"Tokens: {debug_stats.get('tokens', [])}"
        )
        await ctx.info(
            f"[Tool 1] Stats - Title: {debug_stats.get('exact_recall_count', 0)}, "
            f"BM25: {debug_stats.get('bm25_recall_count', 0)}, "
            f"Vector: {debug_stats.get('vector_recall_count', 0)}, "
            f"Fused: {result.get('stats', {}).get('total_fused_results', 0)}, "
            f"FileFilter: {file_ids_filter if file_ids_filter else 'None (global)'}"
        )

        # 返回精简结果（不包含 debug_stats）
        return result

    except Exception as e:
        await ctx.error(f"[Tool 1] Failed: {str(e)}")
        raise


@mcp.tool(
    name="get-docs",
    description="Retrieves full document content and metadata for specified doc_titles (up to 3). Returns chunk_id, file_id, filename, chunk_text, total_chunks_in_file, and chunk_index_in_file for each document. Input exact doc_title strings from resolve-keywords results.",
    tags={"docs", "retrieval"},
)
async def get_docs_tool(
    ctx: Context,
    doc_titles: Annotated[
        Union[List[str], str], Field(description="List of doc_titles to retrieve (max 3), supports list or JSON string")
    ],
    include_metadata: Annotated[
        bool,
        Field(description="Include document metadata in response (default: false)"),
    ] = False,
    max_docs: Annotated[
        int,
        Field(
            description="Maximum number of documents to retrieve (default: 3, max: 3)"
        ),
    ] = 3,
) -> dict:
    # 处理字符串形式的列表（某些模型会传递 '["title1","title2"]' 而不是 ["title1","title2"]）
    if isinstance(doc_titles, str):
        try:
            doc_titles = json.loads(doc_titles)
        except json.JSONDecodeError:
            await ctx.error(f"[Tool 2] Invalid doc_titles format: {doc_titles}")
            return {
                "documents": {},
                "not_found": [],
                "error": f"Invalid doc_titles format. Expected JSON array like [\"title1\", \"title2\"], got: {repr(doc_titles)}"
            }

    # 限制最多3个doc_title
    limit = min(max_docs, 3) if max_docs else 3
    if len(doc_titles) > limit:
        await ctx.warning(
            f"[Tool 2] Truncated {len(doc_titles)} doc_titles to top {limit}"
        )
        doc_titles = doc_titles[:limit]

    await ctx.info(
        f"[Tool 2] Retrieving {len(doc_titles)} documents, include_metadata: {include_metadata}"
    )

    try:
        # 调用文档获取函数（同步函数）
        docs_mapping = get_docs(doc_titles)

        # 分离找到的和未找到的
        documents = {}
        not_found = []

        for title in doc_titles:
            doc_info = docs_mapping.get(title)
            if doc_info is not None:
                documents[title] = doc_info
            else:
                not_found.append(title)

        await ctx.info(
            f"[Tool 2] Completed - Found: {len(documents)}, Not found: {len(not_found)}"
        )

        if not_found:
            await ctx.warning(f"[Tool 2] Doc titles not found: {', '.join(not_found)}")

        result = {"documents": documents, "not_found": not_found}

        # 如果需要元数据，可以在这里添加
        if include_metadata:
            result["metadata"] = {
                "total_requested": len(doc_titles),
                "total_found": len(documents),
                "total_not_found": len(not_found),
            }
            await ctx.info(f"[Tool 2] Metadata included")

        # 直接返回纯数据，让FastMCP自动序列化为结构化JSON
        return result

    except Exception as e:
        await ctx.error(f"[Tool 2] Failed: {str(e)}")
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
