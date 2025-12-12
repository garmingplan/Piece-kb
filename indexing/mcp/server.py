"""
索引 MCP 服务主入口 (piece-index)

基于 FastMCP 实现的文件和切片管理服务。
"""

import logging
from fastmcp import FastMCP

from indexing.mcp.tools.file_tools import create_empty_file, delete_file
from indexing.mcp.tools.chunk_tools import (
    create_chunk,
    update_chunk_content,
    delete_chunk,
)
from indexing.mcp.tools.task_tools import get_task_status

logger = logging.getLogger(__name__)

# 创建 FastMCP 实例
mcp = FastMCP(
    "piece-index",
    instructions="""
Piece 索引 MCP 服务 - 用户个人知识库文件和切片管理工具

注意：add_chunk 需要文件 ID，如果文件不存在请先使用 create_file 创建。
""",
)


# ==================== 文件管理工具 ====================


@mcp.tool()
def create_file(filename: str) -> dict:
    """
    创建空白 Markdown 文件

    Args:
        filename: 文件名（自动补充 .md 后缀，处理重名冲突）

    Returns:
        包含文件信息的字典：
        - success: 是否成功
        - message: 结果消息
        - data: 文件数据（file_id, filename, file_path, status）

    Example:
        创建一个名为"学术论文_2024研究"的空文件：
        >>> create_file("学术论文_2024研究")
    """
    logger.info(f"[MCP Tool] create_file: filename={filename}")
    return create_empty_file(filename)


@mcp.tool()
def remove_file(file_id: int) -> dict:
    """
    删除文件（级联删除所有切片和物理文件）

    Args:
        file_id: 文件 ID

    Returns:
        包含删除结果的字典：
        - success: 是否成功
        - message: 结果消息
        - data: 删除信息（file_id, filename, deleted_chunks）

    Example:
        删除 ID 为 123 的文件：
        >>> remove_file(123)
    """
    logger.info(f"[MCP Tool] remove_file: file_id={file_id}")
    return delete_file(file_id)


# ==================== 切片管理工具 ====================


@mcp.tool()
def add_chunk(file_id: int, doc_title: str, chunk_text: str) -> dict:
    """
    新增切片（异步生成向量）

    Args:
        file_id: 文件 ID
        doc_title: 文档标题（用于一阶段检索返回目标）
        chunk_text: 切片文本内容

    Returns:
        包含切片信息的字典：
        - success: 是否成功
        - message: 结果消息
        - data: 切片数据（task_id, doc_title, chunk_text）
          注意：task_id 是异步任务ID，不是 chunk_id
          切片创建后会异步生成向量，chunk 在向量生成完成后才会被创建

    Workflow:
        1. 调用 add_chunk() 创建切片，返回 task_id
        2. 使用 check_task_status(task_id) 轮询任务状态
        3. 任务完成后，切片已创建并可以通过检索 MCP 查询
        4. 如需修改切片，必须等任务完成后才能获取 chunk_id

    Example:
        为文件 123 添加一个切片：
        >>> result = add_chunk(
        ...     file_id=123,
        ...     doc_title="论文_摘要",
        ...     chunk_text="本文提出了一种新的方法..."
        ... )
        >>> task_id = result["data"]["task_id"]
        >>> # 轮询任务状态
        >>> check_task_status(task_id)
        >>> # 任务完成后，切片已创建

    Note:
        - 返回的 task_id 用于查询向量生成进度，不是 chunk_id
        - 切片在向量生成完成后才会被写入数据库
        - 如需后续操作（修改/删除），请等待任务完成后通过检索工具查询 chunk_id
    """
    logger.info(
        f"[MCP Tool] add_chunk: file_id={file_id}, " f"doc_title={doc_title[:50]}..."
    )
    return create_chunk(file_id, doc_title, chunk_text)


@mcp.tool()
def modify_chunk_content(chunk_id: int, new_content: str) -> dict:
    """
    修改切片内容（异步重新生成向量）

    Args:
        chunk_id: 切片 ID（注意：不是 task_id，是已存在的切片ID）
        new_content: 新的切片文本内容

    Returns:
        包含更新结果的字典：
        - success: 是否成功
        - message: 结果消息
        - data: 更新信息（chunk_id, task_id, new_content）
          注意：task_id 是异步任务ID，用于查询向量重新生成进度

    Workflow:
        1. 调用 modify_chunk_content(chunk_id, new_content) 修改内容
        2. 使用返回的 task_id 通过 check_task_status() 监控向量生成
        3. 任务完成后，切片内容和向量都已更新

    Example:
        修改切片 456 的内容：
        >>> result = modify_chunk_content(456, "更详细的描述...")
        >>> task_id = result["data"]["task_id"]
        >>> # 轮询任务状态
        >>> check_task_status(task_id)

    Note:
        - chunk_id 必须是已存在的切片ID（通过检索 MCP 查询获得）
        - 修改内容后会异步重新生成向量，可通过返回的 task_id 查询进度
        - 不要将 add_chunk 返回的 task_id 用作 chunk_id
    """
    logger.info(
        f"[MCP Tool] modify_chunk_content: chunk_id={chunk_id}, "
        f"new_content={new_content[:50]}..."
    )
    return update_chunk_content(chunk_id, new_content)


@mcp.tool()
def remove_chunk(chunk_id: int) -> dict:
    """
    删除切片（同步删除向量）

    Args:
        chunk_id: 切片 ID

    Returns:
        包含删除结果的字典：
        - success: 是否成功
        - message: 结果消息
        - data: 删除信息（chunk_id, doc_title, file_deleted）

    Example:
        删除切片 456：
        >>> remove_chunk(456)

    Note:
        如果删除的是文件的最后一个切片，文件会被自动删除。
    """
    logger.info(f"[MCP Tool] remove_chunk: chunk_id={chunk_id}")
    return delete_chunk(chunk_id)


# ==================== 任务管理工具 ====================


@mcp.tool()
def check_task_status(task_id: int) -> dict:
    """
    查询任务状态（用于监控异步向量生成任务）

    Args:
        task_id: 任务 ID

    Returns:
        包含任务状态的字典：
        - success: 是否成功
        - message: 结果消息
        - data: 任务数据（task_id, status, progress, chunk_id, error_message等）
          重要：任务完成后会返回 chunk_id（新创建或修改的切片ID）

    Example:
        查询任务 789 的状态：
        >>> result = check_task_status(789)
        >>> if result["data"]["status"] == "completed":
        ...     chunk_id = result["data"]["chunk_id"]  # 获取切片ID
        ...     # 现在可以使用 chunk_id 进行后续操作

    Note:
        - 任务状态包括：pending（待处理）、processing（处理中）、
          completed（已完成）、failed（失败）
        - 任务完成（status="completed"）后，data.chunk_id 会返回创建的切片ID
        - 可以使用返回的 chunk_id 调用 modify_chunk_content 或 remove_chunk
    """
    logger.info(f"[MCP Tool] check_task_status: task_id={task_id}")
    return get_task_status(task_id)


# ==================== 服务信息 ====================


def get_server_info() -> dict:
    """获取服务信息"""
    return {
        "name": "piece-index",
        "version": "0.1.0",
        "description": "Piece 索引 MCP 服务 - 提供文件和切片的 CRUD 操作",
        "tools": [
            "create_file",
            "remove_file",
            "add_chunk",
            "modify_chunk_content",
            "remove_chunk",
            "check_task_status",
        ],
    }


if __name__ == "__main__":
    logger.info("[MCP] 启动 piece-index 服务...")
    logger.info(f"[MCP] 服务信息: {get_server_info()}")
    mcp.run()
