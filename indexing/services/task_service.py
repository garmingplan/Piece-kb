"""
任务服务模块

职责:
- 任务 CRUD 操作
- 任务状态管理
- 任务队列查询
"""

from datetime import datetime
from typing import Optional, List, Dict, Any

from ..database import get_db_cursor
from ..repositories import TaskRepository

# 初始化 Repository
_task_repo = TaskRepository()


def create_task(original_filename: str) -> int:
    """
    创建新任务

    Args:
        original_filename: 原始文件名

    Returns:
        新创建的 task_id
    """
    return _task_repo.create(original_filename)


def get_task(task_id: int) -> Optional[Dict[str, Any]]:
    """根据 ID 获取任务信息"""
    return _task_repo.find_by_id(task_id)


def update_task_status(
    task_id: int,
    status: str,
    progress: Optional[int] = None,
    error_message: Optional[str] = None,
    file_id: Optional[int] = None
) -> None:
    """
    更新任务状态

    Args:
        task_id: 任务 ID
        status: 新状态 ('pending', 'processing', 'completed', 'failed')
        progress: 进度百分比 (0-100)
        error_message: 错误信息（仅 failed 状态）
        file_id: 关联的文件 ID
    """
    _task_repo.update_status(task_id, status, progress, error_message, file_id)


def update_task_progress(task_id: int, progress: int) -> None:
    """更新任务进度"""
    _task_repo.update_progress(task_id, progress)


def get_pending_tasks() -> List[Dict[str, Any]]:
    """获取所有待处理的任务"""
    return _task_repo.find_pending()


def get_active_tasks() -> List[Dict[str, Any]]:
    """
    获取所有活跃的任务（pending 或 processing）

    用于页面加载时恢复任务监控

    Returns:
        活跃任务列表
    """
    return _task_repo.find_active()


def get_tasks_list(
    status: Optional[str] = None,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """
    获取任务列表

    Args:
        status: 可选，按状态筛选
        limit: 返回数量限制

    Returns:
        任务列表
    """
    if status:
        return _task_repo.find_by_status(status, limit)
    else:
        return _task_repo.find_recent(limit)


def delete_task(task_id: int) -> bool:
    """删除任务记录"""
    return _task_repo.delete_by_id(task_id)
