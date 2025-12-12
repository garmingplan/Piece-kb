"""
任务管理工具

提供异步任务状态查询功能。
"""
import logging
from typing import Dict, Any

from indexing.services.task_service import get_task

logger = logging.getLogger(__name__)


def get_task_status(task_id: int) -> Dict[str, Any]:
    """
    查询任务状态（用于监控异步向量生成任务）

    Args:
        task_id: 任务 ID

    Returns:
        {
            "success": bool,
            "message": str,
            "data": {
                "task_id": int,
                "status": str,  # "pending" | "processing" | "completed" | "failed"
                "progress": int,  # 0-100
                "original_filename": str,
                "error_message": str | None,
                "chunk_id": int | None,  # 任务完成后返回创建的切片ID
                "created_at": str,
                "updated_at": str
            }
        }

    Example:
        >>> get_task_status(789)
        {
            "success": True,
            "message": "任务查询成功",
            "data": {
                "task_id": 789,
                "status": "completed",
                "progress": 100,
                "original_filename": "学术论文_2024研究.md",
                "error_message": None,
                "chunk_id": 456,  # 任务完成后返回
                "created_at": "2025-12-12T10:30:00",
                "updated_at": "2025-12-12T10:30:15"
            }
        }
    """
    try:
        # 调用业务逻辑层
        task_info = get_task(task_id)

        if task_info:
            # 解析 error_message 中的 chunk_id（格式: "CHUNK_ID:123"）
            chunk_id = None
            error_message = task_info.get("error_message", "")

            if error_message and error_message.startswith("CHUNK_ID:"):
                try:
                    chunk_id = int(error_message.split(":")[1])
                    error_message = None  # 清除内部数据，不暴露给客户端
                except (IndexError, ValueError):
                    pass

            logger.info(
                f"[MCP] 查询任务状态: task_id={task_id}, "
                f"status={task_info['status']}, progress={task_info['progress']}%, "
                f"chunk_id={chunk_id}"
            )
            return {
                "success": True,
                "message": "任务查询成功",
                "data": {
                    "task_id": task_info["id"],
                    "status": task_info["status"],
                    "progress": task_info["progress"],
                    "original_filename": task_info["original_filename"],
                    "error_message": error_message if task_info["status"] == "failed" else None,
                    "chunk_id": chunk_id,
                    "created_at": task_info["created_at"],
                    "updated_at": task_info["updated_at"]
                }
            }
        else:
            logger.warning(f"[MCP] 查询任务状态失败: 任务不存在 (ID: {task_id})")
            return {
                "success": False,
                "message": f"任务不存在 (ID: {task_id})",
                "data": None
            }

    except Exception as e:
        logger.error(f"[MCP] 查询任务状态异常: {str(e)}", exc_info=True)
        return {
            "success": False,
            "message": f"查询任务状态失败: {str(e)}",
            "data": None
        }
