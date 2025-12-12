"""
测试索引 MCP 服务是否能正常导入
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
ROOT_DIR = Path(__file__).parent.absolute()
sys.path.insert(0, str(ROOT_DIR))

try:
    print("正在导入模块...")
    from indexing.mcp.server import mcp, get_server_info

    print("✅ 模块导入成功!")
    print(f"服务信息: {get_server_info()}")
    print("\n所有工具:")
    for tool_name in get_server_info()["tools"]:
        print(f"  - {tool_name}")

except Exception as e:
    print(f"❌ 导入失败: {e}")
    import traceback
    traceback.print_exc()
