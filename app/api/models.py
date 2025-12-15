"""
API 响应模型定义

职责:
- 定义统一的 Pydantic 响应模型
- 避免各路由文件中重复定义
"""

from typing import Optional, List, Any
from pydantic import BaseModel


# ========== 通用响应 ==========

class ApiResponse(BaseModel):
    """通用 API 响应（支持任意数据类型）"""
    success: bool
    message: str
    data: Optional[Any] = None


class SuccessResponse(BaseModel):
    """通用成功响应"""
    success: bool
    message: str


class DeleteResponse(BaseModel):
    """删除操作响应"""
    success: bool
    message: str


# ========== 文件相关 ==========

class UploadResponse(BaseModel):
    """文件上传响应"""
    task_id: int
    filename: str
    message: str


class FileResponse(BaseModel):
    """文件信息响应"""
    id: int
    filename: str
    file_path: str
    file_size: int
    status: str
    created_at: str
    updated_at: str


# ========== 任务相关 ==========

class TaskResponse(BaseModel):
    """任务状态响应"""
    id: int
    original_filename: str
    status: str
    progress: int
    error_message: Optional[str] = None
    file_id: Optional[int] = None
    created_at: str
    updated_at: str


# ========== 切片相关 ==========

class ChunkResponse(BaseModel):
    """切片信息响应（基础版，不含 file_id）"""
    id: int
    doc_title: str
    chunk_text: str


class ChunkDetailResponse(BaseModel):
    """切片详细信息响应（含 file_id）"""
    id: int
    file_id: int
    doc_title: str
    chunk_text: str


class ChunkDeleteResponse(BaseModel):
    """切片删除响应"""
    success: bool
    message: str
    file_id: int
    file_status: str


class ChunkUpdateRequest(BaseModel):
    """切片更新请求"""
    doc_title: Optional[str] = None
    chunk_text: Optional[str] = None


class ChunkCreateRequest(BaseModel):
    """切片创建请求"""
    doc_title: str
    chunk_text: str


class ChunkUpdateResponse(BaseModel):
    """切片更新响应"""
    success: bool
    message: str
    chunk: Optional[ChunkDetailResponse] = None
    task_id: Optional[int] = None


class ChunkCreateResponse(BaseModel):
    """切片创建响应"""
    success: bool
    message: str
    task_id: int
