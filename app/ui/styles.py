"""
主题样式模块

职责:
- 定义 CSS 变量和主题样式
- 提供主题初始化和切换功能
"""

from nicegui import ui


# 主题 CSS 样式
THEME_CSS = '''
<style>
    :root {
        /* 浅色主题（默认） */
        --bg-sidebar: #f8f9fa;
        --bg-panel: #ffffff;
        --bg-content: #f1f3f5;
        --bg-card: #ffffff;
        --bg-hover: #e9ecef;
        --bg-selected: #e7f5ff;
        --border-color: #dee2e6;
        --border-selected: #339af0;
        --text-primary: #212529;
        --text-secondary: #495057;
        --text-muted: #868e96;
        --text-accent: #1971c2;
        --code-bg: #f1f3f5;
        --code-text: #c92a2a;
        --pre-bg: #f8f9fa;
        --pre-text: #212529;
    }

    body.body--dark {
        /* 深色主题 - VSCode 风格但稍浅 */
        --bg-sidebar: #2d2d30;
        --bg-panel: #333333;
        --bg-content: #252526;
        --bg-card: #3c3c3c;
        --bg-hover: #454545;
        --bg-selected: #094771;
        --border-color: #454545;
        --border-selected: #339af0;
        --text-primary: #d4d4d4;
        --text-secondary: #cccccc;
        --text-muted: #969696;
        --text-accent: #4fc3f7;
        --code-bg: #2d2d30;
        --code-text: #ce9178;
        --pre-bg: #2d2d30;
        --pre-text: #d4d4d4;
    }

    body.theme-pink {
        /* 少女粉主题 - 仅替换强调色 */
        --bg-selected: #ffe4ec;
        --border-selected: #f8a5c2;
        --text-accent: #f06292;
    }

    /* 选中边框样式 */
    .theme-border-selected {
        border-left-color: var(--border-selected) !important;
    }

    html, body {
        overflow: hidden !important;
        height: 100vh !important;
        margin: 0 !important;
        padding: 0 !important;
    }
    .nicegui-content {
        height: 100vh !important;
        overflow: hidden !important;
        padding: 0 !important;
    }
    .chunk-content h1, .chunk-content h2, .chunk-content h3 {
        color: var(--text-primary) !important;
    }
    .chunk-content h1 {
        font-size: 1.25rem !important;
        line-height: 1.75rem !important;
        font-weight: 600 !important;
        margin-top: 0.5rem !important;
        margin-bottom: 0.5rem !important;
    }
    .chunk-content h2 {
        font-size: 1.1rem !important;
        line-height: 1.5rem !important;
        font-weight: 600 !important;
        margin-top: 0.5rem !important;
        margin-bottom: 0.5rem !important;
    }
    .chunk-content h3 {
        font-size: 1rem !important;
        font-weight: 600 !important;
        margin-top: 0.5rem !important;
        margin-bottom: 0.5rem !important;
    }
    .chunk-content p {
        font-size: 0.875rem !important;
        color: var(--text-secondary) !important;
        margin-bottom: 0.5rem !important;
    }
    .chunk-content ul, .chunk-content ol {
        font-size: 0.875rem !important;
        padding-left: 1.5rem !important;
        margin-bottom: 0.5rem !important;
        color: var(--text-secondary) !important;
    }
    .chunk-content code {
        font-size: 0.8rem !important;
        background-color: var(--code-bg) !important;
        color: var(--code-text) !important;
        padding: 0.125rem 0.25rem !important;
        border-radius: 0.25rem !important;
    }
    .chunk-content pre {
        font-size: 0.8rem !important;
        background-color: var(--pre-bg) !important;
        color: var(--pre-text) !important;
        padding: 0.75rem !important;
        border-radius: 0.375rem !important;
        overflow-x: hidden !important;
        white-space: pre-wrap !important;
        word-wrap: break-word !important;
    }

    /* 切片卡片内容区域 - 禁止水平滚动 */
    .chunk-content {
        overflow-x: hidden !important;
        overflow: hidden !important;
        word-wrap: break-word !important;
        overflow-wrap: break-word !important;
        word-break: break-word !important;
        max-width: 100% !important;
        width: 100% !important;
    }
    .chunk-content * {
        max-width: 100% !important;
        word-wrap: break-word !important;
        overflow-wrap: break-word !important;
        word-break: break-word !important;
    }
    .chunk-content p {
        white-space: pre-wrap !important;
        word-break: break-all !important;
    }
    .chunk-content a {
        word-break: break-all !important;
    }
    .chunk-content table {
        display: block !important;
        overflow-x: auto !important;
        overflow: auto !important;
        width: 100% !important;
        max-width: 100% !important;
        table-layout: fixed !important;
    }
    .chunk-content td, .chunk-content th {
        word-wrap: break-word !important;
        overflow-wrap: break-word !important;
        min-width: 50px !important;
    }
    .chunk-content tbody, .chunk-content thead, .chunk-content tr {
        display: block !important;
        width: 100% !important;
        max-width: 100% !important;
    }

    /* 主题化样式类 */
    .theme-sidebar { background-color: var(--bg-sidebar); border-color: var(--border-color); }
    .theme-panel { background-color: var(--bg-panel); border-color: var(--border-color); }
    .theme-content { background-color: var(--bg-content); }
    .theme-card { background-color: var(--bg-card); border-color: var(--border-color); }
    .theme-hover:hover { background-color: var(--bg-hover); }
    .theme-selected { background-color: var(--bg-selected); }
    .theme-border { border-color: var(--border-color); }
    .theme-text { color: var(--text-primary); }
    .theme-text-secondary { color: var(--text-secondary); }
    .theme-text-muted { color: var(--text-muted); }
    .theme-text-accent { color: var(--text-accent); }
</style>
'''


def inject_theme_css():
    """注入主题 CSS 到页面"""
    ui.add_head_html(THEME_CSS)


def init_theme(dark_mode, theme: str):
    """
    初始化主题

    Args:
        dark_mode: NiceGUI dark_mode 对象
        theme: 主题名称 ('light', 'dark', 'pink')
    """
    if theme == "dark":
        dark_mode.enable()
    elif theme == "pink":
        dark_mode.disable()
        ui.colors(primary='#f06292')
        ui.timer(0.1, lambda: ui.run_javascript("document.body.classList.add('theme-pink')"), once=True)
    else:  # light
        dark_mode.disable()


def apply_theme(dark_mode, theme: str):
    """
    切换主题

    Args:
        dark_mode: NiceGUI dark_mode 对象
        theme: 主题名称 ('light', 'dark', 'pink')
    """
    # 移除所有主题类
    ui.run_javascript("document.body.classList.remove('theme-pink')")

    if theme == "dark":
        dark_mode.enable()
        ui.colors()  # 恢复默认颜色
    elif theme == "pink":
        dark_mode.disable()
        ui.run_javascript("document.body.classList.add('theme-pink')")
        ui.colors(primary='#f06292')  # 设置粉色主色
    else:  # light
        dark_mode.disable()
        ui.colors()  # 恢复默认颜色
