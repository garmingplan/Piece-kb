"""
API 路由定义

提供以下接口:
- POST /api/upload - 上传文件
- GET /api/tasks/{task_id} - 查询任务状态
- GET /api/files - 文件列表
- GET /api/files/{file_id}/chunks - 获取文件的切片列表
- DELETE /api/files/{file_id} - 删除文件
"""

from typing import Optional, List
from fastapi import APIRouter, UploadFile, File, HTTPException

from indexing.services import file_service, task_service
from app.utils import MAX_FILE_SIZE
from app.api.models import (
    UploadResponse,
    TaskResponse,
    FileResponse,
    ChunkResponse,
    DeleteResponse,
)

router = APIRouter(prefix="/api")


# ========== 路由 ==========

@router.post("/upload", response_model=UploadResponse)
async def upload_file(file: UploadFile = File(...)):
    """
    上传文件

    - 检查文件大小（限制 50MB）
    - 检查文件是否已存在（哈希去重）
    - 保存文件到 data/files/
    - 插入 files 表记录
    - 创建异步处理任务
    - 返回 task_id
    """
    # 验证文件类型
    filename_lower = file.filename.lower()
    if not (filename_lower.endswith(".md") or filename_lower.endswith(".pdf")):
        raise HTTPException(status_code=400, detail="仅支持 Markdown (.md) 和 PDF (.pdf) 文件")

    # 读取文件内容
    content = await file.read()

    # 检查文件大小
    if len(content) > MAX_FILE_SIZE:
        size_mb = len(content) / (1024 * 1024)
        raise HTTPException(
            status_code=413,
            detail=f"文件过大（{size_mb:.1f}MB），最大支持 50MB"
        )

    # 检查文件是否已存在
    file_hash = file_service.calculate_file_hash(content)
    existing_id = file_service.check_file_hash_exists(file_hash)
    if existing_id:
        raise HTTPException(status_code=409, detail="文件已存在，无需重复上传")

    # 保存物理文件（原始文件 + 工作文件）
    save_result = await file_service.save_file(file.filename, content)

    # 插入 files 表记录
    file_id = file_service.insert_file_record(
        file_hash=save_result["file_hash"],
        filename=save_result["filename"],
        file_path=save_result["file_path"],
        file_size=save_result["file_size"],
        original_file_type=save_result["original_file_type"],
        original_file_path=save_result["original_file_path"],
        status="pending"
    )

    # 创建任务并关联 file_id
    task_id = task_service.create_task(save_result["filename"])
    task_service.update_task_status(task_id, "pending", file_id=file_id)

    return UploadResponse(
        task_id=task_id,
        filename=save_result["filename"],
        message="文件上传成功，正在后台处理"
    )


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: int):
    """查询任务状态"""
    task = task_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    return TaskResponse(**task)


@router.get("/files", response_model=List[FileResponse])
async def get_files(status: Optional[str] = None):
    """
    获取文件列表

    Query 参数:
    - status: 可选，按状态筛选 ('pending', 'indexed', 'error')
    """
    if status and status not in ("pending", "indexed", "error"):
        raise HTTPException(status_code=400, detail="无效的状态值")

    files = file_service.get_files_list(status)
    return [FileResponse(**f) for f in files]


@router.get("/files/{file_id}/chunks", response_model=List[ChunkResponse])
async def get_file_chunks(file_id: int):
    """
    获取文件的切片列表

    Args:
        file_id: 文件 ID
    """
    chunks = file_service.get_chunks_by_file_id(file_id)
    if chunks is None:
        raise HTTPException(status_code=404, detail="文件不存在")

    return [ChunkResponse(**c) for c in chunks]


@router.delete("/files/{file_id}", response_model=DeleteResponse)
async def delete_file(file_id: int):
    """
    删除文件

    - 删除数据库记录（files + chunks，级联删除）
    - 删除物理文件
    """
    success = file_service.delete_file(file_id)

    if not success:
        raise HTTPException(status_code=404, detail="文件不存在")

    return DeleteResponse(success=True, message="文件删除成功")


def register_routes(app):
    """
    注册路由到 FastAPI/NiceGUI 应用

    Args:
        app: FastAPI 或 NiceGUI 应用实例
    """
    app.include_router(router)
