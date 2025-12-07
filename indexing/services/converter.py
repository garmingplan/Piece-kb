"""
文件格式转换模块

职责:
- 将各种格式文件转换为 Markdown
- PDF 分批处理（控制内存）
- 支持多种文档格式（.md, .pdf, .docx, .pptx, .xlsx）
"""

from pathlib import Path

import pymupdf
import pymupdf4llm
from markitdown import MarkItDown


# 支持的文件格式
SUPPORTED_FORMATS = {".md", ".pdf", ".docx", ".pptx", ".xlsx"}

# PDF 处理限制
MAX_PDF_PAGES = 1000  # 最大页数限制
PDF_BATCH_SIZE = 20  # 每批处理的页数


def convert_pdf_to_markdown(file_path: Path) -> str:
    """
    将 PDF 转换为 Markdown 格式（分批处理，控制内存）

    Args:
        file_path: PDF 文件路径

    Returns:
        Markdown 格式的文本内容

    Raises:
        ValueError: PDF 页数超过限制
    """
    doc = pymupdf.open(str(file_path))
    total_pages = len(doc)

    # 检查页数限制
    if total_pages > MAX_PDF_PAGES:
        doc.close()
        raise ValueError(f"PDF 页数过多（{total_pages} 页），最大支持 {MAX_PDF_PAGES} 页")

    # 小文档直接处理
    if total_pages <= PDF_BATCH_SIZE:
        result = pymupdf4llm.to_markdown(doc)
        doc.close()
        return result

    # 大文档分批处理
    md_parts = []
    for start in range(0, total_pages, PDF_BATCH_SIZE):
        end = min(start + PDF_BATCH_SIZE, total_pages)
        pages = list(range(start, end))
        part = pymupdf4llm.to_markdown(doc, pages=pages)
        md_parts.append(part)

    doc.close()
    return "\n\n".join(md_parts)


def convert_to_markdown(file_path: Path) -> str:
    """
    将文件转换为 Markdown 格式

    Args:
        file_path: 文件路径

    Returns:
        Markdown 格式的文本内容

    Raises:
        ValueError: 不支持的文件格式或 PDF 页数超限
        Exception: 转换失败
    """
    suffix = file_path.suffix.lower()

    if suffix not in SUPPORTED_FORMATS:
        raise ValueError(f"不支持的文件格式: {suffix}")

    if suffix == ".md":
        # Markdown 文件直接读取
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    elif suffix == ".pdf":
        # PDF 使用分批处理（控制内存）
        return convert_pdf_to_markdown(file_path)
    else:
        # 其他格式使用 MarkItDown 转换
        md = MarkItDown()
        result = md.convert(str(file_path))
        return result.markdown or ""
