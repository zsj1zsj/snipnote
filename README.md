# SnipNote

一个本地优先、可配置、AI 增强的知识处理系统。适合开发者与重度阅读者。

## 功能

- 保存摘录（手动添加、CSV/JSON/JSONL 导入）
- 链接抓取（输入网页链接自动解析为 Markdown 摘录）
- 基于 SM-2 的间隔复习调度
- 每日回顾摘要（Markdown 输出）
- **Web UI**（本地浏览器使用，现代 React 界面）
- 摘录笔记（选中文字右键添加笔记）
- 收藏功能（收藏 / 取消收藏）
- 已读状态管理
- AI 总结（自动生成摘录摘要）
- AI 建议标签（自动分析内容推荐标签）
- 标签管理页面

## 安装依赖

```bash
# 安装 Python 依赖 (使用 uv)
uv venv .venv
source .venv/bin/activate
uv pip install -r pyproject.toml

# 安装前端依赖（仅首次或更新前端时需要）
cd frontend && npm install && cd ..
```

## 快速开始

### 启动 Web UI

```bash
python3 webui.py
```

然后访问：`http://127.0.0.1:8787`

### 更新前端后重新构建

```bash
cd frontend && npm run build && cd ..
```

### CLI 命令

```bash
# 添加摘录
python3 readlite.py add --text "First highlight" --source "Deep Work" --author "Cal Newport" --tags productivity,focus

# 列出摘录
python3 readlite.py list

# 复习
python3 readlite.py review

# 生成日报
python3 readlite.py daily

# 指定数据库
python3 readlite.py --db /path/to/readlite.db list
```

## Web UI 页面说明

| 页面 | 路径 | 说明 |
|------|------|------|
| 首页 | `/` | 统计概览、最近添加、快速操作 |
| 摘录列表 | `/highlights` | 全部摘录，支持搜索、标签过滤、已读过滤 |
| 摘录详情 | `/highlight/:id` | 查看内容、笔记、摘要、AI 标签 |
| 复习 | `/review` | SM-2 间隔复习 |
| 收藏 | `/favorites` | 收藏列表 |
| 标签 | `/tags` | 标签管理 |
| 日报 | `/daily` | 阅读日报查看与生成 |
| 添加 | `/add` | 手动添加摘录 |
| 从链接添加 | `/add-link` | 输入网址解析内容 |

## 解析规则（配置化）

- 规则引擎支持配置文件：`config/parser_rules.json`
- 解析器模块位于：`parser/engine.py`
- 各域名规则全部在 `config/parser_rules.json` 中维护（`parser/engine.py` 不再内置站点规则）
- 当前内置配置：`solidot.org`、`ifanr.com`、`playno1.com`、`blogjava.net`、`news.yahoo.co.jp`、`medium.com`、`economist.com`、`cnblogs.com`、`liaoxuefeng.com`
- `economist.com` 在疑似 paywall 时会自动尝试通过 `archive.is` 快照抓取正文

### 新增/调整站点规则

在 `config/parser_rules.json` 的 `rules` 下新增规则块，常用字段：

- `domains`：域名列表
- `primary_html_patterns`：正文容器正则
- `drop_patterns`：噪音文本正则
- `image_drop_keywords`：图片 URL 过滤关键词
- `max_images`：最多保留图片数量
- `request_headers`：站点专用请求头

修改配置后重启服务即可生效。

### 需要登录的站点

在 `config/` 目录创建 `cookies.json`：

```json
{
  "example.com": {
    "cookie_name": "cookie_value"
  }
}
```

## 导入格式

支持 `.jsonl` / `.json` / `.csv`：

```csv
text,source,author,location,tags
"We are what we repeatedly do.","Nicomachean Ethics","Aristotle","Book II","habit,virtue"
```

```json
[
  {
    "text": "Simplicity is prerequisite for reliability.",
    "source": "Systems Paper",
    "author": "Edsger Dijkstra",
    "tags": "engineering,reliability"
  }
]
```

## LLM 配置

AI 功能支持配置不同的 LLM 提供商，配置文件为 `config/config.json`：

```json
{
    "llm": {
        "provider": "minimax",
        "api_base_url": "https://api.minimaxi.com/v1/chat/completions",
        "api_key": "your-api-key",
        "model": "MiniMax-M2.5"
    },
    "tags": {
        "prompt": "你是一个专业的标签建议助手..."
    }
}
```

复制模板配置：
```bash
cp config/config.json.template config/config.json
# 然后编辑 config/config.json 填入你的 API Key
```

## 设计原则

- **本地优先** - 所有数据存储在本地 SQLite，不依赖云服务
- **可配置优于硬编码** - 站点解析规则、AI prompt 等均可配置文件管理
- **AI 是增强，而非依赖** - AI 功能可开关，不用 AI 也能正常使用核心功能
- **所有数据可导出** - 纯文本存储，随时可迁移

## 项目结构

```
├── core/           # 核心领域模型
├── storage/        # SQLite 数据层
├── scheduler/      # 复习算法 (SM-2)
├── parser/        # 网页抓取引擎
├── web/           # Web UI 服务 (FastAPI + React)
├── frontend/      # React 前端
├── cli/           # CLI 入口
├── ai/            # LLM 插件层
├── services/      # 业务服务
└── 根目录         # 向后兼容层
```

## 技术栈

- **后端**：Python + FastAPI + SQLite
- **前端**：React + Vite + Tailwind CSS
- **复习算法**：SM-2 (SuperMemo 2)
