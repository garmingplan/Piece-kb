# -*- mode: python ; coding: utf-8 -*-
"""
Piece PyInstaller 打包配置

使用方式:
    pyinstaller Piece.spec

输出:
    dist/Piece/
    ├── Piece.exe
    ├── _internal/
    └── ...
"""

import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import copy_metadata, collect_data_files

# 项目根目录
PROJECT_ROOT = Path(SPECPATH)

# 查找 sqlite_vec 的 DLL 路径
def find_sqlite_vec_dll():
    """查找 sqlite_vec 的 vec0.dll 路径"""
    try:
        import sqlite_vec
        sqlite_vec_dir = Path(sqlite_vec.__file__).parent
        dll_path = sqlite_vec_dir / "vec0.dll"
        if dll_path.exists():
            return str(dll_path)
    except ImportError:
        pass
    return None

# 收集二进制文件
binaries = []
sqlite_vec_dll = find_sqlite_vec_dll()
if sqlite_vec_dll:
    # 将 vec0.dll 放到 sqlite_vec 包目录下
    binaries.append((sqlite_vec_dll, 'sqlite_vec'))

# 收集数据文件
datas = [
    # 图标
    (str(PROJECT_ROOT / 'assets' / 'icon.ico'), 'assets'),
    # 国际化文件
    (str(PROJECT_ROOT / 'app' / 'i18n' / 'locales'), 'app/i18n/locales'),
]

# 添加包元数据（解决 importlib.metadata.PackageNotFoundError）
datas += copy_metadata('fastmcp')
datas += copy_metadata('nicegui')
datas += copy_metadata('uvicorn')
datas += copy_metadata('starlette')
datas += copy_metadata('httpx')
datas += copy_metadata('openai')
datas += copy_metadata('pydantic')
datas += copy_metadata('langchain-core')
datas += copy_metadata('langchain-openai')
datas += copy_metadata('langgraph')

# 收集 jieba 词典文件
datas += collect_data_files('jieba')

# 隐式导入（PyInstaller 无法自动检测的模块）
hiddenimports = [
    # NiceGUI 相关
    'nicegui',
    'webview',
    # 数据库相关
    'sqlite3',
    'sqlite_vec',
    # MCP/FastAPI 相关
    'fastmcp',
    'uvicorn',
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    'starlette',
    'starlette.routing',
    'starlette.responses',
    'starlette.middleware',
    'starlette.middleware.cors',
    'anyio',
    'anyio._backends',
    'anyio._backends._asyncio',
    # LangChain 相关
    'langchain_core',
    'langchain_openai',
    'langgraph',
    # 其他
    'pydantic',
    'httpx',
    'openai',
    'jieba',
    'aiofiles',
    'pystray',
    'PIL',
    'PIL.Image',
    # PDF 处理
    'pymupdf4llm',
    'markitdown',
]

# 排除不需要的模块（减小体积）
excludes = [
    'tkinter',
    'matplotlib',
    'scipy',
    'numpy.testing',
]

block_cipher = None

a = Analysis(
    [str(PROJECT_ROOT / 'app' / 'server.py')],
    pathex=[str(PROJECT_ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Piece',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # 无控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(PROJECT_ROOT / 'assets' / 'icon.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Piece',
)
