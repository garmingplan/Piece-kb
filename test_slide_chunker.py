"""
测试 SlideChunker 是否正确按页切分
"""

from indexing.services.chunking import SlideChunker

# 测试内容（简化版）
test_content = """<!-- Slide number: 1 -->
基于多智能体的中文超声诊断报告智能校验系统

答辩人：潘嘉明
导师：易法令

### Notes:

<!-- Slide number: 2 -->

01
研究背景与意义

02
研究思路与过程

### Notes:

<!-- Slide number: 3 -->
01
研究背景与意义

### Notes:

<!-- Slide number: 4 -->
研究背景与意义-----临床现状与痛点

![](图片8.jpg)

### Notes:
"""

# 测试分块
chunker = SlideChunker()
chunks = chunker.chunk(test_content, "开题答辩")

print(f"总共生成了 {len(chunks)} 个分块\n")

for i, chunk in enumerate(chunks, 1):
    print(f"=== 分块 {i} ===")
    print(f"标题: {chunk['doc_title']}")
    print(f"内容长度: {len(chunk['chunk_text'])} 字符")
    print(f"内容预览: {chunk['chunk_text'][:100]}...")
    print()
