"""
Piece 打包脚本

使用方式:
    python build.py

功能:
1. 使用 PyInstaller 打包为目录式 EXE
2. 添加 README.txt
3. 压缩为 ZIP 文件

输出:
    dist/Piece.zip
"""

import os
import sys
import shutil
import subprocess
import zipfile
from pathlib import Path
from datetime import datetime


# 项目根目录
PROJECT_ROOT = Path(__file__).parent

# 输出目录
DIST_DIR = PROJECT_ROOT / "dist"
BUILD_DIR = PROJECT_ROOT / "build"


def clean():
    """清理旧的构建产物"""
    print("[Build] 清理旧的构建产物...")

    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
        print(f"  - 已删除 {DIST_DIR}")

    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
        print(f"  - 已删除 {BUILD_DIR}")


def run_pyinstaller():
    """运行 PyInstaller 打包"""
    print("[Build] 运行 PyInstaller...")

    spec_file = PROJECT_ROOT / "Piece.spec"

    if not spec_file.exists():
        print(f"  [Error] 找不到 {spec_file}")
        sys.exit(1)

    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", str(spec_file), "--noconfirm"],
        cwd=str(PROJECT_ROOT),
    )

    if result.returncode != 0:
        print("  [Error] PyInstaller 打包失败")
        sys.exit(1)

    print("  - PyInstaller 打包完成")


def create_readme():
    """创建 README.txt"""
    print("[Build] 创建 README.txt...")

    readme_content = """Piece - 个人知识库
==================

使用说明:
1. 双击 Piece.exe 启动应用
2. 拖入 PDF 或 Markdown 文件到应用中
3. 在 Claude Desktop 或 Cursor 中配置 MCP 服务
4. 开始对话查询你的知识库

MCP 服务配置:
- 默认端口: 8686
- 端点: http://localhost:8686/mcp

数据存储:
- 数据库和上传文件默认存储在 ./data 目录
- 可在设置中修改存储路径

更多信息请访问: https://github.com/anthropics/piece
"""

    readme_path = DIST_DIR / "Piece" / "README.txt"
    readme_path.write_text(readme_content, encoding="utf-8")
    print(f"  - 已创建 {readme_path}")


def create_zip():
    """创建 ZIP 压缩包"""
    print("[Build] 创建 ZIP 压缩包...")

    piece_dir = DIST_DIR / "Piece"

    if not piece_dir.exists():
        print(f"  [Error] 找不到 {piece_dir}")
        sys.exit(1)

    # 获取版本号（从 i18n 文件读取）
    version = "0.1.0"
    try:
        import json
        zh_json = PROJECT_ROOT / "app" / "i18n" / "locales" / "zh.json"
        if zh_json.exists():
            data = json.loads(zh_json.read_text(encoding="utf-8"))
            version = data.get("app", {}).get("version", "v0.1.0").lstrip("v")
    except Exception:
        pass

    # 生成 ZIP 文件名（带日期）
    date_str = datetime.now().strftime("%Y%m%d")
    zip_name = f"Piece_v{version}_{date_str}.zip"
    zip_path = DIST_DIR / zip_name

    # 创建 ZIP
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in piece_dir.rglob("*"):
            if file_path.is_file():
                arcname = file_path.relative_to(DIST_DIR)
                zf.write(file_path, arcname)

    print(f"  - 已创建 {zip_path}")

    # 输出 ZIP 大小
    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"  - 文件大小: {size_mb:.1f} MB")


def main():
    """主函数"""
    print("=" * 50)
    print("Piece 打包脚本")
    print("=" * 50)

    # 1. 清理
    clean()

    # 2. PyInstaller 打包
    run_pyinstaller()

    # 3. 创建 README
    create_readme()

    # 4. 创建 ZIP
    create_zip()

    print("=" * 50)
    print("[Build] 打包完成!")
    print(f"输出目录: {DIST_DIR}")
    print("=" * 50)


if __name__ == "__main__":
    main()
