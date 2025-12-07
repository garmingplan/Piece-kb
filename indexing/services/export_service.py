"""
文档导出服务模块

职责:
- 合并 chunks 生成 Markdown 文档
- 重建标题层级结构
- 导出到 exports 文件夹
"""

import re
from pathlib import Path
from typing import Optional, Dict, Any, List

from ..database import get_connection
from ..settings import get_settings


def get_exports_dir() -> Path:
    """获取导出文件存储目录"""
    settings = get_settings()
    exports_dir = settings.get_data_path() / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    return exports_dir


def get_unique_export_filename(base_filename: str) -> str:
    """
    获取唯一的导出文件名

    Args:
        base_filename: 基础文件名（不含扩展名）

    Returns:
        唯一文件名（如 xxx_edited.md 或 xxx_edited_1.md）
    """
    exports_dir = get_exports_dir()
    filename = f"{base_filename}_edited.md"
    file_path = exports_dir / filename

    if not file_path.exists():
        return filename

    # 文件名冲突，添加后缀
    counter = 1
    while True:
        filename = f"{base_filename}_edited_{counter}.md"
        file_path = exports_dir / filename
        if not file_path.exists():
            return filename
        counter += 1


def parse_doc_title(doc_title: str, base_name: str) -> Dict[str, Any]:
    """
    解析 doc_title 提取标题层级

    doc_title 格式:
    - "{base_name}_概述" → h2: "概述"
    - "{base_name}_{h2}" → h2: "{h2}"
    - "{base_name}_{h2}_{h3}" → h2: "{h2}", h3: "{h3}"

    Returns:
        {"h2": str or None, "h3": str or None}
    """
    # 移除 base_name 前缀
    if doc_title.startswith(f"{base_name}_"):
        remaining = doc_title[len(base_name) + 1:]
    else:
        remaining = doc_title

    parts = remaining.split("_", 1)

    if len(parts) == 1:
        return {"h2": parts[0], "h3": None}
    else:
        return {"h2": parts[0], "h3": parts[1]}


def build_markdown_content(chunks: List[Dict[str, Any]], base_name: str) -> str:
    """
    根据 chunks 构建 Markdown 内容（带标题层级）

    Args:
        chunks: chunk 列表，按 id 排序
        base_name: 文档基础名称

    Returns:
        完整的 Markdown 内容
    """
    lines = []
    current_h2 = None

    for chunk in chunks:
        doc_title = chunk["doc_title"]
        chunk_text = chunk["chunk_text"]

        # 解析标题层级
        title_info = parse_doc_title(doc_title, base_name)
        h2 = title_info["h2"]
        h3 = title_info["h3"]

        # 检查 chunk_text 是否已包含标题
        text_lines = chunk_text.strip().split("\n")
        first_line = text_lines[0].strip() if text_lines else ""

        # 判断是否需要添加标题
        has_h2_in_text = first_line.startswith("## ") and not first_line.startswith("### ")
        has_h3_in_text = first_line.startswith("### ")

        if h3:
            # 三级标题
            if h2 and h2 != current_h2:
                # 新的二级标题
                if not has_h2_in_text:
                    lines.append(f"\n## {h2}\n")
                current_h2 = h2

            if not has_h3_in_text:
                lines.append(f"\n### {h3}\n")
            lines.append(chunk_text.strip())
            lines.append("")
        else:
            # 二级标题
            if h2 != current_h2:
                if not has_h2_in_text:
                    lines.append(f"\n## {h2}\n")
                current_h2 = h2

            # 如果 chunk_text 已有标题，直接添加
            if has_h2_in_text:
                lines.append(chunk_text.strip())
            else:
                lines.append(chunk_text.strip())
            lines.append("")

    return "\n".join(lines).strip() + "\n"


def export_file_chunks(file_id: int) -> Dict[str, Any]:
    """
    导出文件的所有 chunks 为 Markdown 文档

    流程:
    1. 获取文件信息
    2. 获取所有 chunks（按 id 排序）
    3. 构建 Markdown 内容（重建标题层级）
    4. 写入 exports 文件夹

    Returns:
        {
            "success": bool,
            "export_path": str,
            "filename": str,
            "chunk_count": int
        }
    """
    conn = get_connection()
    try:
        # 1. 获取文件信息
        file_info = conn.execute(
            "SELECT id, filename FROM files WHERE id = ?", (file_id,)
        ).fetchone()

        if not file_info:
            return {"success": False, "error": "文件不存在"}

        original_filename = file_info["filename"]
        base_name = Path(original_filename).stem

        # 2. 获取所有 chunks
        chunks = conn.execute(
            "SELECT id, doc_title, chunk_text FROM chunks WHERE file_id = ? ORDER BY id",
            (file_id,)
        ).fetchall()

        if not chunks:
            return {"success": False, "error": "文件无切片内容"}

        chunks_list = [dict(c) for c in chunks]

    finally:
        conn.close()

    # 3. 构建 Markdown 内容
    markdown_content = build_markdown_content(chunks_list, base_name)

    # 4. 写入文件
    export_filename = get_unique_export_filename(base_name)
    export_path = get_exports_dir() / export_filename

    with open(export_path, "w", encoding="utf-8") as f:
        f.write(markdown_content)

    return {
        "success": True,
        "export_path": str(export_path),
        "filename": export_filename,
        "chunk_count": len(chunks_list)
    }


def get_export_files_list() -> List[Dict[str, Any]]:
    """
    获取所有导出文件列表

    Returns:
        导出文件信息列表
    """
    exports_dir = get_exports_dir()
    files = []

    for file_path in exports_dir.glob("*.md"):
        stat = file_path.stat()
        files.append({
            "filename": file_path.name,
            "file_path": str(file_path),
            "file_size": stat.st_size,
            "modified_at": stat.st_mtime
        })

    # 按修改时间倒序
    files.sort(key=lambda x: x["modified_at"], reverse=True)
    return files


def delete_export_file(filename: str) -> bool:
    """
    删除导出文件

    Args:
        filename: 导出文件名

    Returns:
        是否删除成功
    """
    export_path = get_exports_dir() / filename

    if not export_path.exists():
        return False

    export_path.unlink()
    return True
