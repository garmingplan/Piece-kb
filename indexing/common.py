"""
公共工具模块

职责:
- 数据库装饰器（减少重复代码）
- 进度追踪器（统一进度回调管理）
- 通用工具函数
"""

import functools
from typing import Callable, Optional, Any, TypeVar
from .database import get_db_cursor


# ========== 数据库装饰器 ==========

T = TypeVar('T')


def with_db_cursor(func: Callable[..., T]) -> Callable[..., T]:
    """
    数据库游标装饰器，自动处理游标创建和事务管理

    装饰的函数第一个参数必须是 cursor

    用法:
        @with_db_cursor
        def get_file_by_id(cursor, file_id: int):
            cursor.execute("SELECT * FROM files WHERE id = ?", (file_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with get_db_cursor() as cursor:
            # 将 cursor 作为第一个参数传递
            return func(cursor, *args, **kwargs)
    return wrapper


def with_db_cursor_retrieval(func: Callable[..., T]) -> Callable[..., T]:
    """
    检索数据库游标装饰器（用于 retrieval 模块）

    装饰的函数第一个参数必须是 cursor

    用法:
        @with_db_cursor_retrieval
        def search_chunks(cursor, query: str):
            cursor.execute("SELECT * FROM chunks_fts WHERE ...")
            return cursor.fetchall()
    """
    from retrieval.db import get_db_cursor as get_retrieval_cursor

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with get_retrieval_cursor() as cursor:
            return func(cursor, *args, **kwargs)
    return wrapper


# ========== 进度追踪器 ==========

class ProgressTracker:
    """
    进度追踪器，统一管理进度回调

    用法:
        tracker = ProgressTracker(start=0, end=100, total=100, callback=progress_callback)

        for i in range(100):
            # ... 处理任务 ...
            tracker.update(i + 1)  # 自动计算并回调进度
    """

    def __init__(
        self,
        start: int,
        end: int,
        total: int,
        callback: Optional[Callable[[int], None]] = None
    ):
        """
        初始化进度追踪器

        Args:
            start: 起始进度值（例如 0）
            end: 结束进度值（例如 100）
            total: 任务总数
            callback: 进度回调函数（接收 int 参数）
        """
        self.start = start
        self.end = end
        self.total = total
        self.callback = callback
        self._last_reported = -1  # 避免重复报告相同进度

    def update(self, current: int) -> None:
        """
        更新进度

        Args:
            current: 当前完成数量
        """
        if not self.callback:
            return

        # 计算当前进度百分比
        if self.total == 0:
            progress = self.end
        else:
            progress = self.start + int((self.end - self.start) * current / self.total)

        # 避免进度倒退和重复报告
        if progress > self._last_reported:
            self.callback(progress)
            self._last_reported = progress

    def finish(self) -> None:
        """标记任务完成，强制报告结束进度"""
        if self.callback and self._last_reported < self.end:
            self.callback(self.end)
            self._last_reported = self.end


# ========== 分段进度追踪器 ==========

class SegmentedProgressTracker:
    """
    分段进度追踪器，用于多阶段任务

    用法:
        tracker = SegmentedProgressTracker(total=100, callback=progress_callback)

        # 阶段1：文件转换（0-30%）
        with tracker.segment(0, 30, total_pages=100) as seg:
            for i in range(100):
                # ... 转换页面 ...
                seg.update(i + 1)

        # 阶段2：文件分块（30-50%）
        with tracker.segment(30, 50, total_chunks=50) as seg:
            for i in range(50):
                # ... 分块 ...
                seg.update(i + 1)

        # 阶段3：向量生成（50-100%）
        with tracker.segment(50, 100, total_batches=10) as seg:
            for i in range(10):
                # ... 生成向量 ...
                seg.update(i + 1)
    """

    def __init__(self, total: int = 100, callback: Optional[Callable[[int], None]] = None):
        """
        初始化分段进度追踪器

        Args:
            total: 总进度值（通常为 100）
            callback: 进度回调函数
        """
        self.total = total
        self.callback = callback

    def segment(self, start: int, end: int, total: int) -> ProgressTracker:
        """
        创建一个进度段

        Args:
            start: 该段起始进度（0-100）
            end: 该段结束进度（0-100）
            total: 该段任务总数

        Returns:
            ProgressTracker 实例
        """
        return ProgressTracker(start, end, total, self.callback)


# ========== 数据库批量操作工具 ==========

class BatchInserter:
    """
    批量插入工具，减少数据库提交次数

    用法:
        with BatchInserter(batch_size=50) as inserter:
            for chunk in chunks:
                inserter.add(
                    "INSERT INTO chunks (file_id, doc_title, chunk_text) VALUES (?, ?, ?)",
                    (file_id, doc_title, chunk_text)
                )
        # 自动提交剩余的数据
    """

    def __init__(self, batch_size: int = 50):
        """
        初始化批量插入器

        Args:
            batch_size: 批量大小（每批提交的记录数）
        """
        self.batch_size = batch_size
        self.buffer = []
        self.cursor = None

    def __enter__(self):
        """进入上下文管理器"""
        from .database import get_db_cursor
        self._cursor_context = get_db_cursor()
        self.cursor = self._cursor_context.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文管理器，提交剩余数据"""
        if self.buffer and not exc_type:
            self._flush()
        return self._cursor_context.__exit__(exc_type, exc_val, exc_tb)

    def add(self, sql: str, params: tuple) -> None:
        """
        添加一条待插入记录

        Args:
            sql: SQL 语句
            params: 参数元组
        """
        self.buffer.append((sql, params))

        # 达到批量大小，执行提交
        if len(self.buffer) >= self.batch_size:
            self._flush()

    def _flush(self) -> None:
        """执行批量提交"""
        if not self.buffer or not self.cursor:
            return

        for sql, params in self.buffer:
            self.cursor.execute(sql, params)

        self.buffer.clear()
