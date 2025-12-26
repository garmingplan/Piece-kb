"""
按页面切分策略

适用于: PDF (.pdf)
识别 PyMuPDF 转换后的页面分隔符
"""

import re
from typing import List, Dict
from .base import BaseChunker
from .heading_chunker import HeadingChunker
from .utils import recursive_split


class PageChunker(BaseChunker):
    """按页面切分文档"""

    def __init__(self):
        """初始化分块器"""
        super().__init__()

    def chunk(self, content: str, base_name: str) -> List[Dict[str, str]]:
        """
        按页面切分文档

        PyMuPDF 转换格式:
        <!-- Page 1 -->
        内容...
        <!-- Page 2 -->
        内容...

        Args:
            content: Markdown 文档内容
            base_name: 文档基础名称（用于生成 doc_title）

        Returns:
            切片列表，每个切片包含 doc_title 和 chunk_text
        """
        # 匹配页面分隔符：<!-- Page N -->
        page_pattern = r"<!--\s*Page\s+(\d+)\s*-->"
        page_matches = list(re.finditer(page_pattern, content))

        # 未找到页面分隔符，回退到标题切分
        if not page_matches:
            heading_chunker = HeadingChunker()
            return heading_chunker.chunk(content, base_name)

        chunks = []

        for i, match in enumerate(page_matches):
            page_num = match.group(1)  # 提取页码
            start = match.end()  # 页面分隔符之后的内容
            end = (
                page_matches[i + 1].start()
                if i + 1 < len(page_matches)
                else len(content)
            )
            page_content = content[start:end].strip()

            if page_content:
                # 检查单页大小是否超过限制
                if len(page_content) > self.max_chunk_size:
                    # 超大页面：递归切分为多个部分
                    sub_chunks = recursive_split(page_content, chunk_size=self.max_chunk_size)
                    for j, sub_chunk in enumerate(sub_chunks, start=1):
                        if sub_chunk.strip():
                            chunks.append({
                                "doc_title": f"{base_name}_第{page_num}页_第{j}部分",
                                "chunk_text": sub_chunk.strip(),
                            })
                else:
                    # 正常大小：一页一个切片
                    chunks.append({
                        "doc_title": f"{base_name}_第{page_num}页",
                        "chunk_text": page_content,
                    })

        return chunks
