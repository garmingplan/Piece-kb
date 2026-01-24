"""
设置操作处理器

职责:
- 初始化设置表单数据
- 保存设置
"""

import asyncio

from nicegui import ui

from indexing.settings import (
    get_settings, save_settings, reload_settings,
    AppSettings, EmbeddingSettings, McpSettings, AppearanceSettings, WebDAVSettings
)
from indexing.services import refresh_embeddings_instance
from app.i18n import t, set_language


class SettingsHandlers:
    """设置操作处理器"""

    def __init__(self, settings_form: dict):
        """
        初始化设置处理器

        Args:
            settings_form: 设置表单数据字典
        """
        self.settings_form = settings_form

    def init_settings_form(self):
        """初始化设置表单数据"""
        settings = get_settings()
        self.settings_form.clear()
        self.settings_form.update({
            "base_url": settings.embedding.base_url,
            "api_key": settings.embedding.api_key,
            "model": settings.embedding.model,
            "vector_dim": settings.embedding.vector_dim,
            "max_tokens": settings.embedding.max_tokens,
            "mcp_port": settings.mcp.port,
            "data_path": settings.data_path,
            "theme": settings.appearance.theme,
            "language": settings.appearance.language,
            # WebDAV 配置
            "webdav_enabled": settings.webdav.enabled,
            "webdav_hostname": settings.webdav.hostname,
            "webdav_username": settings.webdav.username,
            "webdav_password": settings.webdav.password,
        })

    def save_settings_form(self):
        """保存设置"""
        try:
            old_settings = get_settings()
            new_settings = AppSettings(
                embedding=EmbeddingSettings(
                    base_url=self.settings_form["base_url"],
                    api_key=self.settings_form["api_key"],
                    model=self.settings_form["model"],
                    vector_dim=int(self.settings_form["vector_dim"]),
                    max_tokens=int(self.settings_form.get("max_tokens", 8192)),
                ),
                mcp=McpSettings(port=int(self.settings_form["mcp_port"])),
                appearance=AppearanceSettings(
                    theme=self.settings_form["theme"],
                    language=self.settings_form["language"],
                ),
                webdav=WebDAVSettings(
                    enabled=self.settings_form.get("webdav_enabled", False),
                    hostname=self.settings_form.get("webdav_hostname", ""),
                    username=self.settings_form.get("webdav_username", ""),
                    password=self.settings_form.get("webdav_password", ""),
                ),
                data_path=self.settings_form["data_path"],
            )

            if save_settings(new_settings):
                # 检测哪些设置发生了变化，需要重启
                needs_restart = []

                if old_settings.mcp.port != new_settings.mcp.port:
                    needs_restart.append("MCP端口")

                if old_settings.data_path != new_settings.data_path:
                    needs_restart.append("数据路径")

                # 切换语言（立即生效）
                if old_settings.appearance.language != new_settings.appearance.language:
                    set_language(self.settings_form["language"])

                # 检测 embedding 配置变更，刷新实例缓存
                embedding_changed = (
                    old_settings.embedding.base_url != new_settings.embedding.base_url
                    or old_settings.embedding.api_key != new_settings.embedding.api_key
                    or old_settings.embedding.model != new_settings.embedding.model
                )
                if embedding_changed:
                    refresh_embeddings_instance()

                # 根据情况显示不同提示
                if needs_restart:
                    restart_items = "、".join(needs_restart)
                    ui.notify(
                        t("settings.saved_need_restart", items=restart_items),
                        type="warning",
                        close_button=True,
                        timeout=5000
                    )
                else:
                    ui.notify(t("settings.saved_immediately"), type="positive")
            else:
                ui.notify(t("settings.save_failed"), type="negative")
        except Exception as e:
            ui.notify(f"{t('settings.save_failed')}: {e}", type="negative")

    async def test_embedding_connection(self, test_result_label, test_btn):
        """测试嵌入模型连接"""
        test_btn.props("loading")
        test_result_label.set_text(t("settings_embedding.testing"))

        try:
            from indexing.services import get_embeddings_model_with_config

            # 使用表单配置创建临时实例（不缓存）
            # 将实例化放到线程中，避免首次创建时阻塞事件循环
            embeddings = await asyncio.to_thread(
                lambda: get_embeddings_model_with_config(
                    base_url=self.settings_form["base_url"],
                    api_key=self.settings_form["api_key"],
                    model=self.settings_form["model"],
                )
            )

            result = await asyncio.to_thread(
                embeddings.embed_query, "test"
            )

            actual_dim = len(result)
            expected_dim = int(self.settings_form["vector_dim"])

            if actual_dim == expected_dim:
                test_result_label.set_text(t("settings_embedding.test_success", dim=actual_dim))
                test_result_label.classes(remove="theme-text-muted", add="text-green-500")
            else:
                test_result_label.set_text(
                    t("settings_embedding.test_dim_mismatch", actual=actual_dim, expected=expected_dim)
                )
                test_result_label.classes(remove="theme-text-muted", add="text-red-500")

        except Exception as e:
            error_msg = str(e)
            if len(error_msg) > 100:
                error_msg = error_msg[:100] + "..."
            test_result_label.set_text(t("settings_embedding.test_failed", error=error_msg))
            test_result_label.classes(remove="theme-text-muted", add="text-red-500")
        finally:
            test_btn.props(remove="loading")

    async def test_webdav_connection(self, test_result_label, test_btn):
        """测试 WebDAV 连接"""
        test_btn.props("loading")
        test_result_label.set_text(t("settings_webdav.testing"))
        test_result_label.classes(remove="text-green-500 text-red-500", add="theme-text-muted")

        try:
            from webdav4.client import Client

            hostname = self.settings_form.get("webdav_hostname", "").strip()
            username = self.settings_form.get("webdav_username", "").strip()
            password = self.settings_form.get("webdav_password", "").strip()

            if not hostname or not username or not password:
                test_result_label.set_text(t("settings_webdav.test_failed", error="请填写完整配置"))
                test_result_label.classes(remove="theme-text-muted", add="text-red-500")
                return

            client = Client(
                hostname,
                auth=(username, password),
                timeout=10.0
            )

            # 尝试列出根目录来验证连接
            def test_connection():
                try:
                    client.ls("/")
                    return True, None
                except Exception as e:
                    return False, str(e)

            success, error = await asyncio.to_thread(test_connection)

            if success:
                test_result_label.set_text(t("settings_webdav.test_success"))
                test_result_label.classes(remove="theme-text-muted", add="text-green-500")
            else:
                error_msg = error or "未知错误"
                if len(error_msg) > 80:
                    error_msg = error_msg[:80] + "..."
                test_result_label.set_text(t("settings_webdav.test_failed", error=error_msg))
                test_result_label.classes(remove="theme-text-muted", add="text-red-500")

        except Exception as e:
            error_msg = str(e)
            if len(error_msg) > 80:
                error_msg = error_msg[:80] + "..."
            test_result_label.set_text(t("settings_webdav.test_failed", error=error_msg))
            test_result_label.classes(remove="theme-text-muted", add="text-red-500")
        finally:
            test_btn.props(remove="loading")
