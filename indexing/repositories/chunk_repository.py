"""
Chunk Repository

职责:
- 切片数据访问层
- 封装 chunks 表的数据库操作
- 管理 vec_chunks 向量索引
"""

from typing import Optional, List, Dict, Any
from datetime import datetime

from .base_repository import BaseRepository
from ..database import get_db_cursor


class ChunkRepository(BaseRepository):
    """
    Chunk Repository

    管理 chunks 表和 vec_chunks 表的数据访问
    """

    @property
    def table_name(self) -> str:
        return "chunks"

    @property
    def allowed_fields(self) -> List[str]:
        """返回 chunks 表的所有合法字段名"""
        return ["id", "file_id", "doc_title", "chunk_text", "embedding"]

    def _row_to_dict(self, row) -> Dict[str, Any]:
        """将数据库行转换为字典（不包含 embedding 二进制数据）"""
        return {
            "id": row["id"],
            "file_id": row["file_id"],
            "doc_title": row["doc_title"],
            "chunk_text": row["chunk_text"],
        }

    # ========== 切片特定操作 ==========

    def find_by_file_id(self, file_id: int) -> List[Dict[str, Any]]:
        """
        根据文件 ID 获取所有切片

        Args:
            file_id: 文件 ID

        Returns:
            切片列表
        """
        with get_db_cursor() as cursor:
            cursor.execute(
                "SELECT id, file_id, doc_title, chunk_text FROM chunks WHERE file_id = ? ORDER BY id",
                (file_id,)
            )
            return [self._row_to_dict(row) for row in cursor.fetchall()]

    def count_by_file_id(self, file_id: int) -> int:
        """
        统计文件的切片数量

        Args:
            file_id: 文件 ID

        Returns:
            切片数量
        """
        with get_db_cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) as count FROM chunks WHERE file_id = ?",
                (file_id,)
            )
            result = cursor.fetchone()
            return result["count"]

    def find_by_file_id_paginated(
        self,
        file_id: int,
        page: int = 1,
        page_size: int = 50
    ) -> List[Dict[str, Any]]:
        """
        分页查询文件的切片

        Args:
            file_id: 文件 ID
            page: 页码（从1开始）
            page_size: 每页数量

        Returns:
            切片列表
        """
        offset = (page - 1) * page_size

        with get_db_cursor() as cursor:
            cursor.execute(
                """
                SELECT id, file_id, doc_title, chunk_text
                FROM chunks
                WHERE file_id = ?
                ORDER BY id
                LIMIT ? OFFSET ?
                """,
                (file_id, page_size, offset)
            )
            return [self._row_to_dict(row) for row in cursor.fetchall()]

    def insert(
        self,
        file_id: int,
        doc_title: str,
        chunk_text: str,
        embedding: bytes
    ) -> int:
        """
        插入切片记录

        Args:
            file_id: 文件 ID
            doc_title: 文档标题
            chunk_text: 切片文本
            embedding: 向量数据（二进制）

        Returns:
            新插入的 chunk_id
        """
        with get_db_cursor() as cursor:
            # 插入 chunks 表（FTS5 触发器自动同步）
            cursor.execute(
                """
                INSERT INTO chunks (file_id, doc_title, chunk_text, embedding)
                VALUES (?, ?, ?, ?)
                """,
                (file_id, doc_title, chunk_text, embedding)
            )
            chunk_id = cursor.lastrowid

            # 插入 vec_chunks 表
            cursor.execute(
                "INSERT INTO vec_chunks (chunk_id, embedding) VALUES (?, ?)",
                (chunk_id, embedding)
            )

            return chunk_id

    def update_title(self, chunk_id: int, doc_title: str) -> bool:
        """
        更新切片标题

        Args:
            chunk_id: 切片 ID
            doc_title: 新标题

        Returns:
            是否更新成功
        """
        with get_db_cursor() as cursor:
            cursor.execute(
                "UPDATE chunks SET doc_title = ? WHERE id = ?",
                (doc_title, chunk_id)
            )
            return cursor.rowcount > 0

    def update_content(self, chunk_id: int, chunk_text: str, embedding: bytes) -> bool:
        """
        更新切片内容和向量

        Args:
            chunk_id: 切片 ID
            chunk_text: 新文本
            embedding: 新向量数据

        Returns:
            是否更新成功
        """
        with get_db_cursor() as cursor:
            # 更新 chunks 表（FTS5 触发器自动同步）
            cursor.execute(
                "UPDATE chunks SET chunk_text = ?, embedding = ? WHERE id = ?",
                (chunk_text, embedding, chunk_id)
            )

            # 更新 vec_chunks 表
            cursor.execute(
                "UPDATE vec_chunks SET embedding = ? WHERE chunk_id = ?",
                (embedding, chunk_id)
            )

            return cursor.rowcount > 0

    def delete_with_vectors(self, chunk_id: int) -> bool:
        """
        删除切片及其向量索引

        Args:
            chunk_id: 切片 ID

        Returns:
            是否删除成功
        """
        with get_db_cursor() as cursor:
            # 删除 vec_chunks
            cursor.execute("DELETE FROM vec_chunks WHERE chunk_id = ?", (chunk_id,))

            # 删除 chunks（FTS5 触发器自动同步）
            cursor.execute("DELETE FROM chunks WHERE id = ?", (chunk_id,))

            return cursor.rowcount > 0

    def delete_by_file_id(self, file_id: int) -> int:
        """
        删除文件的所有切片

        Args:
            file_id: 文件 ID

        Returns:
            删除的切片数量
        """
        with get_db_cursor() as cursor:
            # 先删除 vec_chunks
            cursor.execute(
                """
                DELETE FROM vec_chunks WHERE chunk_id IN (
                    SELECT id FROM chunks WHERE file_id = ?
                )
                """,
                (file_id,)
            )

            # 再删除 chunks
            cursor.execute("DELETE FROM chunks WHERE file_id = ?", (file_id,))

            return cursor.rowcount

    def get_total_count(self) -> int:
        """
        获取切片总数

        Returns:
            切片总数
        """
        with get_db_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) as count FROM chunks")
            result = cursor.fetchone()
            return result["count"]

    def batch_insert(self, chunks_data: List[Dict[str, Any]]) -> List[int]:
        """
        批量插入切片

        Args:
            chunks_data: 切片数据列表，每项包含:
                - file_id: 文件 ID
                - doc_title: 文档标题
                - chunk_text: 切片文本
                - embedding: 向量数据

        Returns:
            插入的 chunk_id 列表
        """
        chunk_ids = []

        with get_db_cursor() as cursor:
            for chunk in chunks_data:
                cursor.execute(
                    """
                    INSERT INTO chunks (file_id, doc_title, chunk_text, embedding)
                    VALUES (?, ?, ?, ?)
                    """,
                    (chunk["file_id"], chunk["doc_title"], chunk["chunk_text"], chunk["embedding"])
                )
                chunk_id = cursor.lastrowid
                chunk_ids.append(chunk_id)

                # 插入 vec_chunks
                cursor.execute(
                    "INSERT INTO vec_chunks (chunk_id, embedding) VALUES (?, ?)",
                    (chunk_id, chunk["embedding"])
                )

        return chunk_ids
