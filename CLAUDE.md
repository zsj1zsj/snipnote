# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**SnipNote** - A lightweight Readwise alternative (local-first, CLI + Web UI) for managing highlights and spaced repetition reviews.

## Commands

### CLI Commands
```bash
# Add a highlight
python3 readlite.py add --text "..." --source "Book Title" --author "Author Name" --tags tag1,tag2

# Import from file (json/jsonl/csv)
python3 readlite.py import --file path/to/file.jsonl

# List highlights
python3 readlite.py list
python3 readlite.py list --due          # Only due highlights
python3 readlite.py list --limit 50

# Review due highlights (SM-2 algorithm)
python3 readlite.py review
python3 readlite.py review --limit 5
python3 readlite.py review --quality 3  # Non-interactive mode

# Generate daily review digest
python3 readlite.py daily

# Custom database path
python3 readlite.py --db /path/to/readlite.db list
```

### Web UI
```bash
python3 webui.py --host 127.0.0.1 --port 8787
```
Then access `http://127.0.0.1:8787`

## Architecture

### New Modular Structure (v2)

```
├── core/           # 核心领域模型（最稳定）
│   └── __init__.py  # Highlight, Annotation, ReviewSchedule dataclasses
│
├── storage/        # SQLite + repository layer
│   ├── db.py       # connect(), SCHEMA_SQL
│   └── repository.py # HighlightRepository, AnnotationRepository
│
├── scheduler/      # 复习算法（可替换）
│   └── sm2.py      # SM2Scheduler (implements SM-2 algorithm)
│
├── ai/             # LLM 插件层（占位符）
│
├── parser/         # 抓取引擎
│   └── engine.py   # ArticleExtractor, parse_link_to_markdown
│
├── rss/            # RSS 模块（占位符）
│
├── web/            # Web UI
│   └── server.py   # HTTP server
│
├── cli/            # CLI
│   └── main.py     # CLI entry point
│
├── plugins/        # 扩展能力（占位符）
│
└── root            # 向后兼容层
    ├── readlite.py      # 兼容旧 import
    ├── webui.py         # 兼容旧入口
    └── parser_engine.py # 兼容旧 import
```

### Key Components

| File | Purpose |
|------|---------|
| `core/__init__.py` | Domain models: Highlight, Annotation |
| `storage/db.py` | Database connection, schema, migrations |
| `storage/repository.py` | CRUD operations for highlights/annotations |
| `scheduler/sm2.py` | SM-2 spaced repetition algorithm |
| `parser/engine.py` | HTML parsing, article extraction |
| `web/server.py` | HTTP server with Web UI |
| `cli/main.py` | CLI entry point |

### Legacy Files (Backward Compatibility)

The root-level files provide backward compatibility:
- `readlite.py` - Re-exports from new modules, CLI entry point
- `webui.py` - Delegates to web/server.py
- `parser_engine.py` - Re-exports from parser/engine.py

### Parsing Rules
Site-specific rules are configured in `parser_rules.json`:
- `domains` - List of domains the rule applies to
- `primary_html_patterns` - Regex patterns to find main content container
- `drop_patterns` - Regex patterns for noise to filter
- `drop_exact` - Exact match strings to filter
- `stop_patterns` - Patterns that stop further content extraction
- `image_drop_keywords` - Keywords to filter unwanted images
- `max_images` - Maximum images to extract
- `request_headers` - Site-specific HTTP headers
- `post_clean_actions` / `post_parse_actions` - Post-processing action chains

Economist.com has special handling - auto-fallback to archive.is snapshots when paywall is detected.

## Development Notes

- **No external dependencies** - Uses Python standard library only
- Parser rules changes take effect on restart (no code changes needed)
- Old highlights don't auto-recompute when rules change - delete and re-add to reparse
- `cookies.json` follows format: `{ "domain.com": { "cookie_name": "value" } }`
- The Web UI embeds all HTML/CSS/JS inline (no separate frontend files)
- New modules can be imported directly: `from storage import connect`, `from scheduler import SM2Scheduler`
