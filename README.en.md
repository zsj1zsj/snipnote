# SnipNote

A local-first, configurable, AI-enhanced knowledge management system for developers and heavy readers.

## Features

- Save highlights (manual entry, CSV/JSON/JSONL import)
- Link capture (paste a URL to auto-parse content as a Markdown highlight)
- SM-2 spaced repetition scheduling
- Daily review digest (Markdown output)
- **Web UI** (modern React interface, runs locally in your browser)
- Highlight annotations (right-click selected text to add notes)
- Favorites (bookmark / unbookmark highlights)
- Read status tracking
- AI summarization (auto-generate highlight summaries)
- AI tag suggestions (analyze content and recommend tags)
- Tag management page

## Installation

```bash
# Install Python dependencies (using uv)
uv venv .venv
source .venv/bin/activate
uv pip install -r pyproject.toml

# Install frontend dependencies (first time or after frontend updates)
cd frontend && npm install && cd ..
```

## Quick Start

### Start the Web UI

```bash
python3 webui.py
```

Then open: `http://127.0.0.1:8787`

### Rebuild the frontend after changes

```bash
cd frontend && npm run build && cd ..
```

### CLI Commands

```bash
# Add a highlight
python3 readlite.py add --text "First highlight" --source "Deep Work" --author "Cal Newport" --tags productivity,focus

# List highlights
python3 readlite.py list

# Start a review session
python3 readlite.py review

# Generate daily digest
python3 readlite.py daily

# Use a custom database path
python3 readlite.py --db /path/to/readlite.db list
```

## Web UI Pages

| Page | Path | Description |
|------|------|-------------|
| Home | `/` | Stats overview, recently added, quick actions |
| Highlights | `/highlights` | All highlights with search, tag filter, read filter |
| Highlight Detail | `/highlight/:id` | View content, notes, summary, AI tags |
| Review | `/review` | SM-2 spaced repetition session |
| Favorites | `/favorites` | Bookmarked highlights |
| Tags | `/tags` | Tag management |
| Daily Digest | `/daily` | View and generate reading digest |
| Add Highlight | `/add` | Manually add a highlight |
| Add from Link | `/add-link` | Paste a URL to parse and save |

## Parser Rules (Configurable)

- Rule engine reads from `config/parser_rules.json`
- Parser module: `parser/engine.py`
- All per-domain rules are maintained in the config file (no hardcoded site rules in code)
- Built-in configs: `solidot.org`, `ifanr.com`, `playno1.com`, `blogjava.net`, `news.yahoo.co.jp`, `medium.com`, `economist.com`, `cnblogs.com`, `liaoxuefeng.com`
- `economist.com` automatically falls back to `archive.is` snapshots when a paywall is detected

### Adding or Adjusting Site Rules

Add a new rule block under `rules` in `config/parser_rules.json`. Common fields:

- `domains` — list of domains the rule applies to
- `primary_html_patterns` — regex patterns to identify the main content container
- `drop_patterns` — regex patterns for noise to remove
- `image_drop_keywords` — keywords to filter unwanted images by URL
- `max_images` — maximum number of images to keep
- `request_headers` — site-specific HTTP headers

Changes take effect on server restart.

### Sites That Require Login

Create `config/cookies.json`:

```json
{
  "example.com": {
    "cookie_name": "cookie_value"
  }
}
```

## Import Formats

Supports `.jsonl`, `.json`, and `.csv`:

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

## LLM Configuration

AI features support configurable LLM providers via `config/config.json`:

```json
{
    "llm": {
        "provider": "minimax",
        "api_base_url": "https://api.minimaxi.com/v1/chat/completions",
        "api_key": "your-api-key",
        "model": "MiniMax-M2.5"
    },
    "tags": {
        "prompt": "You are a professional tag suggestion assistant..."
    }
}
```

Copy the template to get started:

```bash
cp config/config.json.template config/config.json
# Then edit config/config.json and fill in your API key
```

## Design Principles

- **Local-first** — all data lives in a local SQLite file, no cloud dependency
- **Configurable over hardcoded** — site parser rules, AI prompts, and more are all managed via config files
- **AI as enhancement, not dependency** — AI features are optional; core functionality works without them
- **All data is exportable** — plain-text storage, easy to migrate

## Project Structure

```
├── core/           # Domain models
├── storage/        # SQLite data layer
├── scheduler/      # Review algorithm (SM-2)
├── parser/         # Web scraping engine
├── web/            # Web server (FastAPI + React)
├── frontend/       # React frontend
├── cli/            # CLI entry point
├── ai/             # LLM plugin layer
├── services/       # Business services
└── root            # Backward-compatibility shims
```

## Tech Stack

- **Backend**: Python + FastAPI + SQLite
- **Frontend**: React + Vite + Tailwind CSS
- **Review Algorithm**: SM-2 (SuperMemo 2)
