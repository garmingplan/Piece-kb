"""
MCP 配置视图

职责:
- 渲染 MCP 配置中栏（客户端列表）
- 渲染 MCP 配置右栏（JSON 配置展示）
"""

import json
import copy
from nicegui import ui

from app.i18n import t
from indexing.settings import get_settings


# MCP 客户端配置模板
# 使用 {port} 占位符，运行时替换为实际端口
# 协议：Streamable HTTP，端点：/mcp
MCP_CLIENTS = [
    # ==================== 代码编辑器 ====================
    {
        "id": "cursor",
        "name": "Cursor",
        "icon": "code",
        "config": {
            "mcpServers": {
                "piece-kb": {
                    "url": "http://localhost:{port}/mcp"
                },
                "piece-index": {
                    "url": "http://localhost:{index_port}/mcp"
                }
            }
        }
    },
    {
        "id": "windsurf",
        "name": "Windsurf",
        "icon": "surfing",
        "config": {
            "mcpServers": {
                "piece-kb": {
                    "serverUrl": "http://localhost:{port}/mcp"
                },
                "piece-index": {
                    "serverUrl": "http://localhost:{index_port}/mcp"
                }
            }
        }
    },
    {
        "id": "vscode",
        "name": "VS Code",
        "icon": "laptop_mac",
        "config": {
            "mcp": {
                "servers": {
                    "piece-kb": {
                        "type": "http",
                        "url": "http://localhost:{port}/mcp"
                    },
                    "piece-index": {
                        "type": "http",
                        "url": "http://localhost:{index_port}/mcp"
                    }
                }
            }
        }
    },
    {
        "id": "visual_studio",
        "name": "Visual Studio 2022",
        "icon": "desktop_windows",
        "config": {
            "servers": {
                "piece-kb": {
                    "type": "http",
                    "url": "http://localhost:{port}/mcp"
                },
                "piece-index": {
                    "type": "http",
                    "url": "http://localhost:{index_port}/mcp"
                }
            }
        }
    },
    # ==================== AI 助手插件 ====================
    {
        "id": "cline",
        "name": "Cline",
        "icon": "terminal",
        "config": {
            "mcpServers": {
                "piece-kb": {
                    "url": "http://localhost:{port}/mcp",
                    "type": "streamableHttp"
                },
                "piece-index": {
                    "url": "http://localhost:{index_port}/mcp",
                    "type": "streamableHttp"
                }
            }
        }
    },
    {
        "id": "github_copilot",
        "name": "GitHub Copilot",
        "icon": "hub",
        "config": {
            "mcp": {
                "servers": {
                    "piece-kb": {
                        "type": "http",
                        "url": "http://localhost:{port}/mcp"
                    },
                    "piece-index": {
                        "type": "http",
                        "url": "http://localhost:{index_port}/mcp"
                    }
                }
            }
        }
    },
    {
        "id": "copilot_coding_agent",
        "name": "Copilot Coding Agent",
        "icon": "precision_manufacturing",
        "config": {
            "mcpServers": {
                "piece-kb": {
                    "type": "http",
                    "url": "http://localhost:{port}/mcp"
                },
                "piece-index": {
                    "type": "http",
                    "url": "http://localhost:{index_port}/mcp"
                }
            }
        }
    },
    {
        "id": "augment_code",
        "name": "Augment Code",
        "icon": "add_circle",
        "config": {
            "augment.advanced": {
                "mcpServers": [
                    {
                        "name": "piece-kb",
                        "url": "http://localhost:{port}/mcp"
                    },
                    {
                        "name": "piece-index",
                        "url": "http://localhost:{index_port}/mcp"
                    }
                ]
            }
        }
    },
    {
        "id": "roo_code",
        "name": "Roo Code",
        "icon": "pets",
        "config": {
            "mcpServers": {
                "piece-kb": {
                    "type": "streamable-http",
                    "url": "http://localhost:{port}/mcp"
                },
                "piece-index": {
                    "type": "streamable-http",
                    "url": "http://localhost:{index_port}/mcp"
                }
            }
        }
    },
    {
        "id": "kilo_code",
        "name": "Kilo Code",
        "icon": "speed",
        "config": {
            "mcpServers": {
                "piece-kb": {
                    "type": "streamable-http",
                    "url": "http://localhost:{port}/mcp",
                    "disabled": False
                },
                "piece-index": {
                    "type": "streamable-http",
                    "url": "http://localhost:{index_port}/mcp",
                    "disabled": False
                }
            }
        }
    },
    {
        "id": "qodo_gen",
        "name": "Qodo Gen",
        "icon": "auto_fix_high",
        "config": {
            "mcpServers": {
                "piece-kb": {
                    "url": "http://localhost:{port}/mcp"
                },
                "piece-index": {
                    "url": "http://localhost:{index_port}/mcp"
                }
            }
        }
    },
    # ==================== Claude 系列 ====================
    {
        "id": "claude_desktop",
        "name": "Claude Desktop",
        "icon": "smart_toy",
        "config": {
            "mcpServers": {
                "piece-kb": {
                    "url": "http://localhost:{port}/mcp"
                },
                "piece-index": {
                    "url": "http://localhost:{index_port}/mcp"
                }
            }
        }
    },
    {
        "id": "claude_code",
        "name": "Claude Code",
        "icon": "data_object",
        "config": {},
        "format": "bash",
        "config_text": """# 添加检索服务
claude mcp add \\
  --header 'Authorization: Bearer {api_key}' \\
  --transport http \\
  piece-kb http://localhost:{port}/mcp

# 添加索引服务
claude mcp add \\
  --header 'Authorization: Bearer {api_key}' \\
  --transport http \\
  piece-index http://localhost:{index_port}/mcp"""
    },
    # ==================== 独立 AI 客户端 ====================
    {
        "id": "cherrystudio",
        "name": "CherryStudio",
        "icon": "chat",
        "config": {
            "mcpServers": {
                "piece-kb": {
                    "isActive": True,
                    "name": "piece-kb",
                    "type": "streamableHttp",
                    "url": "http://localhost:{port}/mcp",
                    "baseUrl": "http://localhost:{port}/mcp"
                },
                "piece-index": {
                    "isActive": True,
                    "name": "piece-index",
                    "type": "streamableHttp",
                    "url": "http://localhost:{index_port}/mcp",
                    "baseUrl": "http://localhost:{index_port}/mcp"
                }
            }
        }
    },
    {
        "id": "opencode",
        "name": "Opencode",
        "icon": "open_in_new",
        "config": {
            "mcp": {
                "piece-kb": {
                    "type": "remote",
                    "url": "http://localhost:{port}/mcp",
                    "enabled": True
                },
                "piece-index": {
                    "type": "remote",
                    "url": "http://localhost:{index_port}/mcp",
                    "enabled": True
                }
            }
        }
    },
    {
        "id": "trae",
        "name": "Trae",
        "icon": "route",
        "config": {
            "mcpServers": {
                "piece-kb": {
                    "url": "http://localhost:{port}/mcp"
                },
                "piece-index": {
                    "url": "http://localhost:{index_port}/mcp"
                }
            }
        }
    },
    {
        "id": "amp",
        "name": "Amp",
        "icon": "bolt",
        "config": {
            "mcpServers": {
                "piece-kb": {
                    "url": "http://localhost:{port}/mcp"
                },
                "piece-index": {
                    "url": "http://localhost:{index_port}/mcp"
                }
            }
        }
    },
    {
        "id": "rovo_dev",
        "name": "Rovo Dev CLI",
        "icon": "developer_mode",
        "config": {
            "mcpServers": {
                "piece-kb": {
                    "url": "http://localhost:{port}/mcp"
                },
                "piece-index": {
                    "url": "http://localhost:{index_port}/mcp"
                }
            }
        }
    },
    # ==================== JetBrains ====================
    {
        "id": "jetbrains",
        "name": "JetBrains AI Assistant",
        "icon": "integration_instructions",
        "config": {
            "mcpServers": {
                "piece-kb": {
                    "url": "http://localhost:{port}/mcp"
                },
                "piece-index": {
                    "url": "http://localhost:{index_port}/mcp"
                }
            }
        }
    },
    {
        "id": "kiro",
        "name": "Kiro",
        "icon": "lightbulb",
        "config": {
            "mcpServers": {
                "piece-kb": {
                    "url": "http://localhost:{port}/mcp",
                    "disabled": False,
                    "autoApprove": []
                },
                "piece-index": {
                    "url": "http://localhost:{index_port}/mcp",
                    "disabled": False,
                    "autoApprove": []
                }
            }
        }
    },
    # ==================== CLI 工具 ====================
    {
        "id": "gemini_cli",
        "name": "Gemini CLI",
        "icon": "stars",
        "config": {
            "mcpServers": {
                "piece-kb": {
                    "httpUrl": "http://localhost:{port}/mcp"
                },
                "piece-index": {
                    "httpUrl": "http://localhost:{index_port}/mcp"
                }
            }
        }
    },
    {
        "id": "qwen_coder",
        "name": "Qwen Coder",
        "icon": "psychology",
        "config": {
            "mcpServers": {
                "piece-kb": {
                    "httpUrl": "http://localhost:{port}/mcp"
                },
                "piece-index": {
                    "httpUrl": "http://localhost:{index_port}/mcp"
                }
            }
        }
    },
    {
        "id": "openai_codex",
        "name": "OpenAI Codex",
        "icon": "memory",
        "config": {
            "[mcp_servers.piece-kb]": {
                "url": "http://localhost:{port}/mcp"
            },
            "[mcp_servers.piece-index]": {
                "url": "http://localhost:{index_port}/mcp"
            }
        },
        "format": "toml",
        "config_text": "[mcp_servers.piece-kb]\nurl = \"http://localhost:{port}/mcp\"\n\n[mcp_servers.piece-kb.headers]\nAuthorization = \"Bearer {api_key}\"\n\n[mcp_servers.piece-index]\nurl = \"http://localhost:{index_port}/mcp\"\n\n[mcp_servers.piece-index.headers]\nAuthorization = \"Bearer {api_key}\""
    },
    {
        "id": "copilot_cli",
        "name": "Copilot CLI",
        "icon": "terminal",
        "config": {
            "mcpServers": {
                "piece-kb": {
                    "type": "http",
                    "url": "http://localhost:{port}/mcp"
                },
                "piece-index": {
                    "type": "http",
                    "url": "http://localhost:{index_port}/mcp"
                }
            }
        }
    },
    {
        "id": "amazon_q",
        "name": "Amazon Q Developer",
        "icon": "cloud",
        "config": {
            "mcpServers": {
                "piece-kb": {
                    "url": "http://localhost:{port}/mcp"
                },
                "piece-index": {
                    "url": "http://localhost:{index_port}/mcp"
                }
            }
        }
    },
    {
        "id": "factory",
        "name": "Factory (droid)",
        "icon": "factory",
        "config": {
            "mcpServers": {
                "piece-kb": {
                    "type": "http",
                    "url": "http://localhost:{port}/mcp"
                },
                "piece-index": {
                    "type": "http",
                    "url": "http://localhost:{index_port}/mcp"
                }
            }
        }
    },
    # ==================== 桌面应用 ====================
    {
        "id": "lm_studio",
        "name": "LM Studio",
        "icon": "science",
        "config": {
            "mcpServers": {
                "piece-kb": {
                    "url": "http://localhost:{port}/mcp"
                },
                "piece-index": {
                    "url": "http://localhost:{index_port}/mcp"
                }
            }
        }
    },
    {
        "id": "warp",
        "name": "Warp",
        "icon": "rocket_launch",
        "config": {
            "piece-kb": {
                "url": "http://localhost:{port}/mcp",
                "start_on_launch": True
            },
            "piece-index": {
                "url": "http://localhost:{index_port}/mcp",
                "start_on_launch": True
            }
        }
    },
    {
        "id": "perplexity",
        "name": "Perplexity Desktop",
        "icon": "search",
        "config": {
            "mcpServers": {
                "piece-kb": {
                    "url": "http://localhost:{port}/mcp"
                },
                "piece-index": {
                    "url": "http://localhost:{index_port}/mcp"
                }
            }
        }
    },
    {
        "id": "boltai",
        "name": "BoltAI",
        "icon": "flash_on",
        "config": {
            "mcpServers": {
                "piece-kb": {
                    "url": "http://localhost:{port}/mcp"
                },
                "piece-index": {
                    "url": "http://localhost:{index_port}/mcp"
                }
            }
        }
    },
    {
        "id": "crush",
        "name": "Crush",
        "icon": "favorite",
        "config": {
            "mcp": {
                "piece-kb": {
                    "type": "http",
                    "url": "http://localhost:{port}/mcp"
                },
                "piece-index": {
                    "type": "http",
                    "url": "http://localhost:{index_port}/mcp"
                }
            }
        }
    },
    {
        "id": "zencoder",
        "name": "Zencoder",
        "icon": "self_improvement",
        "config": {
            "mcpServers": {
                "piece-kb": {
                    "url": "http://localhost:{port}/mcp"
                },
                "piece-index": {
                    "url": "http://localhost:{index_port}/mcp"
                }
            }
        }
    },
    {
        "id": "google_antigravity",
        "name": "Google Antigravity",
        "icon": "public",
        "config": {
            "mcpServers": {
                "piece-kb": {
                    "serverUrl": "http://localhost:{port}/mcp"
                },
                "piece-index": {
                    "serverUrl": "http://localhost:{index_port}/mcp"
                }
            }
        }
    },
]


def _get_config_json(client: dict) -> str:
    """
    获取客户端配置字符串

    替换 {port} 占位符为实际端口（检索 MCP）
    替换 {index_port} 占位符为索引 MCP 端口
    替换 {api_key} 占位符为 MCP API 密钥
    支持 JSON 和 TOML 格式
    """
    settings = get_settings()
    retrieval_port = settings.mcp.port  # 检索 MCP 端口（8686）
    index_port = settings.mcp.port + 1  # 索引 MCP 端口（8687）
    api_key = settings.mcp.api_key  # MCP API 密钥
    auth_enabled = settings.mcp.auth_enabled and bool(api_key)

    # 如果有 config_text 字段（如 TOML 格式），直接使用
    if "config_text" in client:
        config_str = client["config_text"]
    else:
        # 深拷贝配置以避免修改原始模板
        config = copy.deepcopy(client["config"])

        # 如果认证启用，为配置添加 Authorization 头
        if auth_enabled:
            _add_auth_headers(config, api_key)

        # 默认使用 JSON 格式
        config_str = json.dumps(config, indent=2, ensure_ascii=False)

    # 替换端口占位符
    config_str = config_str.replace("{port}", str(retrieval_port))
    config_str = config_str.replace("{index_port}", str(index_port))
    config_str = config_str.replace("{api_key}", api_key)

    return config_str


def _add_auth_headers(config: dict, api_key: str):
    """
    为配置添加 Authorization 头

    支持多种客户端配置格式
    """
    auth_header = {"Authorization": f"Bearer {api_key}"}

    # 处理 mcpServers 格式（最常见）
    if "mcpServers" in config:
        for server_config in config["mcpServers"].values():
            if isinstance(server_config, dict):
                server_config["headers"] = auth_header

    # 处理 mcp.servers 格式（VS Code, GitHub Copilot）
    if "mcp" in config and isinstance(config["mcp"], dict):
        servers = config["mcp"].get("servers", config["mcp"])
        for server_config in servers.values():
            if isinstance(server_config, dict):
                server_config["headers"] = auth_header

    # 处理 servers 格式（Visual Studio）
    if "servers" in config and "mcp" not in config:
        for server_config in config["servers"].values():
            if isinstance(server_config, dict):
                server_config["headers"] = auth_header

    # 处理 augment.advanced.mcpServers 格式（Augment Code）
    if "augment.advanced" in config:
        mcp_servers = config["augment.advanced"].get("mcpServers", [])
        for server_config in mcp_servers:
            if isinstance(server_config, dict):
                server_config["headers"] = auth_header

    # 处理 Warp 格式（piece-kb 直接在根级别）
    for key in list(config.keys()):
        if key.startswith("piece-") and isinstance(config[key], dict) and "url" in config[key]:
            config[key]["headers"] = auth_header


def _get_config_language(client: dict) -> str:
    """获取配置文件的语言类型"""
    return client.get("format", "json")


def render_mcp_config_middle(
    selected_client: dict,
    ui_refs: dict,
    on_select_client: callable,
):
    """
    渲染 MCP 配置中栏（客户端列表）

    Args:
        selected_client: 选中的客户端 {"value": str | None}
        ui_refs: UI 组件引用字典
        on_select_client: 选择客户端的回调
    """
    with ui.column().classes(
        "w-64 h-full flex flex-col overflow-hidden theme-panel"
    ).style("border-right: 1px solid var(--border-color)"):
        # 顶部标题栏
        with ui.row().classes(
            "w-full px-3 items-center justify-between"
        ).style("border-bottom: 1px solid var(--border-color); height: 49px"):
            ui.label(t("mcp_config.title")).classes("text-sm font-medium theme-text")

        # 客户端列表
        with ui.scroll_area().classes("flex-1"):
            @ui.refreshable
            def client_list():
                for client in MCP_CLIENTS:
                    is_selected = selected_client["value"] == client["id"]
                    container_classes = "w-full px-3 py-3 cursor-pointer transition-colors border-l-4 "
                    if is_selected:
                        container_classes += "theme-border-selected theme-selected"
                    else:
                        container_classes += "border-l-transparent theme-hover"

                    with ui.element("div").classes(container_classes).style(
                        "border-bottom: 1px solid var(--border-color)"
                    ).on("click", lambda _, c=client: on_select_client(c["id"])):
                        with ui.row().classes("items-center gap-2"):
                            ui.icon(client["icon"], size="xs").classes(
                                "theme-text-accent" if is_selected else "theme-text-muted"
                            )
                            ui.label(client["name"]).classes("text-sm theme-text")

            ui_refs["client_list"] = client_list
            client_list()


def render_mcp_config_right(
    selected_client: dict,
):
    """
    渲染 MCP 配置右栏（JSON 配置展示）

    Args:
        selected_client: 选中的客户端 {"value": str | None}
    """
    with ui.column().classes("flex-1 h-full flex flex-col theme-content"):
        # 查找选中的客户端
        client = None
        if selected_client["value"]:
            client = next(
                (c for c in MCP_CLIENTS if c["id"] == selected_client["value"]),
                None
            )

        # 顶部信息区
        if client:
            icon, title = client["icon"], client["name"]
        else:
            icon, title = "settings_input_component", t("mcp_config.title")

        with ui.row().classes(
            "w-full px-5 items-center justify-between theme-sidebar"
        ).style("border-bottom: 1px solid var(--border-color); height: 49px"):
            with ui.row().classes("items-center gap-2"):
                ui.icon(icon, size="xs").classes("theme-text-accent")
                ui.label(title).classes("text-sm font-medium theme-text")

        # 配置内容区
        with ui.scroll_area().classes("flex-1 p-4"):
            if client is None:
                # 未选择客户端
                with ui.column().classes("w-full h-full items-center justify-center"):
                    ui.icon("settings_input_component", size="lg").classes("theme-text-muted")
                    ui.label(t("mcp_config.select_client")).classes("text-sm mt-2 theme-text-muted")
            else:
                # 显示配置
                config_text = _get_config_json(client)
                config_lang = _get_config_language(client)

                with ui.card().classes("w-full theme-card").style(
                    "border: 1px solid var(--border-color)"
                ):
                    with ui.column().classes("w-full gap-3 p-4"):
                        # 说明文字
                        ui.label(t("mcp_config.hint")).classes("text-sm theme-text-muted")

                        # 代码块（支持 JSON 和 TOML）
                        ui.code(config_text, language=config_lang).classes("w-full")

                        # 复制按钮
                        with ui.row().classes("w-full justify-end"):
                            async def copy_config(text=config_text):
                                await ui.run_javascript(
                                    f'navigator.clipboard.writeText({json.dumps(text)})'
                                )
                                ui.notify(t("mcp_config.copied"), type="positive")

                            ui.button(
                                t("mcp_config.copy_btn"),
                                icon="content_copy",
                                on_click=copy_config
                            ).props("flat dense").classes("theme-text-accent")
