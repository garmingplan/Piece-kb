"""
Task Repository

职责:
- 任务数据访问层
- 封装 tasks 表的数据库操作
"""

from typing import Optional, List, Dict, Any
from datetime import datetime

from .base_repository import BaseRepository
from ..database import get_db_cursor


class TaskRepository(BaseRepository):
    """
    Task Repository

    管理 tasks 表的数据访问
    """

    @property
    def table_name(self) -> str:
        return "tasks"

    @property
    def allowed_fields(self) -> List[str]:
        """返回 tasks 表的所有合法字段名"""
        return [
            "id", "file_id", "original_filename", "status",
            "progress", "error_message", "created_at", "updated_at"
        ]

    def _row_to_dict(self, row) -> Dict[str, Any]:
        """将数据库行转换为字典"""
        return {
            "id": row["id"],
            "file_id": row["file_id"],
            "original_filename": row["original_filename"],
            "status": row["status"],
            "progress": row["progress"],
            "error_message": row["error_message"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    # ========== 任务特定操作 ==========

    def create(self, original_filename: str) -> int:
        """
        创建新任务

        Args:
            original_filename: 原始文件名

        Returns:
            新创建的 task_id
        """
        with get_db_cursor() as cursor:
            now = datetime.now().isoformat()
            cursor.execute(
                """
                INSERT INTO tasks (original_filename, status, progress, created_at, updated_at)
                VALUES (?, 'pending', 0, ?, ?)
                """,
                (original_filename, now, now),
            )
            return cursor.lastrowid

    def find_pending(self) -> List[Dict[str, Any]]:
        """
        获取所有待处理的任务

        Returns:
            待处理任务列表（按创建时间升序）
        """
        with get_db_cursor() as cursor:
            cursor.execute("SELECT * FROM tasks WHERE status = 'pending' ORDER BY created_at ASC")
            return [self._row_to_dict(row) for row in cursor.fetchall()]

    def find_active(self) -> List[Dict[str, Any]]:
        """
        获取所有活跃的任务（pending 或 processing）

        Returns:
            活跃任务列表
        """
        with get_db_cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM tasks
                WHERE status IN ('pending', 'processing')
                ORDER BY created_at ASC
                """
            )
            return [self._row_to_dict(row) for row in cursor.fetchall()]

    def find_by_status(self, status: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        根据状态查询任务列表

        Args:
            status: 任务状态
            limit: 返回数量限制

        Returns:
            任务列表（按创建时间降序）
        """
        with get_db_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM tasks WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status, limit)
            )
            return [self._row_to_dict(row) for row in cursor.fetchall()]

    def find_recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        获取最近的任务列表

        Args:
            limit: 返回数量限制

        Returns:
            任务列表（按创建时间降序）
        """
        with get_db_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?",
                (limit,)
            )
            return [self._row_to_dict(row) for row in cursor.fetchall()]

    def update_status(
        self,
        task_id: int,
        status: str,
        progress: Optional[int] = None,
        error_message: Optional[str] = None,
        file_id: Optional[int] = None
    ) -> bool:
        """
        更新任务状态

        Args:
            task_id: 任务 ID
            status: 新状态
            progress: 进度百分比（可选）
            error_message: 错误信息（可选）
            file_id: 关联的文件 ID（可选）

        Returns:
            是否更新成功
        """
        with get_db_cursor() as cursor:
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
            cursor.execute(sql, params)

            return cursor.rowcount > 0

    def update_progress(self, task_id: int, progress: int) -> bool:
        """
        更新任务进度

        Args:
            task_id: 任务 ID
            progress: 进度百分比（0-100）

        Returns:
            是否更新成功
        """
        return self.update_status(task_id, "processing", progress=progress)
