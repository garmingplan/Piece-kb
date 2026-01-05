"""
Repository 基类

职责:
- 定义通用的数据访问接口
- 提供基础的 CRUD 操作模板
- 封装数据库连接细节
"""

from typing import Optional, List, Dict, Any, Generic, TypeVar
from abc import ABC, abstractmethod
from ..database import get_db_cursor


T = TypeVar('T')


class BaseRepository(ABC, Generic[T]):
    """
    Repository 基类，提供通用的数据访问接口

    子类需要实现:
    - table_name: 表名
    - _row_to_dict: 将数据库行转换为字典
    - allowed_fields: 允许的字段名白名单（可选，用于 SQL 注入防护）
    """

    @property
    @abstractmethod
    def table_name(self) -> str:
        """返回表名"""
        pass

    @property
    def allowed_fields(self) -> List[str]:
        """
        返回允许的字段名白名单（用于动态 SQL 验证）

        子类应该重写此方法返回表的所有合法字段名
        默认返回空列表表示不进行字段名验证

        Returns:
            允许的字段名列表
        """
        return []

    def _validate_field_name(self, field_name: str) -> None:
        """
        验证字段名是否在白名单中

        Args:
            field_name: 要验证的字段名

        Raises:
            ValueError: 字段名不在白名单中
        """
        allowed = self.allowed_fields
        if allowed and field_name not in allowed:
            raise ValueError(f"Invalid field name: {field_name}. Allowed fields: {allowed}")

    @abstractmethod
    def _row_to_dict(self, row) -> Dict[str, Any]:
        """
        将数据库行转换为字典

        Args:
            row: sqlite3.Row 对象

        Returns:
            字典格式的数据
        """
        pass

    # ========== 基础 CRUD 操作 ==========

    def find_by_id(self, id: int) -> Optional[Dict[str, Any]]:
        """
        根据 ID 查询单条记录

        Args:
            id: 记录 ID

        Returns:
            字典格式的记录，不存在则返回 None
        """
        with get_db_cursor() as cursor:
            cursor.execute(f"SELECT * FROM {self.table_name} WHERE id = ?", (id,))
            row = cursor.fetchone()
            return self._row_to_dict(row) if row else None

    def find_all(self, limit: Optional[int] = None, offset: int = 0) -> List[Dict[str, Any]]:
        """
        查询所有记录

        Args:
            limit: 限制返回数量
            offset: 偏移量

        Returns:
            字典列表
        """
        with get_db_cursor() as cursor:
            sql = f"SELECT * FROM {self.table_name}"

            if limit is not None:
                sql += f" LIMIT {limit} OFFSET {offset}"

            cursor.execute(sql)
            return [self._row_to_dict(row) for row in cursor.fetchall()]

    def count(self) -> int:
        """
        统计记录总数

        Returns:
            记录数量
        """
        with get_db_cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) as count FROM {self.table_name}")
            result = cursor.fetchone()
            return result["count"]

    def delete_by_id(self, id: int) -> bool:
        """
        根据 ID 删除记录

        Args:
            id: 记录 ID

        Returns:
            是否删除成功
        """
        with get_db_cursor() as cursor:
            cursor.execute(f"DELETE FROM {self.table_name} WHERE id = ?", (id,))
            return cursor.rowcount > 0

    def exists(self, id: int) -> bool:
        """
        检查记录是否存在

        Args:
            id: 记录 ID

        Returns:
            是否存在
        """
        with get_db_cursor() as cursor:
            cursor.execute(f"SELECT 1 FROM {self.table_name} WHERE id = ? LIMIT 1", (id,))
            return cursor.fetchone() is not None

    # ========== 高级查询 ==========

    def find_by(self, **conditions) -> List[Dict[str, Any]]:
        """
        根据条件查询记录（AND 连接）

        Args:
            **conditions: 查询条件（字段名=值）

        Returns:
            字典列表

        Example:
            repo.find_by(status='indexed', file_size__gt=1000)
        """
        if not conditions:
            return self.find_all()

        where_clauses = []
        params = []

        for key, value in conditions.items():
            # 支持简单的操作符（__gt, __lt, __gte, __lte, __ne）
            if "__gt" in key:
                field = key.replace("__gt", "")
                self._validate_field_name(field)
                where_clauses.append(f"{field} > ?")
            elif "__lt" in key:
                field = key.replace("__lt", "")
                self._validate_field_name(field)
                where_clauses.append(f"{field} < ?")
            elif "__gte" in key:
                field = key.replace("__gte", "")
                self._validate_field_name(field)
                where_clauses.append(f"{field} >= ?")
            elif "__lte" in key:
                field = key.replace("__lte", "")
                self._validate_field_name(field)
                where_clauses.append(f"{field} <= ?")
            elif "__ne" in key:
                field = key.replace("__ne", "")
                self._validate_field_name(field)
                where_clauses.append(f"{field} != ?")
            else:
                self._validate_field_name(key)
                where_clauses.append(f"{key} = ?")

            params.append(value)

        where_sql = " AND ".join(where_clauses)
        sql = f"SELECT * FROM {self.table_name} WHERE {where_sql}"

        with get_db_cursor() as cursor:
            cursor.execute(sql, tuple(params))
            return [self._row_to_dict(row) for row in cursor.fetchall()]

    def find_one_by(self, **conditions) -> Optional[Dict[str, Any]]:
        """
        根据条件查询单条记录

        Args:
            **conditions: 查询条件

        Returns:
            字典格式的记录，不存在则返回 None
        """
        results = self.find_by(**conditions)
        return results[0] if results else None

    # ========== 批量操作 ==========

    def delete_by(self, **conditions) -> int:
        """
        根据条件批量删除记录

        Args:
            **conditions: 删除条件

        Returns:
            删除的记录数
        """
        if not conditions:
            raise ValueError("批量删除必须指定条件，避免误删全表")

        where_clauses = []
        params = []

        for key, value in conditions.items():
            self._validate_field_name(key)
            where_clauses.append(f"{key} = ?")
            params.append(value)

        where_sql = " AND ".join(where_clauses)
        sql = f"DELETE FROM {self.table_name} WHERE {where_sql}"

        with get_db_cursor() as cursor:
            cursor.execute(sql, tuple(params))
            return cursor.rowcount

    def update_by_id(self, id: int, **updates) -> bool:
        """
        根据 ID 更新记录

        Args:
            id: 记录 ID
            **updates: 更新字段（字段名=新值）

        Returns:
            是否更新成功
        """
        if not updates:
            return False

        set_clauses = []
        params = []

        for key, value in updates.items():
            self._validate_field_name(key)
            set_clauses.append(f"{key} = ?")
            params.append(value)

        params.append(id)

        set_sql = ", ".join(set_clauses)
        sql = f"UPDATE {self.table_name} SET {set_sql} WHERE id = ?"

        with get_db_cursor() as cursor:
            cursor.execute(sql, tuple(params))
            return cursor.rowcount > 0
