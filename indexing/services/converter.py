"""
文件格式转换模块

职责:
- 将各种格式文件转换为 Markdown
- PDF 使用 PyMuPDF Native 流式处理（内存安全）
- 支持多种文档格式（.md, .pdf, .docx, .pptx, .xlsx）
"""

from pathlib import Path

import pymupdf
from markitdown import MarkItDown


# 支持的文件格式
SUPPORTED_FORMATS = {".md", ".pdf", ".docx", ".pptx", ".xlsx"}

# PDF 处理限制
MAX_PDF_PAGES = 3000  # 最大页数限制（提高到 3000 页）


def _format_page_to_markdown(page_dict: dict, page_num: int) -> str:
    """
    将 PyMuPDF 页面字典转换为 Markdown 格式

    Args:
        page_dict: PyMuPDF page.get_text("dict") 返回的字典
        page_num: 页码（从 0 开始）

    Returns:
        Markdown 格式的页面内容
    """
    lines = [f"<!-- Page {page_num + 1} -->\n"]

    for block in page_dict.get("blocks", []):
        if block["type"] == 0:  # 文本块
            block_lines = []

            for line in block.get("lines", []):
                line_text = ""
                max_font_size = 0

                for span in line.get("spans", []):
                    text = span.get("text", "").strip()
                    font_size = span.get("size", 12)
                    max_font_size = max(max_font_size, font_size)
                    line_text += text + " "

                line_text = line_text.strip()
                if not line_text:
                    continue

                # 根据字体大小判断标题
                if max_font_size > 16:
                    block_lines.append(f"## {line_text}")
                elif max_font_size > 14:
                    block_lines.append(f"### {line_text}")
                else:
                    block_lines.append(line_text)

            if block_lines:
                lines.append("\n".join(block_lines) + "\n")

        elif block["type"] == 1:  # 图片块
            lines.append("[图片]\n")

    return "\n".join(lines)


def convert_pdf_to_markdown(
    file_path: Path, progress_callback=None
) -> str:
    """
    将 PDF 转换为 Markdown 格式（使用 PyMuPDF Native 流式处理）

    特点:
    - 逐页处理，内存可控
    - 无内存泄漏
    - 支持超大文件（3000+ 页）
    - 自动识别标题（根据字体大小）

    Args:
        file_path: PDF 文件路径
        progress_callback: 进度回调函数 callback(current_page, total_pages)

    Returns:
        Markdown 格式的文本内容

    Raises:
        ValueError: PDF 页数超过限制
    """
    import logging
    logger = logging.getLogger(__name__)

    doc = pymupdf.open(str(file_path))
    total_pages = len(doc)

    # 检查页数限制
    if total_pages > MAX_PDF_PAGES:
        doc.close()
        raise ValueError(f"PDF 页数过多（{total_pages} 页），最大支持 {MAX_PDF_PAGES} 页")

    logger.info(f"[PDF转换] 开始转换: {file_path.name}, 总页数: {total_pages}")
    markdown_parts = []

    # 逐页处理（流式，内存安全）
    for page_num in range(total_pages):
        try:
            page = doc.load_page(page_num)

            # 提取页面字典（包含文本、字体、位置等信息）
            page_dict = page.get_text("dict")

            # 转换为 Markdown
            page_md = _format_page_to_markdown(page_dict, page_num)
            markdown_parts.append(page_md)

            # 释放页面对象（控制内存）
            page = None

            # 进度回调（每 10 页报告一次，减少数据库压力）
            if progress_callback and (page_num + 1) % 10 == 0:
                progress_callback(page_num + 1, total_pages)
                logger.info(f"[PDF转换] 进度: {page_num + 1}/{total_pages} 页")

        except Exception as e:
            # 单页转换失败不中断整体流程，记录错误信息
            markdown_parts.append(
                f"\n\n---\n**[Page {page_num + 1} - 转换失败: {str(e)[:50]}]**\n---\n\n"
            )

    # 最后一次进度回调（确保 100% 完成）
    if progress_callback:
        progress_callback(total_pages, total_pages)

    doc.close()
    logger.info(f"[PDF转换] 完成: {file_path.name}")
    return "\n\n".join(markdown_parts)


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
        # PDF 使用 PyMuPDF Native 流式处理
        return convert_pdf_to_markdown(file_path)
    else:
        # 其他格式使用 MarkItDown 转换
        md = MarkItDown()
        result = md.convert(str(file_path))
        return result.markdown or ""
