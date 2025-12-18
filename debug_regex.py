import re

# 你提供的分块内容示例
content = """<!-- Slide number: 1 -->
基于多智能体的中文超声诊断报告智能校验系统

答辩人：潘嘉明
导师：易法令

### Notes:

<!-- Slide number: 2 -->

01
研究背景与意义

02
研究思路与过程

03
实验与数据验证

04
可行性与进度

### Notes:

<!-- Slide number: 3 -->
01
研究背景与意义

### Notes:"""

# 测试正则表达式
slide_pattern = r"<!--\s*Slide number:\s*(\d+)\s*-->"
slide_matches = list(re.finditer(slide_pattern, content))

print(f"找到 {len(slide_matches)} 个 Slide 分隔符\n")

for i, match in enumerate(slide_matches):
    print(f"Match {i+1}:")
    print(f"  Slide 编号: {match.group(1)}")
    print(f"  开始位置: {match.start()}")
    print(f"  结束位置: {match.end()}")
    print(f"  匹配内容: {repr(match.group(0))}")
    print()
