"""
导出 API 路由定义

提供以下接口:
- GET /api/files/{file_id}/export - 导出合并文档
- GET /api/exports - 获取导出文件列表
- DELETE /api/exports/{filename} - 删除导出文件
"""

from typing import List
from fastapi import APIRouter, HTTPException

from indexing.services import export_service
from app.api.models import (
    ExportResponse,
    ExportFileInfo,
    DeleteResponse,
)

router = APIRouter(prefix="/api")


# ========== 路由 ==========


@router.get("/files/{file_id}/export", response_model=ExportResponse)
async def export_file(file_id: int):
    """
    导出文件的所有切片为 Markdown 文档

    - 合并所有 chunks
    - 重建标题层级结构
    - 保存到 exports 文件夹
    """
    result = export_service.export_file_chunks(file_id)

    if not result["success"]:
        raise HTTPException(status_code=404, detail=result.get("error", "导出失败"))

    return ExportResponse(
        success=True,
        message="导出成功",
        export_path=result["export_path"],
        filename=result["filename"],
        chunk_count=result["chunk_count"]
    )


@router.get("/exports", response_model=List[ExportFileInfo])
async def list_exports():
    """获取所有导出文件列表"""
    files = export_service.get_export_files_list()
    return [ExportFileInfo(**f) for f in files]


@router.delete("/exports/{filename}", response_model=DeleteResponse)
async def delete_export(filename: str):
    """删除导出文件"""
    # 安全检查：防止路径遍历攻击
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="无效的文件名")

    success = export_service.delete_export_file(filename)

    if not success:
        raise HTTPException(status_code=404, detail="文件不存在")

    return DeleteResponse(success=True, message="删除成功")


def register_export_routes(app):
    """注册导出路由到应用"""
    app.include_router(router)
