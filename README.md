# Readlite

一个轻量的 Readwise 平替（本地优先，CLI + Web UI）。

功能：
- 保存摘录（手动添加、CSV/JSON/JSONL 导入）
- 链接抓取（输入网页链接自动解析为 Markdown 摘录）
- 基于 SM-2 的间隔复习调度
- 每日回顾摘要（Markdown 输出）
- Web UI（本地浏览器使用）
- 摘录批注（选中文字右键高亮/批注）
- 卡片删除（所有主要页面可删）
- 图片缩略图展示（hover 放大预览）
- 收藏功能（Favorite / 取消 Favorite）
- 已读状态管理（可手动切换；进入详情页自动标记为已读）
- 全部摘录支持已读过滤（默认仅未读，可切换为仅已读/全部）

## 快速开始

```bash
python3 readlite.py add --text "First highlight" --source "Deep Work" --author "Cal Newport" --tags productivity,focus
python3 readlite.py list
python3 readlite.py review
python3 readlite.py daily
```

启动 Web UI：

```bash
python3 webui.py --host 127.0.0.1 --port 8787
```

然后访问：`http://127.0.0.1:8787`

## Web UI 使用说明

- 导航页：
  - `/add`：手动添加摘录
  - `/add-link`：链接抓取并解析为 Markdown
- `/favorites`：收藏摘录列表（支持搜索与 tag 过滤）
- `全部摘录` 页支持关键词搜索，并在页面中高亮匹配文本
- `全部摘录` 页支持按关键词与标签联合过滤（`q + tag`）
- `全部摘录` 页支持已读过滤（`read`）：
  - `仅未读`（默认）
  - `仅已读`
  - `全部`
  - 切换 `read` 选项会自动生效（无需再点“搜索”）
  - `read` 选项会自动记忆（刷新后保持上次选择）
- `全部摘录` 页仅显示每条摘录前 100 字预览；完整内容仅在“查看并批注”页展示
- 文本内支持高亮语法：`==需要高亮的内容==`
- `查看并批注` 可对摘录添加：
  - 在正文中选中文字并右键，可直接高亮
  - 选择“写批注”会弹出输入框记录评价
- 进入“查看并批注”页后，会自动将该摘录标记为已读
- `查看并批注` 页支持键盘快捷键（无鼠标流）：
  - `H`：高亮当前选中内容（或当前激活高亮）
  - `M`：给当前选中内容（或当前激活高亮）写批注
  - `Enter`：编辑当前批注
  - `Delete / Backspace`：删除当前批注
  - `Z`：从“查看并批注”页返回“全部摘录”
  - `Cmd/Ctrl + S`：保存批注（弹窗打开时）
  - `Cmd/Ctrl + F`：聚焦页内搜索框
  - `J / K`：在高亮间向下/向上跳转
- 全局快捷键：
  - `A`：快速跳转到“添加链接”页面
- 快捷键映射来自配置文件：`shortcuts.json`
  - 可按 `global` / `detail` 下的动作修改按键
  - 修改后重启 `webui.py` 生效
- 卡片标题可直接点击进入“查看并批注”页
- 卡片支持 `标记已读/未读`、`收藏/取消收藏`、删除（删除摘录会联动删除其批注）
- 图片默认缩略图展示，hover 可放大预览
- 添加链接时，已摘录过的 URL 不允许重复保存（会提示并可跳转到已有卡片）
- 标签支持多值：可用逗号或分号输入，保存时自动去重并标准化展示
- 现有摘录可在“查看并批注”页通过“追加标签”继续补充 tags（自动去重）

## 解析规则（配置化）

- 规则引擎支持配置文件：`parser_rules.json`
- 代码入口仍在：`parser_engine.py`（仅保留通用解析流程与通用动作）
- 各域名规则全部在 `parser_rules.json` 中维护（`parser_engine.py` 不再内置站点规则）
- 当前内置配置：`solidot.org`、`ifanr.com`、`playno1.com`、`blogjava.net`、`news.yahoo.co.jp`、`medium.com`、`cnblogs.com`、`liaoxuefeng.com`
- `economist.com` 需要屏蔽的脚本地址也已放入 `parser_rules.json > blocked_script_sources`
- 代码块会尽量保留语言标记（例如 ` ```java `），并在页面渲染时挂载 `language-xxx` class
- 若代码块未识别到语言，会默认按 `java` 处理

### 如何新增/调整站点规则

在 `parser_rules.json` 的 `rules` 下新增一个规则块，常用字段：

- `domains`：域名列表
- `primary_html_patterns`：正文容器正则（按顺序尝试）
- `drop_patterns`：需要过滤的噪音文本正则
- `drop_exact`：精确匹配过滤词（可选）
- `stop_patterns`：命中后停止继续追加正文（可选）
- `image_drop_keywords`：图片 URL 过滤关键词
- `max_images`：该站点最多保留图片数量
- `request_headers`：站点专用请求头（可选）
- `pre_primary_actions`：优先正文提取动作（可选，例如 `yahoo_preloaded_state`）
- `post_clean_actions`：基础清洗后再执行的动作链（可选）
- `post_parse_actions`：最终输出前动作链（可选）
- `text_replacements`：文本替换规则（可选，正则 `pattern` + `to`）
- `min_blocks` / `min_blocks_error`：最小正文段落数和失败提示（可选）

修改配置后重启 `webui.py` 即可生效，无需改 Python 代码。

### 站点专用抓取参数

- `playno1.com` 已支持站点专用请求头策略（含 `Referer`）。
- 如需复用你的登录态，请在启动前设置环境变量：

```bash
export PLAYNO1_COOKIE='你的完整 Cookie 字符串'
python3 webui.py --host 127.0.0.1 --port 8787
```

注意：
- 不要把 Cookie 写入代码或提交到 Git。
- Cookie 过期后需要重新设置。

## 常见问题

- 为什么我改了规则，但页面内容没变化？
  - 旧摘录不会自动重算；需要删除旧卡片后重新抓取链接。
- 为什么页面仍显示旧样式？
  - 重启服务后再浏览器强制刷新（`Cmd+Shift+R`）。
- 为什么有些站点返回 `HTTP 403`？
  - 这通常是反爬/付费墙限制。系统会重试多组请求头并尝试特定站点策略，但无法保证绕过鉴权。
- 已知 bug：进入 `/add-link` 页面时，URL 输入框偶发出现“看起来已聚焦但无法立即输入”的情况。
  - 临时规避：手动点击一次 URL 输入框后可正常编辑。
- 已知 bug：部分页面（例如 `liaoxuefeng.com`）中“未显式标注语言”的代码块，偶发被误判为 `javascript`，未稳定按默认 `java` 渲染。
  - 临时规避：在原文代码块中显式 language class（如 `language-java`）时可正常高亮。

默认数据库路径：`data/readlite.db`

可通过 `--db` 指定自定义数据库：

```bash
python3 readlite.py --db /path/to/readlite.db list
```

## 导入格式

支持 `.jsonl` / `.json` / `.csv`，字段如下（除 `text` 外都可选）：

- `text`
- `source`
- `author`
- `location`
- `tags`

CSV 示例：

```csv
text,source,author,location,tags
"We are what we repeatedly do.","Nicomachean Ethics","Aristotle","Book II","habit,virtue"
```

JSON 示例：

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
# snipnote
