# 知识库+3.2 — 企业级文件搜索与 AI 问答助手

知识库+3.2 是一款面向企业知识库场景的桌面应用，集成**全量文件搜索**、**AI 问答**和**网页搜索**三大功能。现代化 UI 设计，支持连续对话，提供本地与云端多模型选择。

---

## ✨ 功能特性

### 文件搜索
- **双源搜索** — 本地知识库 / NAS 网盘，可独立切换或全量搜索
- **文件名 + 内容** — 支持按文件名精准匹配，或深入文件内容检索（txt / md / docx / pdf / csv 等）
- **实时结果** — 毫秒级响应，结果按类型分组显示

### AI 问答
- **连续对话** — 支持多轮上下文对话，保留问答历史
- **模型自由切换** — 本地 Ollama / DeepSeek API / 智谱云端 / SenseNova 商汤
- **文本选择复制** — 问答内容可自由鼠标选择、右键复制
- **气泡式对话 UI** — 现代化聊天气泡布局，阅读体验自然
- **知识库 + 网页联动** — 搜索结果可直接发送给 AI 做二次分析

### 网页搜索
- **Bing 搜索集成** — 一键获取网络最新信息
- **结果 → AI 分析** — 网页搜索结果无缝衔接 AI 问答

### 支持的 AI 模型

| 提供商 | 模型 | 类型 | 所需 API Key |
|--------|------|------|-------|
| 本地 Ollama | `qwen2.5:3b`（自动检测） | 本地推理 | 无需 |
| DeepSeek | `deepseek-chat` | 云端 API | ✅ |
| 智谱云端 | `glm-4-flash` | 云端 API | ✅ |
| SenseNova 商汤 | `SenseChat-5` | 云端 API | ✅ |

---

## 🚀 快速开始

### 方式一：下载安装包（推荐）

从 [Releases](../../releases) 下载 `知识库+3.2_Installer.exe`，双击安装即可。安装包附带 55 个完整知识库文档作为示例。

### 方式二：从源码运行（开发）

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 运行
python main.py
```

> **环境要求**：Python 3.11 及以上，Windows 10/11

### 使用流程

1. **文件搜索** — 输入关键词 → 选择搜索范围（本地 / NAS / 全部） → 可选「含内容」搜索
2. **AI 问答** — 选择 AI 提供商 → 配置 API Key（首次使用需在设置内填写） → 输入问题
3. **网页搜索** — 切换到「问题解答」标签页 → 输入搜索词 → 结果可直接发送给 AI

---

## 📁 项目结构

```
知识库+3.2/
├── main.py                 # 程序入口
├── config.py               # 配置管理（用户配置存 %APPDATA%）
├── constants.py            # 常量与 AI 模型配置表
├── requirements.txt        # Python 依赖
├── installer/
│   └── 知识库+3.2.iss      # Inno Setup 安装脚本
├── sample_files/
│   └── 知识库文件/          # 55 个知识库文档（打包时随安装包部署）
├── services/
│   ├── ai_service.py       # AI 问答服务（本地 Ollama + 4 家云端 API）
│   ├── file_searcher.py    # 知识库文件检索引擎
│   └── web_searcher.py     # Bing 网页搜索
├── ui/
│   ├── main_window.py      # 主窗口（tab 切换 + 状态管理）
│   ├── search_panel.py     # 搜索面板（范围选择器 + 结果列表）
│   ├── settings_window.py  # 设置窗口（AI Key / 搜索路径）
│   ├── web_panel.py        # 网页搜索 + AI 问答面板
│   └── widgets.py          # 通用 UI 组件
└── utils/
    ├── helpers.py           # 工具函数（图标 / 大小格式化 / 文本检测）
    └── logger.py            # 日志
```

---

## 🛠 技术栈

| 类别 | 选型 |
|------|------|
| **语言** | Python 3.12 |
| **GUI** | Tkinter (ttk) |
| **打包** | PyInstaller (单文件 exe) |
| **安装包** | Inno Setup 6 |
| **AI API** | OpenAI 兼容协议 + 智谱/商汤原生接口 |
| **文件解析** | python-docx + PyMuPDF |

---

## 📦 自行打包

```bash
# 1. 生成 exe
pyinstaller --noconfirm --onefile --windowed --name "知识库+3.2" --icon "app_icon正式.ico" main.py

# 2. 编译安装包（需先安装 Inno Setup 6）
ISCC.exe installer\知识库+3.2.iss
```

产物位于 `dist/` 目录：
- `知识库+3.2.exe` — 单文件可执行程序
- `知识库+3.2_Installer.exe` — 完整安装包

---

## 📋 更新记录

### v3.2
- ✨ UI 全面优化：聊天气泡、现代化下拉框、可选择复制的对话文本
- ✨ 对话稳定性增强：连续对话上下文管理
- ✨ 新增 AI 提供商：智谱云端、SenseNova 商汤

---

## 📄 许可证

[MIT](./LICENSE)

Copyright (c) 2026 Jeff-code310
