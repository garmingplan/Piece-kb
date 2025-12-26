"""
任务服务模块

职责:
- 任务 CRUD 操作
- 任务状态管理
- 任务队列查询
"""

from datetime import datetime
from typing import Optional, List, Dict, Any

from ..database import get_connection


def create_task(original_filename: str) -> int:
    """
    创建新任务

    Args:
        original_filename: 原始文件名

    Returns:
        新创建的 task_id
    """
    conn = get_connection()
    try:
        now = datetime.now().isoformat()
        cursor = conn.execute(
            """
            INSERT INTO tasks (original_filename, status, progress, created_at, updated_at)
            VALUES (?, 'pending', 0, ?, ?)
            """,
            (original_filename, now, now),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_task(task_id: int) -> Optional[Dict[str, Any]]:
    """根据 ID 获取任务信息"""
    conn = get_connection()
    try:
        result = conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        return dict(result) if result else None
    finally:
        conn.close()


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
    conn = get_connection()
    try:
        now = datetime.now().isoformat()

        # 构建动态 SQL
        updates = ["status = ?", "updated_at = ?"]
        params = [status, now]

        if progress is not None:
            updates.append("progress = ?")
            params.append(progress)

        if error_message is not None:
            updates.append("error_message = ?")
            params.append(error_message)

        if file_id is not None:
            updates.append("file_id = ?")
            params.append(file_id)

        params.append(task_id)

        sql = f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?"
        conn.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def update_task_progress(task_id: int, progress: int) -> None:
    """更新任务进度"""
    update_task_status(task_id, "processing", progress=progress)


def get_pending_tasks() -> List[Dict[str, Any]]:
    """获取所有待处理的任务"""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE status = 'pending' ORDER BY created_at ASC"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_active_tasks() -> List[Dict[str, Any]]:
    """
    获取所有活跃的任务（pending 或 processing）

    用于页面加载时恢复任务监控

    Returns:
        活跃任务列表
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT * FROM tasks
            WHERE status IN ('pending', 'processing')
            ORDER BY created_at ASC
            """
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


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
    conn = get_connection()
    try:
        if status:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def delete_task(task_id: int) -> bool:
    """删除任务记录"""
    conn = get_connection()
    try:
        cursor = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()
