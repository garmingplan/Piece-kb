"""
Chunk API 路由定义

提供以下接口:
- PUT /api/chunks/{chunk_id} - 修改切片
- DELETE /api/chunks/{chunk_id} - 删除切片
- POST /api/files/{file_id}/chunks - 新增切片
"""

from fastapi import APIRouter, HTTPException

from indexing.services import chunk_service
from app.api.models import (
    ChunkUpdateRequest,
    ChunkCreateRequest,
    ChunkDetailResponse,
    ChunkDeleteResponse,
    ChunkUpdateResponse,
    ChunkCreateResponse,
)

router = APIRouter(prefix="/api")


# ========== 路由 ==========


@router.delete("/chunks/{chunk_id}", response_model=ChunkDeleteResponse)
async def delete_chunk(chunk_id: int):
    """
    删除单个切片

    - 删除 chunks 记录（FTS5 自动同步）
    - 删除 vec_chunks 记录
    - 如果文件无剩余切片，更新状态为 'empty'
    """
    result = chunk_service.delete_chunk(chunk_id)

    if not result["success"]:
        raise HTTPException(status_code=404, detail=result.get("error", "删除失败"))

    return ChunkDeleteResponse(
        success=True,
        message="切片删除成功",
        file_id=result["file_id"],
        file_status=result["file_status"]
    )


@router.put("/chunks/{chunk_id}", response_model=ChunkUpdateResponse)
async def update_chunk(chunk_id: int, request: ChunkUpdateRequest):
    """
    修改切片

    - 修改 doc_title: 同步操作，立即返回
    - 修改 chunk_text: 异步操作，返回 task_id（需重新生成 embedding）
    - 同时修改两者: 先同步更新 doc_title，再异步处理 chunk_text
    """
    if request.doc_title is None and request.chunk_text is None:
        raise HTTPException(status_code=400, detail="请提供要修改的字段")

    # 检查 chunk 是否存在
    chunk = chunk_service.get_chunk_by_id(chunk_id)
    if not chunk:
        raise HTTPException(status_code=404, detail="切片不存在")

    task_id = None
    updated_chunk = chunk

    # 1. 同步更新 doc_title
    if request.doc_title is not None:
        updated_chunk = chunk_service.update_chunk_title(chunk_id, request.doc_title)
        if not updated_chunk:
            raise HTTPException(status_code=500, detail="更新标题失败")

    # 2. 异步更新 chunk_text
    if request.chunk_text is not None:
        task_id = chunk_service.create_chunk_update_task(chunk_id, request.chunk_text)
        message = "标题已更新，内容更新任务已创建" if request.doc_title else "内容更新任务已创建"
    else:
        message = "标题更新成功"

    return ChunkUpdateResponse(
        success=True,
        message=message,
        chunk=ChunkDetailResponse(**updated_chunk) if updated_chunk else None,
        task_id=task_id
    )


@router.post("/files/{file_id}/chunks", response_model=ChunkCreateResponse)
async def create_chunk(file_id: int, request: ChunkCreateRequest):
    """
    新增切片

    - 异步操作，返回 task_id（需生成 embedding）
    - 如果文件状态为 'empty'，完成后更新为 'indexed'
    """
    try:
        task_id = chunk_service.create_chunk_add_task(
            file_id=file_id,
            doc_title=request.doc_title,
            chunk_text=request.chunk_text
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return ChunkCreateResponse(
        success=True,
        message="新增切片任务已创建",
        task_id=task_id
    )


def register_chunk_routes(app):
    """注册 Chunk 路由到应用"""
    app.include_router(router)
