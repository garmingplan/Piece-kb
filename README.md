<h1 align="center">Piece</h1>

<p align="center">
  <img src="assets/icon.ico" alt="Piece Icon" width="128" height="128">
</p>

<p align="center">
  <strong>拒绝 RAG 黑盒 · 混合智能检索 · 本地化 MCP 服务</strong>
</p>

<p align="center">
  <a href="https://github.com/your-repo/Piece/releases">
    <img src="https://img.shields.io/github/v/release/your-repo/Piece?label=版本" alt="Release">
  </a>
  <img src="https://img.shields.io/badge/平台-Windows%20%7C%20macOS-blue" alt="Platform">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
</p>

---

**Piece** 是一款**个人知识库 RAG MCP Server**，专为 AI 时代打造。它为 Claude Desktop、Cursor 等 AI 客户端提供本地文档检索能力，让 AI 能够基于你的个人知识库进行对话和回答。

**核心特点**：桌面应用 + MCP 服务 + RAG 检索，你完全掌控自己的数据。

## 💡 适用场景

- 📚 为 AI 提供论文和研究资料的检索能力
- 💼 让 AI 基于你的工作文档和技术规范回答问题
- 📝 将个人笔记转化为 AI 可查询的知识库
- 🤖 为 AI 助手注入专属领域知识

## ✨ 核心亮点

### 📦 开箱即用 & 后台常驻

- **无需 Docker**：双击即用的独立桌面应用
- **托盘常驻**：最小化后持续运行，MCP 服务随时响应

### 🧠 两段式 Agentic 智能检索

**解决痛点**：传统 RAG 直接返回文本片段，容易出现**主题错配**（答非所问）。

**Piece 的方案**：

- **第一段 - 找到相关主题**：混合检索（BM25 关键词 + Vector 语义）+ RRF 重排，智能定位最相关的文档标题
- **第二段 - 精准提取内容**：根据标题快速获取完整上下文，避免碎片化

**效果**：
- **理想情况**：索引良好、主题明确时，检索准确度大幅提升，主题错配显著减少
- **效果下限**：即使索引质量一般，至少保证混合检索 + 重排的基础效果

**额外优势**：

- **透明可控**：可查看、编辑每个检索单元，手动优化索引质量
- **智能分块**：自动识别标题层级，帮助建立良好索引

### 🔌 自由选择模型

你可以自由配置嵌入（Embedding）模型：

- **本地模型**（Ollama）→ 极致隐私
- **云端 API**（OpenAI / SiliconFlow）→ 更强性能

你的数据，你做主。

### ✨ 数据完全掌控

- **可视化管理**：查看、编辑、新增或删除文档切片
- **数据导出**：将优化后的切片合并导出为 Markdown 文档

### ☁️ WebDAV 云同步

内置 WebDAV 协议支持（如坚果云），多设备间安全同步文件。

### ⚡ 快速接入 AI 客户端

**基于 HTTP 协议的 MCP 服务**，兼容性极强：

- 一键复制配置即可接入 Claude Desktop、Cursor 等
- 提供 2 个 MCP 工具：`resolve-keywords`（智能检索）+ `get-docs`（文档获取）
- AI 客户端可直接调用，实现"对话式查询知识库"

## 🚀 快速开始

### 下载安装

前往 [Releases](https://github.com/your-repo/Piece/releases) 下载最新版本

- **Windows**：解压后双击 `Piece.exe`
- **macOS**：解压后双击 `Piece.app`（首次运行可能需要在系统设置中允许）

### 三步上手

**1. 配置嵌入模型**

在设置页面填入嵌入模型配置（支持 OpenAI / SiliconFlow / Ollama 等）

**2. 导入文档**

拖入 PDF 或 Markdown 文件，应用会自动完成索引

**3. 连接 AI 客户端**

在 MCP 配置页面复制配置到 Claude Desktop，即可开始对话查询

### 界面预览

<p align="center">
  <img src="doc/screenshot.png" alt="Piece 界面预览" width="800">
</p>

> 提示：如果图片无法显示，请访问 [Releases](https://github.com/your-repo/Piece/releases) 查看完整截图。

## 📄 License

MIT License © 2024 Piece
