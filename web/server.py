#!/usr/bin/env python3
import argparse
import datetime as dt
import html
import html as html_std
import json
import os
import re
import sqlite3
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, parse_qsl, urlencode, urljoin, urlparse, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from parser import parse_link_to_markdown
from storage import connect
from scheduler import SM2Scheduler


def _config_dir():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


DEFAULT_DB = Path(_config_dir()) / "data" / "readlite.db"


DEFAULT_SHORTCUTS: dict[str, dict[str, list[str]]] = {
    "global": {
        "go_add_link": ["a"],
    },
    "detail": {
        "highlight": ["h"],
        "note": ["m"],
        "edit_note": ["enter"],
        "delete_annotation": ["delete", "backspace"],
        "next_mark": ["j"],
        "prev_mark": ["k"],
        "save_note": ["meta+s", "ctrl+s"],
        "focus_search": ["meta+f", "ctrl+f"],
        "back_to_highlights": ["z"],
    },
}


def _merge_dict(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in override.items():
        base_value = merged.get(key)
        if isinstance(base_value, dict) and isinstance(value, dict):
            merged[key] = _merge_dict(base_value, value)
        else:
            merged[key] = value
    return merged


def load_shortcuts_config() -> dict[str, dict[str, list[str]]]:
    path = os.path.join(_config_dir(), "shortcuts.json")
    if not os.path.exists(path):
        return DEFAULT_SHORTCUTS
    try:
        with open(path, "r", encoding="utf-8") as f:
            user_cfg = json.load(f)
    except (OSError, json.JSONDecodeError):
        return DEFAULT_SHORTCUTS
    if not isinstance(user_cfg, dict):
        return DEFAULT_SHORTCUTS
    merged = _merge_dict(DEFAULT_SHORTCUTS, user_cfg)
    return merged


SHORTCUTS_CONFIG = load_shortcuts_config()


def shortcut_list(scope: str, action: str) -> list[str]:
    group = SHORTCUTS_CONFIG.get(scope, {})
    if not isinstance(group, dict):
        return []
    raw = group.get(action, [])
    if not isinstance(raw, list):
        return []
    return [str(x).strip().lower() for x in raw if str(x).strip()]


def format_shortcut_spec(spec: str) -> str:
    token_map = {
        "meta": "⌘",
        "ctrl": "Ctrl",
        "alt": "Alt",
        "shift": "Shift",
        "enter": "Enter",
        "delete": "Delete",
        "backspace": "Backspace",
        "escape": "Esc",
        "space": "Space",
    }
    parts = [p for p in (spec or "").split("+") if p]
    shown = []
    for p in parts:
        key = p.lower().strip()
        shown.append(token_map.get(key, key.upper() if len(key) == 1 else key.title()))
    return "+".join(shown)


def shortcut_hint(scope: str, action: str, fallback: str = "-") -> str:
    specs = shortcut_list(scope, action)
    if not specs:
        return fallback
    return " / ".join(format_shortcut_spec(s) for s in specs)


def today_iso() -> str:
    return dt.date.today().isoformat()


def normalize_article_url(url: str) -> str:
    try:
        parts = urlsplit((url or "").strip())
    except ValueError:
        return (url or "").strip()
    scheme = (parts.scheme or "https").lower()
    netloc = (parts.netloc or "").lower()
    path = parts.path or "/"
    if path != "/":
        path = path.rstrip("/")
    query_items = parse_qsl(parts.query, keep_blank_values=True)
    filtered = []
    for k, v in query_items:
        lk = (k or "").lower()
        if lk.startswith("utm_") or lk in {"fbclid", "gclid", "igshid", "mc_cid", "mc_eid"}:
            continue
        filtered.append((k, v))
    query = urlencode(filtered)
    return urlunsplit((scheme, netloc, path, query, ""))


class ArticleExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_title = False
        self.current_tag = ""
        self.skip_depth = 0
        self.ignore_depth = 0
        self.ignore_stack: list[bool] = []
        self.skip_stack: list[bool] = []
        self.noise_stack: list[bool] = []
        self.title_chunks: list[str] = []
        self.current_chunks: list[str] = []
        self.blocks: list[tuple[str, str]] = []

    def _is_noise_container(self, tag: str, attrs) -> bool:
        if tag in {"nav", "footer", "aside"}:
            return True
        attr_map = {k.lower(): (v or "").lower() for k, v in attrs}
        text = " ".join([attr_map.get("id", ""), attr_map.get("class", ""), attr_map.get("role", "")])
        tokens = set(re.findall(r"[a-z0-9]+", text))
        noise_keywords = {
            "menu",
            "nav",
            "footer",
            "sidebar",
            "comment",
            "comments",
            "related",
            "share",
            "social",
            "cookie",
            "newsletter",
            "promo",
            "advert",
            "ads",
        }
        return bool(tokens & noise_keywords)

    def handle_starttag(self, tag: str, attrs):
        tag = tag.lower()
        is_skip = tag in {"script", "style", "noscript"}
        is_noise = self._is_noise_container(tag, attrs)
        ignored = is_skip or is_noise or self.skip_depth > 0 or self.ignore_depth > 0
        self.ignore_stack.append(ignored)
        self.skip_stack.append(is_skip)
        self.noise_stack.append(is_noise)
        if is_skip:
            self.skip_depth += 1
        if is_noise:
            self.ignore_depth += 1
        if ignored:
            return
        if tag == "title":
            self.in_title = True
        if tag in {"p", "li", "blockquote", "h1", "h2", "h3"}:
            self.current_tag = tag
            self.current_chunks = []

    def handle_endtag(self, tag: str):
        tag = tag.lower()
        ignored = self.ignore_stack.pop() if self.ignore_stack else False
        was_skip = self.skip_stack.pop() if self.skip_stack else False
        was_noise = self.noise_stack.pop() if self.noise_stack else False
        if was_skip and self.skip_depth > 0:
            self.skip_depth -= 1
        if was_noise and self.ignore_depth > 0:
            self.ignore_depth -= 1
        if ignored:
            return
        if tag == "title":
            self.in_title = False
        if tag == self.current_tag and self.current_chunks:
            text = " ".join(self.current_chunks).strip()
            if text:
                self.blocks.append((tag, re.sub(r"\s+", " ", text)))
            self.current_tag = ""
            self.current_chunks = []

    def handle_data(self, data: str):
        if self.skip_depth > 0:
            return
        text = data.strip()
        if not text:
            return
        if self.in_title:
            self.title_chunks.append(text)
        if self.current_tag:
            self.current_chunks.append(text)

    @property
    def title(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self.title_chunks)).strip()


def fetch_link_as_markdown(url: str, timeout: int = 10) -> tuple[str, str]:
    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        },
    )
    with urlopen(req, timeout=timeout) as resp:
        content_type = (resp.headers.get("Content-Type") or "").lower()
        if "text/html" not in content_type and content_type:
            raise ValueError(f"不支持的内容类型: {content_type}")
        raw = resp.read()
    text = raw.decode("utf-8", errors="replace")
    parser = ArticleExtractor()
    parser.feed(text)
    parser.close()

    parsed = urlparse(url)
    host = parsed.netloc
    title = parser.title or host or "Untitled Page"
    blocks = parser.blocks[:180]
    fallback_blocks = fallback_extract_blocks(text)[:180]
    jsonld_blocks = extract_jsonld_blocks(text)[:180]
    image_urls = extract_image_urls(text, url)[:4]

    # Pick the highest-quality candidate to avoid shell-only content pages.
    meta_blocks = extract_meta_description(text)
    candidates = [blocks, fallback_blocks, jsonld_blocks, meta_blocks]
    blocks = max(candidates, key=blocks_quality)
    if not blocks:
        raise ValueError("页面中没有可提取的正文段落")

    lines = [f"# {title}", "", f"来源: [{host or url}]({url})", ""]
    for idx, img in enumerate(image_urls, start=1):
        lines.append(f"![图片 {idx}]({img})")
        lines.append("")
    total_chars = 0
    max_chars = 45000
    for tag, block in blocks:
        if not block:
            continue
        if total_chars >= max_chars:
            lines.append("")
            lines.append("_内容过长，已截断。_")
            break
        chunk = block[:1400]
        total_chars += len(chunk)
        if tag == "h1":
            lines.append(f"## {chunk}")
        elif tag == "h2":
            lines.append(f"### {chunk}")
        elif tag == "h3":
            lines.append(f"#### {chunk}")
        elif tag == "li":
            lines.append(f"- {chunk}")
        else:
            lines.append(chunk)
        lines.append("")
    markdown = "\n".join(lines).strip()
    return title, markdown


def blocks_quality(blocks: list[tuple[str, str]]) -> tuple[int, int, int]:
    if not blocks:
        return (0, 0, 0)
    body_like = 0
    total = 0
    long_count = 0
    for tag, text in blocks:
        ln = len(text or "")
        total += ln
        if tag in {"p", "li", "blockquote"}:
            body_like += 1
        if ln >= 120:
            long_count += 1
    return (body_like, long_count, total)


def extract_jsonld_blocks(raw_html: str) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    scripts = re.findall(
        r'(?is)<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        raw_html,
    )
    for script_content in scripts:
        content = html_std.unescape(script_content).strip()
        if not content:
            continue
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            continue
        for item in iter_article_candidates(payload):
            headline = (
                str(item.get("headline") or item.get("name") or "").strip()
                if isinstance(item, dict)
                else ""
            )
            body = (
                str(item.get("articleBody") or item.get("text") or item.get("description") or "").strip()
                if isinstance(item, dict)
                else ""
            )
            if headline:
                blocks.append(("h2", re.sub(r"\s+", " ", headline)[:300]))
            blocks.extend(body_to_blocks(body))
    return blocks


def extract_meta_description(raw_html: str) -> list[tuple[str, str]]:
    patterns = [
        r'(?is)<meta[^>]*property=["\']og:description["\'][^>]*content=["\'](.*?)["\'][^>]*>',
        r'(?is)<meta[^>]*name=["\']description["\'][^>]*content=["\'](.*?)["\'][^>]*>',
    ]
    for pat in patterns:
        m = re.search(pat, raw_html)
        if m:
            desc = html_std.unescape(m.group(1)).strip()
            desc = re.sub(r"\s+", " ", desc)
            if len(desc) >= 40:
                return [("p", desc[:1400])]
    return []


def normalize_image_url(candidate: str, page_url: str) -> str:
    c = (candidate or "").strip()
    if not c or c.startswith("data:"):
        return ""
    c = c.replace("&amp;", "&")
    absolute = urljoin(page_url, c)
    if absolute.startswith("http://") or absolute.startswith("https://"):
        return absolute
    return ""


def image_quality_score(url: str) -> int:
    lower = url.lower()
    score = 0
    if "c=original" in lower:
        score += 100
    if "q=w_" in lower:
        score += 20
    if "c_fill" in lower:
        score -= 5
    try:
        query = dict(parse_qsl(urlsplit(url).query, keep_blank_values=True))
        width_raw = query.get("w") or ""
        if width_raw.isdigit():
            score += min(int(width_raw), 4000) // 100
    except ValueError:
        pass
    return score


def image_dedupe_key(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme.lower()}://{parts.netloc.lower()}{parts.path}"


def extract_image_urls(raw_html: str, page_url: str) -> list[str]:
    chosen: dict[str, tuple[str, int]] = {}

    def add(url: str):
        normalized = normalize_image_url(url, page_url)
        if not normalized:
            return
        key = image_dedupe_key(normalized)
        score = image_quality_score(normalized)
        existing = chosen.get(key)
        if existing is None or score > existing[1]:
            chosen[key] = (normalized, score)

    # 1) Meta images.
    meta_patterns = [
        r'(?is)<meta[^>]*property=["\']og:image(?::secure_url)?["\'][^>]*content=["\'](.*?)["\'][^>]*>',
        r'(?is)<meta[^>]*name=["\']twitter:image(?::src)?["\'][^>]*content=["\'](.*?)["\'][^>]*>',
    ]
    for pat in meta_patterns:
        for m in re.finditer(pat, raw_html):
            add(m.group(1))

    # 2) JSON-LD image fields.
    scripts = re.findall(
        r'(?is)<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        raw_html,
    )
    for script_content in scripts:
        content = html_std.unescape(script_content).strip()
        if not content:
            continue
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            continue
        for item in iter_article_candidates(payload):
            image_value = item.get("image") if isinstance(item, dict) else None
            if isinstance(image_value, str):
                add(image_value)
            elif isinstance(image_value, list):
                for it in image_value:
                    if isinstance(it, str):
                        add(it)
                    elif isinstance(it, dict):
                        add(str(it.get("url") or it.get("contentUrl") or ""))
            elif isinstance(image_value, dict):
                add(str(image_value.get("url") or image_value.get("contentUrl") or ""))

    # 3) Img tags from article/main/body area.
    area_match = re.search(r"(?is)<(article|main)[^>]*>(.*?)</\1>", raw_html)
    area = area_match.group(2) if area_match else raw_html
    for m in re.finditer(r"(?is)<img[^>]+>", area):
        tag = m.group(0)
        src_match = re.search(r'(?i)\b(?:src|data-src|data-original|data-lazy-src)=["\'](.*?)["\']', tag)
        if src_match:
            add(src_match.group(1))

    # Return by quality desc, then stable URL ordering.
    ordered = sorted(chosen.values(), key=lambda x: (-x[1], x[0]))
    return [u for u, _ in ordered]


def iter_article_candidates(payload):
    stack = [payload]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            types = node.get("@type")
            if isinstance(types, str):
                type_list = [types]
            elif isinstance(types, list):
                type_list = [str(t) for t in types]
            else:
                type_list = []
            lowered = {t.lower() for t in type_list}
            if {"article", "newsarticle", "blogposting"} & lowered:
                yield node
            if "@graph" in node and isinstance(node["@graph"], list):
                stack.extend(node["@graph"])
            for v in node.values():
                if isinstance(v, (dict, list)):
                    stack.append(v)
        elif isinstance(node, list):
            stack.extend(node)


def body_to_blocks(body: str) -> list[tuple[str, str]]:
    if not body:
        return []
    text = re.sub(r"(?is)<[^>]+>", " ", body)
    text = html_std.unescape(text)
    text = text.replace("\\n", "\n")
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.splitlines()]
    cleaned = [ln for ln in lines if len(ln) >= 45]
    if cleaned:
        return [("p", ln[:1400]) for ln in cleaned]

    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) < 120:
        return []
    # Fallback split by sentence punctuation.
    parts = re.split(r"(?<=[.!?。！？])\s+", compact)
    merged: list[str] = []
    current = ""
    for part in parts:
        if not part:
            continue
        if len(current) + len(part) < 360:
            current = f"{current} {part}".strip()
        else:
            if current:
                merged.append(current)
            current = part
    if current:
        merged.append(current)
    return [("p", p[:1400]) for p in merged if len(p) >= 60]


def fallback_extract_blocks(raw_html: str) -> list[tuple[str, str]]:
    content = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", raw_html)
    main_match = re.search(r"(?is)<(article|main)[^>]*>(.*?)</\1>", content)
    if main_match:
        content = main_match.group(2)
    else:
        body_match = re.search(r"(?is)<body[^>]*>(.*?)</body>", content)
        if body_match:
            content = body_match.group(1)
    content = re.sub(r"(?i)</(p|li|h1|h2|h3|h4|h5|h6|blockquote|div|section|article|br)>", "\n", content)
    content = re.sub(r"(?is)<[^>]+>", " ", content)
    content = html_std.unescape(content)
    lines = []
    for part in content.splitlines():
        cleaned = re.sub(r"\s+", " ", part).strip()
        if len(cleaned) < 35:
            continue
        if re.search(r"(cookie|privacy|subscribe|newsletter|advertis|all rights reserved)", cleaned, re.I):
            continue
        lines.append(("p", cleaned[:1400]))
    return lines


def inject_highlight_markers(text: str, keyword: str) -> str:
    keyword = keyword.strip()
    if not keyword:
        return text
    try:
        pattern = re.compile(re.escape(keyword), flags=re.IGNORECASE)
    except re.error:
        return text
    return pattern.sub(lambda m: f"=={m.group(0)}==", text)


def inject_selected_highlights(text: str, phrases: list[str]) -> str:
    result = text or ""
    cleaned = []
    seen = set()
    for phrase in phrases:
        p = re.sub(r"\s+", " ", (phrase or "").strip())
        if len(p) < 2:
            continue
        key = p.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(p)
    cleaned.sort(key=len, reverse=True)
    for phrase in cleaned:
        pattern = re.compile(re.escape(phrase), flags=re.IGNORECASE)
        result = pattern.sub(lambda m: f"=={m.group(0)}==", result)
    return result


def render_inline(text: str) -> str:
    placeholders: list[str] = []
    token_prefix = "__MDTOKEN_"
    token_suffix = "__"

    def stash(value: str) -> str:
        token = f"{token_prefix}{len(placeholders)}{token_suffix}"
        placeholders.append(value)
        return token

    def link_repl(match: re.Match) -> str:
        label = html.escape(match.group(1), quote=False)
        url = html.escape(match.group(2), quote=True)
        return stash(f"<a href=\"{url}\" target=\"_blank\" rel=\"noopener noreferrer\">{label}</a>")

    text = re.sub(r"\[([^\]]+)\]\((https?://[^\s)]+)\)", link_repl, text)
    escaped = html.escape(text, quote=False)
    escaped = re.sub(r"==([^=\n]+)==", r"<mark>\1</mark>", escaped)
    escaped = re.sub(r"\*\*([^*\n]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*([^*\n]+)\*", r"<em>\1</em>", escaped)

    for idx, value in enumerate(placeholders):
        escaped = escaped.replace(f"{token_prefix}{idx}{token_suffix}", value)
    return escaped


def render_markdown(text: str, keyword: str = "", selected_quotes: list[str] | None = None) -> str:
    md = text or ""
    if selected_quotes:
        md = inject_selected_highlights(md, selected_quotes)
    md = inject_highlight_markers(md, keyword)
    lines = md.splitlines()
    out: list[str] = []
    in_list = False
    in_code = False
    code_lines: list[str] = []
    code_lang = ""
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        fence_match = re.match(r"^```([a-zA-Z0-9_+#-]*)\s*$", line.strip())
        if fence_match:
            if in_list:
                out.append("</ul>")
                in_list = False
            if not in_code:
                in_code = True
                code_lines = []
                code_lang = (fence_match.group(1) or "").strip().lower() or "java"
            else:
                escaped_code = html.escape("\n".join(code_lines), quote=False)
                cls = f' class="language-{html.escape(code_lang, quote=True)}"' if code_lang else ""
                data_lang = f' data-lang="{html.escape(code_lang, quote=True)}"' if code_lang else ""
                out.append(f"<pre{data_lang}><code{cls}>{escaped_code}</code></pre>")
                in_code = False
                code_lines = []
                code_lang = ""
            i += 1
            continue
        if in_code:
            code_lines.append(line)
            i += 1
            continue
        if not line:
            if in_list:
                out.append("</ul>")
                in_list = False
            i += 1
            continue
        image_match = re.match(r"^!\[([^\]]*)\]\((https?://[^\s)]+)\)$", line)
        if image_match:
            if in_list:
                out.append("</ul>")
                in_list = False

            imgs: list[tuple[str, str]] = []
            j = i
            while j < len(lines):
                probe = lines[j].rstrip()
                if not probe:
                    j += 1
                    continue
                m = re.match(r"^!\[([^\]]*)\]\((https?://[^\s)]+)\)$", probe)
                if not m:
                    break
                alt = html.escape(m.group(1), quote=False) or "image"
                src = html.escape(m.group(2), quote=True)
                imgs.append((alt, src))
                j += 1

            if imgs:
                html_imgs = "".join(
                    f"<span class=\"img-wrap\"><img class=\"md-thumb\" src=\"{src}\" alt=\"{alt}\" loading=\"lazy\" /></span>"
                    for alt, src in imgs
                )
                out.append(f"<div class='img-row'>{html_imgs}</div>")
            i = j
            continue
        heading_match = re.match(r"^(#{1,6})\s+(.*)$", line)
        if heading_match:
            if in_list:
                out.append("</ul>")
                in_list = False
            level = min(6, len(heading_match.group(1)))
            content = render_inline(heading_match.group(2))
            out.append(f"<h{level}>{content}</h{level}>")
            i += 1
            continue
        if line.startswith("- "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{render_inline(line[2:])}</li>")
            i += 1
            continue
        if in_list:
            out.append("</ul>")
            in_list = False
        out.append(f"<p>{render_inline(line)}</p>")
        i += 1
    if in_list:
        out.append("</ul>")
    if in_code:
        escaped_code = html.escape("\n".join(code_lines), quote=False)
        cls = f' class="language-{html.escape(code_lang, quote=True)}"' if code_lang else ""
        data_lang = f' data-lang="{html.escape(code_lang, quote=True)}"' if code_lang else ""
        out.append(f"<pre{data_lang}><code{cls}>{escaped_code}</code></pre>")
    return "".join(out) if out else "<p></p>"


def page_layout(title: str, body: str) -> str:
    add_link_hint = shortcut_hint("global", "go_add_link", "A")
    global_shortcuts_json = json.dumps(SHORTCUTS_CONFIG.get("global", {}), ensure_ascii=False)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(title)}</title>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.10.0/styles/github-dark.min.css" />
  <style>
    :root {{
      --bg: #f5f4ee;
      --paper: #ffffff;
      --ink: #18231f;
      --muted: #65736d;
      --accent: #0f766e;
      --line: #dfe4e2;
      --warn: #a16207;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background:
        radial-gradient(circle at 10% 20%, #e8efe9 0%, transparent 40%),
        radial-gradient(circle at 90% 0%, #e8ecef 0%, transparent 35%),
        var(--bg);
      color: var(--ink);
      font-family: "Avenir Next", "PingFang SC", "Noto Sans SC", sans-serif;
      line-height: 1.45;
    }}
    .wrap {{ max-width: 980px; margin: 0 auto; padding: 20px 16px 40px; }}
    .nav {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-bottom: 14px;
    }}
    .nav a {{
      color: var(--accent);
      text-decoration: none;
      border: 1px solid var(--line);
      background: var(--paper);
      padding: 7px 10px;
      border-radius: 10px;
      font-weight: 600;
    }}
    .card {{
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 14px;
      margin-bottom: 12px;
      box-shadow: 0 2px 14px rgba(17, 24, 39, 0.04);
    }}
    h1 {{ margin: 6px 0 12px; font-size: 1.6rem; }}
    h2 {{ margin: 0 0 8px; font-size: 1.1rem; }}
    p {{ margin: 0.2rem 0; }}
    .meta {{ color: var(--muted); font-size: 0.95rem; }}
    .md p {{ margin: 0.35rem 0; }}
    .md ul {{ margin: 0.3rem 0 0.3rem 1.1rem; padding: 0; }}
    .md h1, .md h2, .md h3 {{ margin: 0.2rem 0 0.55rem; font-size: 1.05rem; }}
    .md code {{
      background: #eef3f1;
      border: 1px solid #d9e4df;
      padding: 1px 4px;
      border-radius: 5px;
    }}
    .md pre {{
      position: relative;
      margin: 8px 0;
      padding: 10px 12px;
      background: #0f172a;
      color: #e5e7eb;
      border-radius: 10px;
      overflow-x: auto;
      border: 1px solid #1f2937;
    }}
    .md pre[data-lang]::before {{
      content: attr(data-lang);
      position: absolute;
      top: 6px;
      right: 8px;
      font-size: 11px;
      line-height: 1;
      color: #94a3b8;
      text-transform: lowercase;
    }}
    .md pre code {{
      background: transparent;
      border: 0;
      padding: 0;
      color: inherit;
      border-radius: 0;
      white-space: pre;
      display: block;
      line-height: 1.5;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
    }}
    .md pre code.hljs {{
      background: transparent;
      padding: 0;
    }}
    .md mark {{
      background: #fff3a2;
      color: #111827;
      padding: 0 3px;
      border-radius: 3px;
    }}
    .md mark.active-mark {{
      background: #f59e0b;
      color: #111827;
      box-shadow: 0 0 0 2px rgba(245, 158, 11, 0.3);
    }}
    code {{
      background: #eef3f1;
      border: 1px solid #d9e4df;
      padding: 1px 4px;
      border-radius: 5px;
    }}
    .md .img-wrap {{
      margin: 8px 0;
      display: inline-block;
      position: relative;
      overflow: hidden;
      width: 220px;
      aspect-ratio: 16 / 10;
      border-radius: 10px;
      border: 1px solid #dfe4e2;
      background: #f2f4f3;
    }}
    .md .img-wrap:hover {{
      overflow: visible;
      z-index: 40;
    }}
    .md .img-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: flex-start;
      margin: 8px 0;
      width: 100%;
    }}
    .md .img-row .img-wrap {{
      margin: 0;
    }}
    .md img.md-thumb {{
      width: 100% !important;
      height: 100%;
      object-fit: cover;
      display: block;
      box-shadow: 0 2px 10px rgba(17, 24, 39, 0.08);
      transition: transform 0.18s ease, box-shadow 0.18s ease;
      transform-origin: center center;
      cursor: zoom-in;
      background: #f2f4f3;
    }}
    .md img.md-thumb:hover {{
      object-fit: contain;
      transform: scale(2.2);
      box-shadow: 0 10px 24px rgba(0, 0, 0, 0.22);
      z-index: 30;
      position: relative;
      background: #111827;
    }}
    @media (max-width: 640px) {{
      .md .img-wrap {{
        width: 160px;
      }}
      .md img.md-thumb {{
        width: 100% !important;
        max-width: none;
      }}
    }}
    .grid {{
      display: grid;
      gap: 10px;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    }}
    input, textarea {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 9px;
      padding: 9px 10px;
      font: inherit;
      background: #fff;
    }}
    textarea {{ min-height: 110px; resize: vertical; }}
    button {{
      border: 0;
      border-radius: 10px;
      padding: 9px 12px;
      background: var(--accent);
      color: #fff;
      font-weight: 700;
      cursor: pointer;
    }}
    .scorebar {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 10px;
    }}
    .scorebar button {{ min-width: 52px; }}
    .tag {{
      display: inline-block;
      font-size: 0.82rem;
      color: var(--warn);
      background: #fff8db;
      border: 1px solid #f1e4a6;
      border-radius: 999px;
      padding: 2px 8px;
      margin-left: 6px;
    }}
    .tag-read {{
      display: inline-block;
      font-size: 0.82rem;
      color: #0b6bcb;
      background: #eaf4ff;
      border: 1px solid #b9d9ff;
      border-radius: 999px;
      padding: 2px 8px;
      margin-left: 6px;
    }}
    .inline-form {{
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 8px;
      margin: 8px 0 14px;
    }}
    .ctx-menu {{
      position: fixed;
      display: none;
      z-index: 9999;
      background: #0f172a;
      color: #fff;
      border-radius: 10px;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.25);
      overflow: hidden;
      min-width: 150px;
    }}
    .ctx-menu button {{
      width: 100%;
      border: 0;
      border-radius: 0;
      background: transparent;
      color: #fff;
      text-align: left;
      padding: 10px 12px;
      cursor: pointer;
    }}
    .ctx-menu button:hover {{ background: rgba(255, 255, 255, 0.12); }}
    .modal {{
      position: fixed;
      inset: 0;
      display: none;
      align-items: center;
      justify-content: center;
      z-index: 10000;
      background: rgba(0, 0, 0, 0.35);
      padding: 14px;
    }}
    .modal-card {{
      width: 100%;
      max-width: 560px;
      background: #fff;
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 14px;
    }}
    .actions {{
      display: flex;
      gap: 8px;
      justify-content: flex-end;
      margin-top: 10px;
    }}
    .actions .secondary {{
      background: #d1d5db;
      color: #111827;
    }}
    .row-actions {{
      display: flex;
      gap: 8px;
      align-items: center;
      margin-top: 8px;
    }}
    .danger {{
      background: #b91c1c;
    }}
    .danger:hover {{
      background: #991b1b;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="nav">
      <a href="/">首页</a>
      <a href="/add">添加摘录</a>
      <a href="/add-link" title="快捷键 {html.escape(add_link_hint, quote=True)}">添加链接</a>
      <a href="/highlights">全部摘录</a>
      <a href="/favorites">Favorites</a>
      <a href="/tags">标签管理</a>
    </div>
    {body}
  </div>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.10.0/highlight.min.js"></script>
  <script>
    (function () {{
      var globalShortcuts = {global_shortcuts_json};
      var HIGHLIGHTS_STATE_KEY = 'highlights_list_state_v1';
      var HIGHLIGHTS_RESTORE_KEY = 'highlights_list_restore_v1';
      if (window.hljs) {{
        document.querySelectorAll('pre code').forEach(function (el) {{
          window.hljs.highlightElement(el);
        }});
      }}

      function isTypingTarget(el) {{
        if (!el) return false;
        var tag = (el.tagName || '').toLowerCase();
        return tag === 'input' || tag === 'textarea' || el.isContentEditable;
      }}

      function normalizeKeyName(key) {{
        var k = (key || '').toLowerCase();
        if (k === ' ') return 'space';
        if (k === 'esc') return 'escape';
        if (k === 'arrowup') return 'up';
        if (k === 'arrowdown') return 'down';
        if (k === 'arrowleft') return 'left';
        if (k === 'arrowright') return 'right';
        return k;
      }}

      function normalizeShortcutSpec(spec) {{
        var tokens = String(spec || '').toLowerCase().split('+');
        var mods = [];
        var key = '';
        for (var i = 0; i < tokens.length; i++) {{
          var t = normalizeKeyName(tokens[i].trim());
          if (!t) continue;
          if (t === 'meta' || t === 'ctrl' || t === 'alt' || t === 'shift') {{
            mods.push(t);
          }} else {{
            key = t;
          }}
        }}
        mods.sort();
        if (!key) return mods.join('+');
        return mods.concat([key]).join('+');
      }}

      function eventSpec(e) {{
        var mods = [];
        if (e.metaKey) mods.push('meta');
        if (e.ctrlKey) mods.push('ctrl');
        if (e.altKey) mods.push('alt');
        if (e.shiftKey) mods.push('shift');
        mods.sort();
        mods.push(normalizeKeyName(e.key || ''));
        return mods.join('+');
      }}

      function matchShortcut(e, specs) {{
        if (!Array.isArray(specs)) return false;
        var hit = eventSpec(e);
        for (var i = 0; i < specs.length; i++) {{
          if (hit === normalizeShortcutSpec(specs[i])) return true;
        }}
        return false;
      }}

      document.addEventListener('keydown', function (e) {{
        if (isTypingTarget(e.target)) return;
        if (matchShortcut(e, globalShortcuts.go_add_link || [])) {{
          e.preventDefault();
          window.location.href = '/add-link';
        }}
      }});

      if (window.location.pathname === '/highlights') {{
        try {{
          var restore = sessionStorage.getItem(HIGHLIGHTS_RESTORE_KEY);
          if (restore === '1') {{
            sessionStorage.removeItem(HIGHLIGHTS_RESTORE_KEY);
            var rawState = sessionStorage.getItem(HIGHLIGHTS_STATE_KEY);
            if (rawState) {{
              var state = JSON.parse(rawState);
              var currentUrl = window.location.pathname + window.location.search;
              if (state && state.url === currentUrl) {{
                var targetId = null;
                var candidates = [state.nextId, state.prevId, state.clickedId, state.anchorId];
                for (var ci = 0; ci < candidates.length; ci++) {{
                  var cid = candidates[ci];
                  if (!cid) continue;
                  var probe = document.querySelector('.card[data-highlight-id="' + cid + '"]');
                  if (probe) {{
                    targetId = cid;
                    break;
                  }}
                }}
                if (targetId) {{
                  var targetEl = document.querySelector('.card[data-highlight-id="' + targetId + '"]');
                  var desiredTop = parseInt(state.clickedTop, 10);
                  if (isNaN(desiredTop)) desiredTop = 100;
                  if (targetEl) {{
                    var delta = targetEl.getBoundingClientRect().top - desiredTop;
                    window.scrollBy(0, delta);
                  }}
                }} else {{
                  var y = parseInt(state.y, 10);
                  if (!isNaN(y)) {{
                    window.scrollTo(0, y);
                  }}
                }}
              }}
            }}
          }}
        }} catch (e) {{}}

        document.addEventListener('click', function (e) {{
          if (e.defaultPrevented) return;
          if (e.button !== 0) return;
          if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
          var target = e.target;
          var link = target && target.closest ? target.closest('a[href]') : null;
          if (!link) return;
          var href = link.getAttribute('href') || '';
          if (!href.startsWith('/highlight?id=')) return;
          try {{
            var card = link.closest('.card[data-highlight-id]');
            var clickedId = card ? card.getAttribute('data-highlight-id') : '';
            var clickedTop = card ? Math.round(card.getBoundingClientRect().top) : 100;
            var prevId = '';
            var nextId = '';
            if (card) {{
              var prev = card.previousElementSibling;
              var next = card.nextElementSibling;
              while (prev && !prev.matches('.card[data-highlight-id]')) prev = prev.previousElementSibling;
              while (next && !next.matches('.card[data-highlight-id]')) next = next.nextElementSibling;
              prevId = prev ? prev.getAttribute('data-highlight-id') : '';
              nextId = next ? next.getAttribute('data-highlight-id') : '';
            }}
            var anchorId = '';
            var cards = document.querySelectorAll('.card[data-highlight-id]');
            for (var i = 0; i < cards.length; i++) {{
              var r = cards[i].getBoundingClientRect();
              if (r.bottom > 0 && r.top < window.innerHeight) {{
                anchorId = cards[i].getAttribute('data-highlight-id') || '';
                break;
              }}
            }}
            var state = {{
              url: window.location.pathname + window.location.search,
              y: String(window.scrollY || window.pageYOffset || 0),
              clickedId: clickedId,
              prevId: prevId,
              nextId: nextId,
              anchorId: anchorId,
              clickedTop: String(clickedTop)
            }};
            sessionStorage.setItem(HIGHLIGHTS_STATE_KEY, JSON.stringify(state));
          }} catch (err) {{}}
        }});

        document.addEventListener('submit', function (e) {{
          var form = e.target;
          if (!form || !form.matches || !form.matches("form[action='/highlight/delete']")) return;
          try {{
            var card = form.closest('.card[data-highlight-id]');
            var clickedId = card ? card.getAttribute('data-highlight-id') : '';
            var clickedTop = card ? Math.round(card.getBoundingClientRect().top) : 100;
            var prevId = '';
            var nextId = '';
            if (card) {{
              var prev = card.previousElementSibling;
              var next = card.nextElementSibling;
              while (prev && !prev.matches('.card[data-highlight-id]')) prev = prev.previousElementSibling;
              while (next && !next.matches('.card[data-highlight-id]')) next = next.nextElementSibling;
              prevId = prev ? prev.getAttribute('data-highlight-id') : '';
              nextId = next ? next.getAttribute('data-highlight-id') : '';
            }}
            var anchorId = '';
            var cards = document.querySelectorAll('.card[data-highlight-id]');
            for (var i = 0; i < cards.length; i++) {{
              var r = cards[i].getBoundingClientRect();
              if (r.bottom > 0 && r.top < window.innerHeight) {{
                anchorId = cards[i].getAttribute('data-highlight-id') || '';
                break;
              }}
            }}
            var state = {{
              url: window.location.pathname + window.location.search,
              y: String(window.scrollY || window.pageYOffset || 0),
              clickedId: clickedId,
              prevId: prevId,
              nextId: nextId,
              anchorId: anchorId,
              clickedTop: String(clickedTop)
            }};
            sessionStorage.setItem(HIGHLIGHTS_STATE_KEY, JSON.stringify(state));
            sessionStorage.setItem(HIGHLIGHTS_RESTORE_KEY, '1');
          }} catch (err) {{}}
        }});
      }}

      var containers = document.querySelectorAll('.md');
      containers.forEach(function (container) {{
        var nodes = Array.prototype.slice.call(container.children || []);
        var i = 0;
        while (i < nodes.length) {{
          var node = nodes[i];
          if (!node || node.tagName !== 'P') {{
            i += 1;
            continue;
          }}
          var wrap = node.querySelector(':scope > .img-wrap');
          if (!wrap || node.children.length !== 1 || (node.textContent || '').trim() !== '') {{
            i += 1;
            continue;
          }}
          var row = document.createElement('div');
          row.className = 'img-row';
          var j = i;
          while (j < nodes.length) {{
            var p = nodes[j];
            if (!p || p.tagName !== 'P') break;
            var w = p.querySelector(':scope > .img-wrap');
            if (!w || p.children.length !== 1 || (p.textContent || '').trim() !== '') break;
            row.appendChild(w);
            j += 1;
          }}
          container.insertBefore(row, node);
          for (var k = i; k < j; k++) {{
            if (nodes[k] && nodes[k].parentNode === container) {{
              container.removeChild(nodes[k]);
            }}
          }}
          nodes = Array.prototype.slice.call(container.children || []);
          i += 1;
        }}
      }});
    }})();
  </script>
</body>
</html>"""


class App:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def conn(self) -> sqlite3.Connection:
        return connect(Path(self.db_path))


def fetch_counts(conn: sqlite3.Connection) -> dict:
    due = conn.execute(
        "SELECT COUNT(*) as c FROM highlights WHERE date(next_review) <= date(?)",
        (today_iso(),),
    ).fetchone()["c"]
    total = conn.execute("SELECT COUNT(*) as c FROM highlights").fetchone()["c"]
    return {"due": due, "total": total}


def fetch_all_tags(conn: sqlite3.Connection) -> list[tuple[str, int]]:
    """Fetch all unique tags with their usage count."""
    rows = conn.execute("SELECT id, tags FROM highlights WHERE tags != ''").fetchall()
    tag_counts: dict[str, int] = {}
    for row in rows:
        tags_str = row["tags"] or ""
        # Split by comma or semicolon
        tags = re.split(r"[,，;；]+", tags_str)
        for tag in tags:
            tag = tag.strip()
            if tag:
                tag_lower = tag.lower()
                if tag_lower in tag_counts:
                    tag_counts[tag_lower] += 1
                else:
                    tag_counts[tag_lower] = 1
    # Return sorted by count descending, then alphabetically
    result = []
    seen: set[str] = set()
    for row in rows:
        tags_str = row["tags"] or ""
        tags = re.split(r"[,，;；]+", tags_str)
        for tag in tags:
            tag = tag.strip()
            if tag and tag.lower() not in seen:
                seen.add(tag.lower())
                result.append((tag, tag_counts.get(tag.lower(), 0)))
    result.sort(key=lambda x: (-x[1], x[0].lower()))
    return result


def fetch_due(
    conn: sqlite3.Connection,
    limit: int = 20,
    sort_order: str = "desc",
    sort_by_time: bool = False,
) -> list[sqlite3.Row]:
    direction = "ASC" if (sort_order or "").lower() == "asc" else "DESC"
    if sort_by_time:
        order_clause = f"datetime(created_at) {direction}, id {direction}"
    else:
        order_clause = "next_review, id"
    return conn.execute(
        f"""
        SELECT id, text, source, author, tags, favorite, is_read, repetitions, next_review, interval_days, efactor, created_at
        FROM highlights
        WHERE date(next_review) <= date(?)
        ORDER BY {order_clause}
        LIMIT ?
        """,
        (today_iso(), limit),
    ).fetchall()


def fetch_recent(conn: sqlite3.Connection, limit: int = 20) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT id, text, source, author, tags, favorite, is_read, repetitions, next_review
        FROM highlights
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def fetch_recent_filtered(
    conn: sqlite3.Connection,
    keyword: str,
    tag: str,
    limit: int = 100,
    read_mode: str = "unread",
) -> list[sqlite3.Row]:
    kw = keyword.strip()
    tg = tag.strip()
    mode = (read_mode or "unread").strip().lower()
    where_parts: list[str] = []
    if mode == "unread":
        where_parts.append("is_read = 0")
    elif mode == "read":
        where_parts.append("is_read = 1")
    params: list[str | int] = []
    if kw:
        like = f"%{kw}%"
        where_parts.append("(text LIKE ? OR source LIKE ? OR author LIKE ? OR tags LIKE ?)")
        params.extend([like, like, like, like])
    if tg:
        tag_like = f"%{tg}%"
        where_parts.append("tags LIKE ?")
        params.append(tag_like)
    where_sql = " AND ".join(where_parts) if where_parts else "1=1"
    params.append(limit)

    return conn.execute(
        f"""
        SELECT id, text, source, author, tags, favorite, is_read, repetitions, next_review
        FROM highlights
        WHERE {where_sql}
        ORDER BY id DESC
        LIMIT ?
        """,
        tuple(params),
    ).fetchall()


def fetch_favorites_filtered(conn: sqlite3.Connection, keyword: str, tag: str, limit: int = 100) -> list[sqlite3.Row]:
    kw = keyword.strip()
    tg = tag.strip()
    where_parts: list[str] = ["favorite = 1"]
    params: list[str | int] = []
    if kw:
        like = f"%{kw}%"
        where_parts.append("(text LIKE ? OR source LIKE ? OR author LIKE ? OR tags LIKE ?)")
        params.extend([like, like, like, like])
    if tg:
        tag_like = f"%{tg}%"
        where_parts.append("tags LIKE ?")
        params.append(tag_like)
    where_sql = " AND ".join(where_parts)
    params.append(limit)
    return conn.execute(
        f"""
        SELECT id, text, source, author, tags, favorite, is_read, repetitions, next_review
        FROM highlights
        WHERE {where_sql}
        ORDER BY id DESC
        LIMIT ?
        """,
        tuple(params),
    ).fetchall()


def fetch_annotations(conn: sqlite3.Connection, highlight_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT id, selected_text, note, created_at
        FROM annotations
        WHERE highlight_id = ?
        ORDER BY id DESC
        """,
        (highlight_id,),
    ).fetchall()


def row_meta(row: sqlite3.Row) -> str:
    src = f"{row['author']} - {row['source']}".strip(" -")
    tag_value = row["tags"] if "tags" in row.keys() else ""
    tag = render_tags_html(tag_value)
    read_tag = "<span class='tag-read'>已读</span>" if ("is_read" in row.keys() and int(row["is_read"] or 0) == 1) else ""
    return f"{html.escape(src) if src else 'Unknown'}{read_tag}{tag}"


def normalize_tags(raw_tags: str) -> str:
    raw = (raw_tags or "").strip()
    if not raw:
        return ""
    parts = re.split(r"[,，;；\n]+", raw)
    seen: set[str] = set()
    ordered: list[str] = []
    for part in parts:
        t = part.strip()
        if not t:
            continue
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(t)
    return ", ".join(ordered)


def merge_tags(existing_tags: str, incoming_tags: str) -> str:
    existing = normalize_tags(existing_tags)
    incoming = normalize_tags(incoming_tags)
    if not existing:
        return incoming
    if not incoming:
        return existing
    return normalize_tags(f"{existing}, {incoming}")


def render_tags_html(raw_tags: str) -> str:
    normalized = normalize_tags(raw_tags)
    if not normalized:
        return ""
    tags = [x.strip() for x in normalized.split(",") if x.strip()]
    return "".join(f"<span class='tag'>{html.escape(t)}</span>" for t in tags)


def markdown_preview_text(md_text: str, limit: int = 100) -> str:
    text = md_text or ""
    # Remove fenced code blocks and inline markdown markers for list preview.
    text = re.sub(r"(?is)```.*?```", " ", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", text)
    text = re.sub(r"\[[^\]]+\]\((https?://[^\s)]+)\)", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-*]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def strip_leading_duplicate_title(md_text: str, source_title: str) -> str:
    lines = (md_text or "").splitlines()
    source = (source_title or "").strip()
    if not lines or not source:
        return md_text

    def canon(s: str) -> str:
        s = (s or "").strip().lower()
        s = re.sub(r"^#{1,6}\s*", "", s)
        s = re.sub(r"\s+", "", s)
        return s

    source_c = canon(source)
    i = 0
    removed_any = False
    # Only trim the very beginning block to avoid removing legitimate in-body headings.
    while i < len(lines) and i < 10:
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        heading_m = re.match(r"^#{1,6}\s+(.+)$", line)
        candidate = heading_m.group(1).strip() if heading_m else line
        if canon(candidate) == source_c:
            removed_any = True
            i += 1
            continue
        if removed_any and line.startswith("来源:"):
            i += 1
            continue
        break

    if i <= 0:
        return md_text
    return "\n".join(lines[i:]).lstrip("\n")


def card_title_label(row: sqlite3.Row) -> str:
    source = row["source"] if "source" in row.keys() else ""
    title = (source or "").strip() or "未命名摘录"
    date_text = ""
    if "next_review" in row.keys() and row["next_review"]:
        date_text = str(row["next_review"]).strip()
    elif "created_at" in row.keys() and row["created_at"]:
        date_text = str(row["created_at"]).strip()[:10]
    return f"#{row['id']} {title}{(' ' + date_text) if date_text else ''}"


def delete_button(highlight_id: int, return_to: str) -> str:
    safe_return = html.escape(return_to, quote=True)
    return (
        "<form method='post' action='/highlight/delete' "
        "onsubmit=\"return confirm('确认删除这条摘录吗？');\" style='display:inline;'>"
        f"<input type='hidden' name='id' value='{highlight_id}' />"
        f"<input type='hidden' name='return_to' value='{safe_return}' />"
        "<button type='submit' class='danger'>删除</button>"
        "</form>"
    )


def favorite_button(highlight_id: int, is_favorite: bool, return_to: str) -> str:
    safe_return = html.escape(return_to, quote=True)
    label = "取消收藏" if is_favorite else "收藏"
    return (
        "<form method='post' action='/highlight/favorite' style='display:inline;'>"
        f"<input type='hidden' name='id' value='{highlight_id}' />"
        f"<input type='hidden' name='return_to' value='{safe_return}' />"
        "<button type='submit'>"
        f"{label}"
        "</button>"
        "</form>"
    )


def read_button(highlight_id: int, is_read: bool, return_to: str) -> str:
    safe_return = html.escape(return_to, quote=True)
    label = "标记未读" if is_read else "标记已读"
    return (
        "<form method='post' action='/highlight/read' style='display:inline;'>"
        f"<input type='hidden' name='id' value='{highlight_id}' />"
        f"<input type='hidden' name='return_to' value='{safe_return}' />"
        "<button type='submit'>"
        f"{label}"
        "</button>"
        "</form>"
    )


def detail_title_link(highlight_id: int, label: str) -> str:
    return f"<a href='/highlight?id={highlight_id}'>{html.escape(label)}</a>"


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            if path == "/":
                return self.handle_home()
            if path == "/add":
                return self.handle_add_form()
            if path in {"/add-link", "/add_link"}:
                return self.handle_add_link_form()
            if path == "/review":
                return self.handle_review()
            if path == "/highlights":
                return self.handle_highlights()
            if path == "/favorites":
                return self.handle_favorites()
            if path == "/tags":
                return self.handle_tags()
            if path == "/highlight":
                return self.handle_highlight_detail()
            if path == "/daily":
                return self.handle_daily()
            self.respond(HTTPStatus.NOT_FOUND, page_layout("404", "<h1>Not found</h1>"))

        def do_POST(self):
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            if path == "/add":
                return self.handle_add_submit()
            if path in {"/add-link", "/add_link"}:
                return self.handle_add_link_submit()
            if path == "/highlight/annotate":
                return self.handle_annotate_submit()
            if path == "/annotation/delete":
                return self.handle_delete_annotation()
            if path == "/highlight/delete":
                return self.handle_delete_highlight()
            if path == "/highlight/add-tag":
                return self.handle_add_tag_submit()
            if path == "/highlight/favorite":
                return self.handle_favorite_submit()
            if path == "/highlight/read":
                return self.handle_read_submit()
            if path == "/review/score":
                return self.handle_score_submit()
            if path == "/tags/create":
                return self.handle_tag_create()
            if path == "/tags/rename":
                return self.handle_tag_rename()
            if path == "/tags/delete":
                return self.handle_tag_delete()
            self.respond(HTTPStatus.NOT_FOUND, page_layout("404", "<h1>Not found</h1>"))

        def read_form(self) -> dict:
            length = int(self.headers.get("Content-Length", "0"))
            data = self.rfile.read(length).decode("utf-8")
            parsed = parse_qs(data)
            return {k: v[0] for k, v in parsed.items()}

        def respond(
            self,
            status: HTTPStatus,
            body: str,
            content_type: str = "text/html; charset=utf-8",
            extra_headers: list[tuple[str, str]] | None = None,
        ):
            raw = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            if extra_headers:
                for k, v in extra_headers:
                    self.send_header(k, v)
            self.end_headers()
            self.wfile.write(raw)

        def redirect(self, location: str):
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", location)
            self.end_headers()

        def get_cookie(self, name: str) -> str:
            raw = self.headers.get("Cookie", "")
            if not raw:
                return ""
            for part in raw.split(";"):
                token = part.strip()
                if not token or "=" not in token:
                    continue
                k, v = token.split("=", 1)
                if k.strip() == name:
                    return v.strip()
            return ""

        def handle_home(self):
            parsed = urlparse(self.path)
            sort = parse_qs(parsed.query).get("sort", ["desc"])[0].strip().lower()
            if sort not in {"asc", "desc"}:
                sort = "desc"
            with app.conn() as conn:
                counts = fetch_counts(conn)
                due = fetch_due(conn, 6, sort_order=sort, sort_by_time=True)
            cards = []
            for row in due:
                title_label = card_title_label(row)
                body_md = strip_leading_duplicate_title(row["text"], row["source"] if "source" in row.keys() else "")
                preview = markdown_preview_text(body_md, 100)
                preview_html = f"<p>{render_inline(preview)}</p>" if preview else "<p></p>"
                actions = (
                    "<div class='row-actions'>"
                    f"<a href='/highlight?id={row['id']}'>查看并批注</a>"
                    f"{read_button(row['id'], bool(row['is_read']), '/')}"
                    f"{favorite_button(row['id'], bool(row['favorite']), '/')}"
                    f"{delete_button(row['id'], '/')}"
                    "</div>"
                )
                cards.append(
                    f"<div class='card'><h2>{detail_title_link(row['id'], title_label)}</h2>"
                    f"<div class='md'>{preview_html}</div><p class='meta'>{row_meta(row)}</p>{actions}</div>"
                )
            due_html = "".join(cards) if cards else "<div class='card'><p>今天没有到期摘录。</p></div>"
            sort_form = (
                "<form method='get' action='/' class='inline-form'>"
                "<select name='sort' onchange='this.form.submit()'>"
                f"<option value='desc' {'selected' if sort == 'desc' else ''}>时间倒序（默认）</option>"
                f"<option value='asc' {'selected' if sort == 'asc' else ''}>时间顺序</option>"
                "</select>"
                "</form>"
            )
            body = (
                "<h1>SnipNote Web</h1>"
                f"<div class='grid'>"
                f"<div class='card'><h2>总摘录</h2><p>{counts['total']}</p></div>"
                f"<div class='card'><h2>今日到期</h2><p>{counts['due']}</p></div>"
                "</div>"
                "<h2 style='margin-top:14px;'>待复习</h2>"
                f"{sort_form}"
                f"{due_html}"
            )
            self.respond(HTTPStatus.OK, page_layout("SnipNote Web", body))

        def handle_add_form(self):
            body = """
            <h1>添加摘录</h1>
            <div class="card">
              <p class="meta">要从网页自动解析内容，请点这里：<a href="/add-link">进入添加链接页面</a></p>
            </div>
            <form method="post" action="/add" class="card">
              <p><textarea name="text" placeholder="摘录内容" required></textarea></p>
              <div class="grid">
                <p><input name="source" placeholder="来源（书名/文章）" /></p>
                <p><input name="author" placeholder="作者" /></p>
                <p><input name="location" placeholder="位置（页码/链接）" /></p>
                <p><input name="tags" placeholder="标签（逗号/分号分隔）" /></p>
              </div>
              <button type="submit">保存</button>
            </form>
            """
            self.respond(HTTPStatus.OK, page_layout("添加摘录", body))

        def handle_add_link_form(self):
            body = """
            <h1>添加链接</h1>
            <form method="post" action="/add-link" class="card">
              <h2>自动解析网页为 Markdown 摘录</h2>
              <p class="meta">输入文章链接后，系统会提取标题和正文片段，自动生成格式化文本。</p>
              <p><input id="add-link-url" name="url" placeholder="https://example.com/article" required autofocus /></p>
              <div class="grid">
                <p><input name="author" placeholder="作者（可选，留空自动）" /></p>
                <p><input name="tags" placeholder="标签（逗号/分号分隔，可选）" /></p>
              </div>
              <button type="submit">抓取并保存</button>
            </form>
            <script>
            (function() {
              var input = document.getElementById('add-link-url');
              if (!input) return;
              function keepFocus() {
                if (document.activeElement === input) return;
                input.focus({ preventScroll: true });
                try {
                  var len = (input.value || '').length;
                  input.setSelectionRange(len, len);
                } catch (e) {}
              }
              window.requestAnimationFrame(keepFocus);
              setTimeout(keepFocus, 50);
              setTimeout(keepFocus, 150);
              window.addEventListener('pageshow', function () {
                setTimeout(keepFocus, 0);
              });
              document.addEventListener('keydown', function (e) {
                var tag = (e.target && e.target.tagName ? e.target.tagName.toLowerCase() : '');
                var typing = tag === 'input' || tag === 'textarea' || (e.target && e.target.isContentEditable);
                if (!typing && !e.metaKey && !e.ctrlKey && !e.altKey) {
                  keepFocus();
                }
              }, { once: true });
            })();
            </script>
            """
            self.respond(HTTPStatus.OK, page_layout("添加链接", body))

        def handle_add_submit(self):
            form = self.read_form()
            text = form.get("text", "").strip()
            if not text:
                self.respond(HTTPStatus.BAD_REQUEST, page_layout("错误", "<h1>text 不能为空</h1>"))
                return
            now = dt.datetime.now().isoformat(timespec="seconds")
            with app.conn() as conn:
                conn.execute(
                    """
                    INSERT INTO highlights (text, source, author, location, tags, created_at, next_review)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        text,
                        form.get("source", ""),
                        form.get("author", ""),
                        form.get("location", ""),
                        normalize_tags(form.get("tags", "")),
                        now,
                        today_iso(),
                    ),
                )
                conn.commit()
            self.redirect("/highlights")

        def handle_add_link_submit(self):
            form = self.read_form()
            url = form.get("url", "").strip()
            if not url or not (url.startswith("http://") or url.startswith("https://")):
                self.respond(HTTPStatus.BAD_REQUEST, page_layout("错误", "<h1>链接必须以 http:// 或 https:// 开头</h1>"))
                return
            normalized_url = normalize_article_url(url)
            with app.conn() as conn:
                existing = conn.execute(
                    """
                    SELECT id, source, location
                    FROM highlights
                    WHERE location IN (?, ?)
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (url, normalized_url),
                ).fetchone()
            if existing is not None:
                existing_title = html.escape(existing["source"] or "已摘录内容")
                existing_loc = html.escape(existing["location"] or normalized_url, quote=True)
                body = (
                    "<h1>链接已摘录</h1>"
                    "<div class='card'>"
                    "<p class='meta'>该 URL 已存在，不允许重复摘录。</p>"
                    f"<p><strong>{existing_title}</strong></p>"
                    f"<p class='meta'>已保存链接：{existing_loc}</p>"
                    f"<p><a href='/highlight?id={existing['id']}'>打开已有摘录 #{existing['id']}</a></p>"
                    "</div>"
                )
                self.respond(HTTPStatus.CONFLICT, page_layout("链接已摘录", body))
                return
            try:
                parsed = parse_link_to_markdown(url)
                title, markdown = parsed.title, parsed.markdown
            except Exception as exc:
                msg = html.escape(str(exc), quote=False)
                self.respond(
                    HTTPStatus.BAD_REQUEST,
                    page_layout(
                        "抓取失败",
                        f"<h1>抓取失败</h1><div class='card'><p class='meta'>{msg}</p></div>",
                    ),
                )
                return

            parsed = urlparse(url)
            source = title
            author = form.get("author", "").strip()
            tags = normalize_tags(form.get("tags", ""))
            now = dt.datetime.now().isoformat(timespec="seconds")
            with app.conn() as conn:
                conn.execute(
                    """
                    INSERT INTO highlights (text, source, author, location, tags, created_at, next_review)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        markdown,
                        source,
                        author or parsed.netloc,
                        normalized_url,
                        tags,
                        now,
                        today_iso(),
                    ),
                )
                conn.commit()
            self.redirect("/highlights")

        def handle_highlights(self):
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            keyword = query.get("q", [""])[0].strip()
            tag_filter = query.get("tag", [""])[0].strip()
            read_query = query.get("read", [""])[0].strip().lower()
            if read_query in {"all", "unread", "read"}:
                read_filter = read_query
            else:
                cookie_read = self.get_cookie("highlights_read_filter").strip().lower()
                read_filter = cookie_read if cookie_read in {"all", "unread", "read"} else "unread"
            return_to = "/highlights"
            if parsed.query:
                return_to = f"/highlights?{parsed.query}"
            with app.conn() as conn:
                rows = fetch_recent_filtered(conn, keyword, tag_filter, 100, read_filter)
            has_filter = bool(keyword or tag_filter)
            result_meta = (
                f"<p class='meta'>一共搜到 <strong>{len(rows)}</strong> 个结果。</p>"
                if has_filter
                else f"<p class='meta'>当前共显示 <strong>{len(rows)}</strong> 条摘录。</p>"
            )
            read_select = (
                "<select name='read' onchange='this.form.submit()'>"
                f"<option value='unread' {'selected' if read_filter == 'unread' else ''}>仅未读</option>"
                f"<option value='read' {'selected' if read_filter == 'read' else ''}>仅已读</option>"
                f"<option value='all' {'selected' if read_filter == 'all' else ''}>全部</option>"
                "</select>"
            )
            if not rows:
                body = (
                    "<h1>全部摘录</h1>"
                    "<form method='get' action='/highlights' class='inline-form'>"
                    f"<input name='q' placeholder='搜索关键词并高亮' value='{html.escape(keyword)}' />"
                    f"<input name='tag' placeholder='按标签过滤（如 Java）' value='{html.escape(tag_filter)}' />"
                    f"{read_select}"
                    "<button type='submit'>搜索</button></form>"
                    f"{result_meta}"
                    "<div class='card'>暂无数据。</div>"
                )
                cookie_header = (
                    "highlights_read_filter="
                    f"{read_filter}; Path=/; Max-Age=31536000; SameSite=Lax"
                )
                self.respond(
                    HTTPStatus.OK,
                    page_layout("全部摘录", body),
                    extra_headers=[("Set-Cookie", cookie_header)],
                )
                return
            blocks = []
            for row in rows:
                title_label = card_title_label(row)
                body_md = strip_leading_duplicate_title(row["text"], row["source"] if "source" in row.keys() else "")
                preview = markdown_preview_text(body_md, 100)
                preview_html = f"<p>{render_inline(inject_highlight_markers(preview, keyword))}</p>" if preview else "<p></p>"
                actions = (
                    "<div class='row-actions'>"
                    f"<a href='/highlight?id={row['id']}'>查看并批注</a>"
                    f"{read_button(row['id'], bool(row['is_read']), return_to)}"
                    f"{favorite_button(row['id'], bool(row['favorite']), return_to)}"
                    f"{delete_button(row['id'], return_to)}"
                    "</div>"
                )
                blocks.append(
                    f"<div class='card' data-highlight-id='{row['id']}'><h2>{detail_title_link(row['id'], title_label)}</h2>"
                    f"<div class='md'>{preview_html}</div>"
                    f"<p class='meta'>{row_meta(row)}</p>"
                    f"{actions}</div>"
                )
            body = (
                "<h1>全部摘录</h1>"
                "<form method='get' action='/highlights' class='inline-form'>"
                f"<input name='q' placeholder='搜索关键词并高亮' value='{html.escape(keyword)}' />"
                f"<input name='tag' placeholder='按标签过滤（如 Java）' value='{html.escape(tag_filter)}' />"
                f"{read_select}"
                "<button type='submit'>搜索</button></form>"
                f"{result_meta}"
                "<p class='meta'>支持高亮语法：在文本里使用 <code>==需要高亮的内容==</code>。</p>"
                + "".join(blocks)
            )
            cookie_header = (
                "highlights_read_filter="
                f"{read_filter}; Path=/; Max-Age=31536000; SameSite=Lax"
            )
            self.respond(
                HTTPStatus.OK,
                page_layout("全部摘录", body),
                extra_headers=[("Set-Cookie", cookie_header)],
            )

        def handle_favorites(self):
            parsed = urlparse(self.path)
            keyword = parse_qs(parsed.query).get("q", [""])[0].strip()
            tag_filter = parse_qs(parsed.query).get("tag", [""])[0].strip()
            return_to = "/favorites"
            if parsed.query:
                return_to = f"/favorites?{parsed.query}"
            with app.conn() as conn:
                rows = fetch_favorites_filtered(conn, keyword, tag_filter, 100)
            has_filter = bool(keyword or tag_filter)
            result_meta = (
                f"<p class='meta'>一共搜到 <strong>{len(rows)}</strong> 个结果。</p>"
                if has_filter
                else f"<p class='meta'>当前共显示 <strong>{len(rows)}</strong> 条收藏摘录。</p>"
            )
            if not rows:
                body = (
                    "<h1>Favorites</h1>"
                    "<form method='get' action='/favorites' class='inline-form'>"
                    f"<input name='q' placeholder='搜索关键词并高亮' value='{html.escape(keyword)}' />"
                    f"<input name='tag' placeholder='按标签过滤（如 Java）' value='{html.escape(tag_filter)}' />"
                    "<button type='submit'>搜索</button></form>"
                    f"{result_meta}"
                    "<div class='card'>暂无收藏摘录。</div>"
                )
                self.respond(HTTPStatus.OK, page_layout("Favorites", body))
                return
            blocks = []
            for row in rows:
                title_label = card_title_label(row)
                body_md = strip_leading_duplicate_title(row["text"], row["source"] if "source" in row.keys() else "")
                actions = (
                    "<div class='row-actions'>"
                    f"<a href='/highlight?id={row['id']}'>查看并批注</a>"
                    f"{read_button(row['id'], bool(row['is_read']), return_to)}"
                    f"{favorite_button(row['id'], bool(row['favorite']), return_to)}"
                    f"{delete_button(row['id'], return_to)}"
                    "</div>"
                )
                blocks.append(
                    f"<div class='card'><h2>{detail_title_link(row['id'], title_label)}</h2>"
                    f"<div class='md'>{render_markdown(body_md, keyword)}</div>"
                    f"<p class='meta'>{row_meta(row)}</p>"
                    f"{actions}</div>"
                )
            body = (
                "<h1>Favorites</h1>"
                "<form method='get' action='/favorites' class='inline-form'>"
                f"<input name='q' placeholder='搜索关键词并高亮' value='{html.escape(keyword)}' />"
                f"<input name='tag' placeholder='按标签过滤（如 Java）' value='{html.escape(tag_filter)}' />"
                "<button type='submit'>搜索</button></form>"
                f"{result_meta}"
                "<p class='meta'>支持高亮语法：在文本里使用 <code>==需要高亮的内容==</code>。</p>"
                + "".join(blocks)
            )
            self.respond(HTTPStatus.OK, page_layout("Favorites", body))

        def handle_tags(self):
            with app.conn() as conn:
                tags = fetch_all_tags(conn)
            if not tags:
                body = (
                    "<h1>标签管理</h1>"
                    "<p>暂无标签。</p>"
                    "<form method='post' action='/tags/create'>"
                    "<input name='tag' placeholder='新标签名称' required />"
                    "<button type='submit'>创建</button></form>"
                )
                self.respond(HTTPStatus.OK, page_layout("标签管理", body))
                return
            tag_rows = []
            for tag, count in tags:
                tag_escaped = html.escape(tag)
                tag_rows.append(
                    f"<tr><td>{tag_escaped}</td><td>{count}</td>"
                    f"<td>"
                    f"<form method='post' action='/tags/rename' style='display:inline'>"
                    f"<input type='hidden' name='old_tag' value='{tag_escaped}' />"
                    f"<input type='text' name='new_tag' placeholder='新名称' required style='width:100px' />"
                    f"<button type='submit'>改名</button></form> "
                    f"<form method='post' action='/tags/delete' style='display:inline' onsubmit=\"return confirm('确定要删除标签「" + tag_escaped + "」吗？\\\\n所有使用该标签的卡片都会移除该标签。')\">"
                    f"<input type='hidden' name='tag' value='{tag_escaped}' />"
                    f"<button type='submit' class='danger'>删除</button>"
                    f"</form>"
                    f"</td></tr>"
                )
            body = (
                "<h1>标签管理</h1>"
                "<p>共 " + str(len(tags)) + " 个标签。</p>"
                "<form method='post' action='/tags/create' style='margin-bottom:20px'>"
                "<input name='tag' placeholder='新标签名称' required />"
                "<button type='submit'>创建</button></form>"
                "<table><thead><tr><th>标签</th><th>使用次数</th><th>操作</th></tr></thead>"
                "<tbody>" + "".join(tag_rows) + "</tbody></table>"
            )
            self.respond(HTTPStatus.OK, page_layout("标签管理", body))

        def handle_tag_create(self):
            form = self.read_form()
            new_tag = (form.get("tag") or "").strip()
            if not new_tag:
                self.redirect("/tags")
                return
            # Just redirect back - the tag will be created when added to a highlight
            self.redirect("/tags")

        def handle_tag_rename(self):
            form = self.read_form()
            old_tag = (form.get("old_tag") or "").strip()
            new_tag = (form.get("new_tag") or "").strip()
            if not old_tag or not new_tag:
                self.redirect("/tags")
                return
            old_tag_lower = old_tag.lower()
            with app.conn() as conn:
                rows = conn.execute("SELECT id, tags FROM highlights WHERE tags != ''").fetchall()
                for row in rows:
                    tags_str = row["tags"] or ""
                    tags = re.split(r"[,，;；]+", tags_str)
                    new_tags = []
                    for tag in tags:
                        tag = tag.strip()
                        if tag.lower() == old_tag_lower:
                            new_tags.append(new_tag)
                        elif tag:
                            new_tags.append(tag)
                    if new_tags:
                        conn.execute("UPDATE highlights SET tags = ? WHERE id = ?", (", ".join(new_tags), row["id"]))
                    else:
                        conn.execute("UPDATE highlights SET tags = '' WHERE id = ?", (row["id"],))
                conn.commit()
            self.redirect("/tags")

        def handle_tag_delete(self):
            form = self.read_form()
            tag_to_delete = (form.get("tag") or "").strip()
            if not tag_to_delete:
                self.redirect("/tags")
                return
            tag_lower = tag_to_delete.lower()
            with app.conn() as conn:
                rows = conn.execute("SELECT id, tags FROM highlights WHERE tags != ''").fetchall()
                for row in rows:
                    tags_str = row["tags"] or ""
                    tags = re.split(r"[,，;；]+", tags_str)
                    new_tags = [t.strip() for t in tags if t.strip() and t.lower() != tag_lower]
                    if new_tags:
                        conn.execute("UPDATE highlights SET tags = ? WHERE id = ?", (", ".join(new_tags), row["id"]))
                    else:
                        conn.execute("UPDATE highlights SET tags = '' WHERE id = ?", (row["id"],))
                conn.commit()
            self.redirect("/tags")

        def handle_highlight_detail(self):
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            try:
                highlight_id = int(query.get("id", ["0"])[0])
            except ValueError:
                highlight_id = 0
            keep_unread = query.get("keep_unread", ["0"])[0].strip() == "1"
            if highlight_id <= 0:
                self.respond(HTTPStatus.BAD_REQUEST, page_layout("错误", "<h1>参数错误</h1>"))
                return

            with app.conn() as conn:
                row = conn.execute(
                    """
                    SELECT id, text, source, author, location, tags, favorite, is_read, next_review
                    FROM highlights
                    WHERE id = ?
                    """,
                    (highlight_id,),
                ).fetchone()
                if row is None:
                    self.respond(HTTPStatus.NOT_FOUND, page_layout("错误", "<h1>摘录不存在</h1>"))
                    return
                if int(row["is_read"] or 0) == 0 and not keep_unread:
                    conn.execute("UPDATE highlights SET is_read = 1 WHERE id = ?", (highlight_id,))
                    conn.commit()
                    row = conn.execute(
                        """
                        SELECT id, text, source, author, location, tags, favorite, is_read, next_review
                        FROM highlights
                        WHERE id = ?
                        """,
                        (highlight_id,),
                    ).fetchone()
                annotations = fetch_annotations(conn, highlight_id)

            selected_quotes = [a["selected_text"] for a in annotations if a["selected_text"]]
            detail_md = strip_leading_duplicate_title(row["text"], row["source"] or "")
            rendered = render_markdown(detail_md, selected_quotes=selected_quotes)
            ann_blocks = []
            ann_index: dict[str, dict[str, str | int]] = {}
            for ann in annotations:
                selected_text_clean = re.sub(r"\s+", " ", (ann["selected_text"] or "").strip())
                if selected_text_clean and selected_text_clean not in ann_index:
                    ann_index[selected_text_clean] = {
                        "id": int(ann["id"]),
                        "note": ann["note"] or "",
                    }
                quote_html = (
                    f"<blockquote class='meta'>“{html.escape(ann['selected_text'])}”</blockquote>"
                    if ann["selected_text"]
                    else ""
                )
                note_html = (
                    f"<div class='md'><p>{html.escape(ann['note'])}</p></div>"
                    if ann["note"]
                    else "<p class='meta'>（无评价文本）</p>"
                )
                ann_blocks.append(
                    "<div class='card'>"
                    f"<p class='meta'>批注时间：{html.escape(ann['created_at'])}</p>"
                    f"{quote_html}{note_html}"
                    "<div class='row-actions'>"
                    "<form method='post' action='/annotation/delete' style='display:inline;'>"
                    f"<input type='hidden' name='id' value='{ann['id']}' />"
                    f"<input type='hidden' name='highlight_id' value='{row['id']}' />"
                    "<button type='submit' class='danger' onclick=\"return confirm('确认删除这条批注吗？');\">删除批注</button>"
                    "</form>"
                    "</div>"
                    "</div>"
                )
            ann_html = "".join(ann_blocks) if ann_blocks else "<div class='card'><p>还没有批注。</p></div>"
            ann_index_json = json.dumps(ann_index, ensure_ascii=False)
            detail_shortcuts_json = json.dumps(SHORTCUTS_CONFIG.get("detail", {}), ensure_ascii=False)
            hint_highlight = shortcut_hint("detail", "highlight", "H")
            hint_note = shortcut_hint("detail", "note", "M")
            hint_next = shortcut_hint("detail", "next_mark", "J")
            hint_prev = shortcut_hint("detail", "prev_mark", "K")
            hint_edit = shortcut_hint("detail", "edit_note", "Enter")
            hint_delete = shortcut_hint("detail", "delete_annotation", "Delete")
            hint_back = shortcut_hint("detail", "back_to_highlights", "Z")
            hint_save = shortcut_hint("detail", "save_note", "⌘+S / Ctrl+S")
            hint_search = shortcut_hint("detail", "focus_search", "⌘+F / Ctrl+F")
            location_html = ""
            if row["location"]:
                safe_link = html.escape(row["location"], quote=True)
                location_html = (
                    f"<p class='meta'>原文链接："
                    f"<a href='{safe_link}' target='_blank' rel='noopener noreferrer'>{safe_link}</a></p>"
                )
            detail_return_to = f"/highlight?id={row['id']}"
            detail_read_return_to = f"/highlight?id={row['id']}&keep_unread=1"
            interaction_html = f"""
                <div class='card'>
                  <h2>交互批注</h2>
                  <p class='meta'>在正文里先选中文本，再右键。可直接选择“高亮选中”或“写批注”。</p>
                  <p class='meta'>提示：批注会保存到下方批注记录，并自动在正文中高亮对应片段。</p>
                  <p class='meta'>快捷键：<code>{html.escape(hint_highlight)}</code> 高亮，<code>{html.escape(hint_note)}</code> 批注，<code>{html.escape(hint_next)}</code>/<code>{html.escape(hint_prev)}</code> 切换高亮，<code>{html.escape(hint_edit)}</code> 编辑，<code>{html.escape(hint_delete)}</code> 删除，<code>{html.escape(hint_back)}</code> 返回全部摘录，<code>{html.escape(hint_save)}</code> 保存，<code>{html.escape(hint_search)}</code> 搜索。</p>
                  <p><input id='quick-find-input' placeholder='搜索当前文章高亮/笔记' /></p>
                </div>
                <form id='annotate-form' method='post' action='/highlight/annotate' style='display:none;'>
                  <input type='hidden' name='id' value='{row['id']}' />
                  <input type='hidden' name='selected_text' id='selected-text-input' />
                  <input type='hidden' name='note' id='note-input' />
                </form>
                <form id='delete-annotation-form' method='post' action='/annotation/delete' style='display:none;'>
                  <input type='hidden' name='id' id='delete-annotation-id' />
                  <input type='hidden' name='highlight_id' value='{row['id']}' />
                </form>
                <div id='selection-menu' class='ctx-menu'>
                  <button type='button' id='menu-highlight'>高亮选中</button>
                  <button type='button' id='menu-note'>写批注</button>
                </div>
                <div id='note-modal' class='modal'>
                  <div class='modal-card'>
                    <h2>写批注</h2>
                    <p class='meta'>将保存到当前选中文本上。</p>
                    <textarea id='note-textarea' placeholder='写下你的想法、疑问或反驳'></textarea>
                    <div class='actions'>
                      <button type='button' class='secondary' id='note-cancel'>取消</button>
                      <button type='button' id='note-save'>保存批注</button>
                    </div>
                  </div>
                </div>
                <script>
                (function() {{
                  var scrollKey = 'highlight-scroll-{row['id']}';
                  var article = document.getElementById('article-content');
                  var menu = document.getElementById('selection-menu');
                  var noteModal = document.getElementById('note-modal');
                  var noteTextarea = document.getElementById('note-textarea');
                  var quickFindInput = document.getElementById('quick-find-input');
                  var highlightsStateKey = 'highlights_list_state_v1';
                  var highlightsRestoreKey = 'highlights_list_restore_v1';
                  var form = document.getElementById('annotate-form');
                  var deleteForm = document.getElementById('delete-annotation-form');
                  var selectedInput = document.getElementById('selected-text-input');
                  var noteInput = document.getElementById('note-input');
                  var deleteAnnotationIdInput = document.getElementById('delete-annotation-id');
                  var annIndex = {ann_index_json};
                  var detailShortcuts = {detail_shortcuts_json};
                  var currentSelection = '';
                  var currentMarkIndex = -1;
                  var marks = [];

                  function normalizeText(s) {{
                    return (s || '').replace(/\\s+/g, ' ').trim();
                  }}

                  function getSelectionText() {{
                    var sel = window.getSelection();
                    if (!sel || sel.rangeCount === 0) return '';
                    var text = normalizeText(sel.toString() || '');
                    if (!text) return '';
                    var range = sel.getRangeAt(0);
                    var container = range.commonAncestorContainer;
                    var element = container.nodeType === 1 ? container : container.parentElement;
                    if (!article || !element || !article.contains(element)) return '';
                    return text;
                  }}

                  function hideMenu() {{
                    menu.style.display = 'none';
                  }}

                  function isTypingTarget(el) {{
                    if (!el) return false;
                    var tag = (el.tagName || '').toLowerCase();
                    return tag === 'input' || tag === 'textarea' || el.isContentEditable;
                  }}

                  function normalizeKeyName(key) {{
                    var k = (key || '').toLowerCase();
                    if (k === ' ') return 'space';
                    if (k === 'esc') return 'escape';
                    if (k === 'arrowup') return 'up';
                    if (k === 'arrowdown') return 'down';
                    if (k === 'arrowleft') return 'left';
                    if (k === 'arrowright') return 'right';
                    return k;
                  }}

                  function normalizeShortcutSpec(spec) {{
                    var tokens = String(spec || '').toLowerCase().split('+');
                    var mods = [];
                    var key = '';
                    for (var i = 0; i < tokens.length; i++) {{
                      var t = normalizeKeyName(tokens[i].trim());
                      if (!t) continue;
                      if (t === 'meta' || t === 'ctrl' || t === 'alt' || t === 'shift') {{
                        mods.push(t);
                      }} else {{
                        key = t;
                      }}
                    }}
                    mods.sort();
                    if (!key) return mods.join('+');
                    return mods.concat([key]).join('+');
                  }}

                  function eventSpec(e) {{
                    var mods = [];
                    if (e.metaKey) mods.push('meta');
                    if (e.ctrlKey) mods.push('ctrl');
                    if (e.altKey) mods.push('alt');
                    if (e.shiftKey) mods.push('shift');
                    mods.sort();
                    mods.push(normalizeKeyName(e.key || ''));
                    return mods.join('+');
                  }}

                  function matchShortcut(e, specs) {{
                    if (!Array.isArray(specs)) return false;
                    var hit = eventSpec(e);
                    for (var i = 0; i < specs.length; i++) {{
                      if (hit === normalizeShortcutSpec(specs[i])) return true;
                    }}
                    return false;
                  }}

                  function collectMarks() {{
                    marks = Array.prototype.slice.call(article.querySelectorAll('mark'));
                    if (!marks.length) {{
                      currentMarkIndex = -1;
                    }} else if (currentMarkIndex >= marks.length) {{
                      currentMarkIndex = 0;
                    }}
                  }}

                  function activateMark(index, scrollIntoView) {{
                    collectMarks();
                    if (!marks.length) return '';
                    currentMarkIndex = index;
                    if (currentMarkIndex < 0) currentMarkIndex = 0;
                    if (currentMarkIndex >= marks.length) currentMarkIndex = marks.length - 1;
                    marks.forEach(function(m) {{ m.classList.remove('active-mark'); }});
                    var current = marks[currentMarkIndex];
                    current.classList.add('active-mark');
                    if (scrollIntoView) {{
                      current.scrollIntoView({{ block: 'center', behavior: 'smooth' }});
                    }}
                    return normalizeText(current.textContent || '');
                  }}

                  function moveMark(delta) {{
                    collectMarks();
                    if (!marks.length) return '';
                    if (currentMarkIndex < 0) {{
                      currentMarkIndex = delta > 0 ? 0 : marks.length - 1;
                    }} else {{
                      currentMarkIndex = (currentMarkIndex + delta + marks.length) % marks.length;
                    }}
                    return activateMark(currentMarkIndex, true);
                  }}

                  function resolveCurrentSelection() {{
                    var selected = getSelectionText();
                    if (selected) return selected.slice(0, 1200);
                    var markText = activateMark(currentMarkIndex, false);
                    return (markText || '').slice(0, 1200);
                  }}

                  function openNoteModal(defaultText) {{
                    noteTextarea.value = defaultText || '';
                    noteModal.style.display = 'flex';
                    noteTextarea.focus();
                  }}

                  function showMenu(x, y) {{
                    menu.style.left = x + 'px';
                    menu.style.top = y + 'px';
                    menu.style.display = 'block';
                  }}

                  function submitAnnotation(note) {{
                    try {{
                      sessionStorage.setItem(scrollKey, String(window.scrollY || 0));
                    }} catch (e) {{}}
                    selectedInput.value = currentSelection;
                    noteInput.value = note || '';
                    form.submit();
                  }}

                  function deleteCurrentAnnotation() {{
                    var text = resolveCurrentSelection();
                    if (!text) return;
                    var entry = annIndex[text];
                    if (!entry || !entry.id) return;
                    try {{
                      sessionStorage.setItem(scrollKey, String(window.scrollY || 0));
                    }} catch (e) {{}}
                    deleteAnnotationIdInput.value = String(entry.id);
                    deleteForm.submit();
                  }}

                  function pageFind(term) {{
                    var q = normalizeText(term);
                    if (!q) return;
                    if (typeof window.find === 'function') {{
                      window.find(q, false, false, true, false, false, false);
                    }}
                  }}

                  function goBackToHighlights() {{
                    var fallback = '/highlights';
                    try {{
                      var raw = sessionStorage.getItem(highlightsStateKey);
                      if (raw) {{
                        var state = JSON.parse(raw);
                        if (state && typeof state.url === 'string' && state.url.indexOf('/highlights') === 0) {{
                          sessionStorage.setItem(highlightsRestoreKey, '1');
                          window.location.href = state.url;
                          return;
                        }}
                      }}
                    }} catch (e) {{}}
                    window.location.href = fallback;
                  }}

                  try {{
                    var saved = sessionStorage.getItem(scrollKey);
                    if (saved !== null) {{
                      sessionStorage.removeItem(scrollKey);
                      var y = parseInt(saved, 10);
                      if (!isNaN(y)) {{
                        window.scrollTo(0, y);
                      }}
                    }}
                  }} catch (e) {{}}

                  document.addEventListener('contextmenu', function(e) {{
                    var text = getSelectionText();
                    if (!text) {{
                      hideMenu();
                      return;
                    }}
                    e.preventDefault();
                    currentSelection = text.slice(0, 1200);
                    showMenu(e.clientX, e.clientY);
                  }});

                  document.addEventListener('click', function(e) {{
                    if (!menu.contains(e.target)) {{
                      hideMenu();
                    }}
                  }});

                  document.getElementById('menu-highlight').addEventListener('click', function() {{
                    hideMenu();
                    submitAnnotation('');
                  }});

                  document.getElementById('menu-note').addEventListener('click', function() {{
                    hideMenu();
                    openNoteModal('');
                  }});

                  document.getElementById('note-cancel').addEventListener('click', function() {{
                    noteModal.style.display = 'none';
                  }});

                  document.getElementById('note-save').addEventListener('click', function() {{
                    noteModal.style.display = 'none';
                    submitAnnotation((noteTextarea.value || '').trim());
                  }});

                  quickFindInput.addEventListener('keydown', function(e) {{
                    if (e.key === 'Enter') {{
                      e.preventDefault();
                      pageFind(quickFindInput.value || '');
                    }}
                  }});

                  collectMarks();

                  document.addEventListener('keydown', function(e) {{
                    var target = e.target;
                    var typing = isTypingTarget(target);

                    if (matchShortcut(e, detailShortcuts.save_note || [])) {{
                      e.preventDefault();
                      if (noteModal.style.display === 'flex') {{
                        noteModal.style.display = 'none';
                        submitAnnotation((noteTextarea.value || '').trim());
                      }}
                      return;
                    }}

                    if (matchShortcut(e, detailShortcuts.focus_search || [])) {{
                      e.preventDefault();
                      quickFindInput.focus();
                      quickFindInput.select();
                      return;
                    }}

                    if (typing) return;

                    if (matchShortcut(e, detailShortcuts.next_mark || [])) {{
                      e.preventDefault();
                      moveMark(1);
                      return;
                    }}
                    if (matchShortcut(e, detailShortcuts.back_to_highlights || [])) {{
                      e.preventDefault();
                      goBackToHighlights();
                      return;
                    }}
                    if (matchShortcut(e, detailShortcuts.prev_mark || [])) {{
                      e.preventDefault();
                      moveMark(-1);
                      return;
                    }}
                    if (matchShortcut(e, detailShortcuts.highlight || [])) {{
                      e.preventDefault();
                      currentSelection = resolveCurrentSelection();
                      if (!currentSelection) return;
                      submitAnnotation('');
                      return;
                    }}
                    if (matchShortcut(e, detailShortcuts.note || [])) {{
                      e.preventDefault();
                      currentSelection = resolveCurrentSelection();
                      if (!currentSelection) return;
                      var entry = annIndex[currentSelection];
                      openNoteModal(entry && entry.note ? entry.note : '');
                      return;
                    }}
                    if (matchShortcut(e, detailShortcuts.edit_note || [])) {{
                      e.preventDefault();
                      currentSelection = resolveCurrentSelection();
                      if (!currentSelection) return;
                      var entry2 = annIndex[currentSelection];
                      openNoteModal(entry2 && entry2.note ? entry2.note : '');
                      return;
                    }}
                    if (matchShortcut(e, detailShortcuts.delete_annotation || [])) {{
                      e.preventDefault();
                      deleteCurrentAnnotation();
                    }}
                  }});
                }})();
                </script>
            """
            body = (
                f"<h1>摘录 #{row['id']}</h1>"
                "<div class='card'>"
                f"<h2>{html.escape(row['source'] or 'Untitled')}</h2>"
                f"<p class='meta'>{row_meta(row)} | 下次复习 {html.escape(row['next_review'])}</p>"
                "<form method='post' action='/highlight/add-tag' class='inline-form'>"
                f"<input type='hidden' name='id' value='{row['id']}' />"
                "<input name='tags' placeholder='追加标签（逗号/分号分隔）' />"
                "<button type='submit'>追加标签</button>"
                "</form>"
                "<div class='row-actions'>"
                f"{read_button(row['id'], bool(row['is_read']), detail_read_return_to)}"
                f"{favorite_button(row['id'], bool(row['favorite']), detail_return_to)}"
                f"{delete_button(row['id'], '/highlights')}"
                "</div>"
                f"{location_html}"
                f"<div class='md' id='article-content'>{rendered}</div>"
                "</div>"
                f"{interaction_html}"
                "<h2>批注记录</h2>"
                f"{ann_html}"
            )
            self.respond(HTTPStatus.OK, page_layout(f"摘录 {row['id']}", body))

        def handle_annotate_submit(self):
            form = self.read_form()
            try:
                highlight_id = int(form.get("id", "0"))
            except ValueError:
                highlight_id = 0
            selected_text = form.get("selected_text", "").strip()
            note = form.get("note", "").strip()
            if highlight_id <= 0:
                self.respond(HTTPStatus.BAD_REQUEST, page_layout("错误", "<h1>参数错误</h1>"))
                return
            if not selected_text and not note:
                self.redirect(f"/highlight?id={highlight_id}")
                return

            with app.conn() as conn:
                exists = conn.execute("SELECT 1 FROM highlights WHERE id = ?", (highlight_id,)).fetchone()
                if not exists:
                    self.respond(HTTPStatus.NOT_FOUND, page_layout("错误", "<h1>摘录不存在</h1>"))
                    return
                conn.execute(
                    """
                    INSERT INTO annotations (highlight_id, selected_text, note, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        highlight_id,
                        selected_text,
                        note,
                        dt.datetime.now().isoformat(timespec="seconds"),
                    ),
                )
                conn.commit()
            self.redirect(f"/highlight?id={highlight_id}")

        def handle_delete_annotation(self):
            form = self.read_form()
            try:
                annotation_id = int(form.get("id", "0"))
            except ValueError:
                annotation_id = 0
            try:
                highlight_id = int(form.get("highlight_id", "0"))
            except ValueError:
                highlight_id = 0

            if annotation_id > 0:
                with app.conn() as conn:
                    conn.execute("DELETE FROM annotations WHERE id = ?", (annotation_id,))
                    conn.commit()

            if highlight_id > 0:
                self.redirect(f"/highlight?id={highlight_id}")
            else:
                self.redirect("/highlights")

        def handle_delete_highlight(self):
            form = self.read_form()
            try:
                highlight_id = int(form.get("id", "0"))
            except ValueError:
                highlight_id = 0
            return_to = form.get("return_to", "/highlights").strip() or "/highlights"
            if highlight_id <= 0:
                self.respond(HTTPStatus.BAD_REQUEST, page_layout("错误", "<h1>参数错误</h1>"))
                return
            if not return_to.startswith("/"):
                return_to = "/highlights"

            with app.conn() as conn:
                conn.execute("DELETE FROM highlights WHERE id = ?", (highlight_id,))
                conn.commit()
            self.redirect(return_to)

        def handle_add_tag_submit(self):
            form = self.read_form()
            try:
                highlight_id = int(form.get("id", "0"))
            except ValueError:
                highlight_id = 0
            incoming_tags = form.get("tags", "")
            if highlight_id <= 0:
                self.respond(HTTPStatus.BAD_REQUEST, page_layout("错误", "<h1>参数错误</h1>"))
                return
            if not incoming_tags.strip():
                self.redirect(f"/highlight?id={highlight_id}")
                return

            with app.conn() as conn:
                row = conn.execute("SELECT tags FROM highlights WHERE id = ?", (highlight_id,)).fetchone()
                if row is None:
                    self.respond(HTTPStatus.NOT_FOUND, page_layout("错误", "<h1>摘录不存在</h1>"))
                    return
                merged = merge_tags(row["tags"] or "", incoming_tags)
                conn.execute("UPDATE highlights SET tags = ? WHERE id = ?", (merged, highlight_id))
                conn.commit()
            self.redirect(f"/highlight?id={highlight_id}")

        def handle_favorite_submit(self):
            form = self.read_form()
            try:
                highlight_id = int(form.get("id", "0"))
            except ValueError:
                highlight_id = 0
            return_to = form.get("return_to", "/highlights").strip() or "/highlights"
            if highlight_id <= 0:
                self.respond(HTTPStatus.BAD_REQUEST, page_layout("错误", "<h1>参数错误</h1>"))
                return
            if not return_to.startswith("/"):
                return_to = "/highlights"

            with app.conn() as conn:
                row = conn.execute("SELECT favorite FROM highlights WHERE id = ?", (highlight_id,)).fetchone()
                if row is None:
                    self.respond(HTTPStatus.NOT_FOUND, page_layout("错误", "<h1>摘录不存在</h1>"))
                    return
                new_favorite = 0 if int(row["favorite"] or 0) == 1 else 1
                conn.execute("UPDATE highlights SET favorite = ? WHERE id = ?", (new_favorite, highlight_id))
                conn.commit()
            self.redirect(return_to)

        def handle_read_submit(self):
            form = self.read_form()
            try:
                highlight_id = int(form.get("id", "0"))
            except ValueError:
                highlight_id = 0
            return_to = form.get("return_to", "/highlights").strip() or "/highlights"
            if highlight_id <= 0:
                self.respond(HTTPStatus.BAD_REQUEST, page_layout("错误", "<h1>参数错误</h1>"))
                return
            if not return_to.startswith("/"):
                return_to = "/highlights"

            with app.conn() as conn:
                row = conn.execute("SELECT is_read FROM highlights WHERE id = ?", (highlight_id,)).fetchone()
                if row is None:
                    self.respond(HTTPStatus.NOT_FOUND, page_layout("错误", "<h1>摘录不存在</h1>"))
                    return
                new_is_read = 0 if int(row["is_read"] or 0) == 1 else 1
                conn.execute("UPDATE highlights SET is_read = ? WHERE id = ?", (new_is_read, highlight_id))
                conn.commit()
            self.redirect(return_to)

        def handle_review(self):
            with app.conn() as conn:
                rows = fetch_due(conn, 1)
                due_count = fetch_counts(conn)["due"]
            if not rows:
                body = "<h1>复习</h1><div class='card'><p>今天没有到期摘录。</p></div>"
                self.respond(HTTPStatus.OK, page_layout("复习", body))
                return
            row = rows[0]
            title_label = card_title_label(row)
            body_md = strip_leading_duplicate_title(row["text"], row["source"] if "source" in row.keys() else "")
            buttons = "".join(
                f"<button name='quality' value='{q}' type='submit'>{q}</button>" for q in range(6)
            )
            body = (
                f"<h1>复习 <span class='tag'>剩余 {due_count}</span></h1>"
                f"<div class='card'>"
                f"<h2>{detail_title_link(row['id'], title_label)}</h2>"
                f"<div class='md'>{render_markdown(body_md)}</div>"
                f"<p class='meta'>{row_meta(row)}</p>"
                f"<div class='row-actions'><a href='/highlight?id={row['id']}'>查看并批注</a>{read_button(row['id'], bool(row['is_read']), '/review')}{favorite_button(row['id'], bool(row['favorite']), '/review')}{delete_button(row['id'], '/review')}</div>"
                f"<form method='post' action='/review/score'>"
                f"<input type='hidden' name='id' value='{row['id']}' />"
                f"<div class='scorebar'>{buttons}</div>"
                "</form>"
                "</div>"
            )
            self.respond(HTTPStatus.OK, page_layout("复习", body))

        def handle_score_submit(self):
            form = self.read_form()
            try:
                item_id = int(form.get("id", "0"))
                quality = int(form.get("quality", "-1"))
            except ValueError:
                self.respond(HTTPStatus.BAD_REQUEST, page_layout("错误", "<h1>参数错误</h1>"))
                return
            if quality not in {0, 1, 2, 3, 4, 5} or item_id <= 0:
                self.respond(HTTPStatus.BAD_REQUEST, page_layout("错误", "<h1>参数错误</h1>"))
                return
            with app.conn() as conn:
                row = conn.execute(
                    "SELECT id, repetitions, interval_days, efactor FROM highlights WHERE id = ?",
                    (item_id,),
                ).fetchone()
                if row is None:
                    self.respond(HTTPStatus.NOT_FOUND, page_layout("错误", "<h1>摘录不存在</h1>"))
                    return
                result = SM2Scheduler.next_schedule(
                    row["repetitions"], row["interval_days"], row["efactor"], quality
                )
                reps, interval, ef = result.repetitions, result.interval_days, result.efactor
                next_review = result.next_review
                conn.execute(
                    """
                    UPDATE highlights
                    SET repetitions = ?, interval_days = ?, efactor = ?, last_reviewed = ?, next_review = ?
                    WHERE id = ?
                    """,
                    (
                        reps,
                        interval,
                        ef,
                        dt.datetime.now().isoformat(timespec="seconds"),
                        next_review.isoformat(),
                        item_id,
                    ),
                )
                conn.commit()
            self.redirect("/review")

        def handle_daily(self):
            with app.conn() as conn:
                due = fetch_due(conn, 10)
                random_rows = conn.execute(
                    "SELECT id, text, source, author, tags, favorite, is_read, next_review, created_at FROM highlights ORDER BY RANDOM() LIMIT 5"
                ).fetchall()
            due_blocks = []
            for r in due:
                title_label = card_title_label(r)
                body_md = strip_leading_duplicate_title(r["text"], r["source"] if "source" in r.keys() else "")
                due_blocks.append(
                    f"<div class='card'><h2>{detail_title_link(r['id'], title_label)}</h2><div class='md'>{render_markdown(body_md)}</div><p class='meta'>{row_meta(r)}</p><div class='row-actions'><a href='/highlight?id={r['id']}'>查看并批注</a>{read_button(r['id'], bool(r['is_read']), '/daily')}{favorite_button(r['id'], bool(r['favorite']), '/daily')}{delete_button(r['id'], '/daily')}</div></div>"
                )
            due_html = "".join(due_blocks) or "<div class='card'><p>今天没有到期摘录。</p></div>"
            random_blocks = []
            for r in random_rows:
                title_label = card_title_label(r)
                body_md = strip_leading_duplicate_title(r["text"], r["source"] if "source" in r.keys() else "")
                random_blocks.append(
                    f"<div class='card'><h2>{detail_title_link(r['id'], title_label)}</h2><div class='md'>{render_markdown(body_md)}</div><p class='meta'>{row_meta(r)}</p><div class='row-actions'><a href='/highlight?id={r['id']}'>查看并批注</a>{read_button(r['id'], bool(r['is_read']), '/daily')}{favorite_button(r['id'], bool(r['favorite']), '/daily')}{delete_button(r['id'], '/daily')}</div></div>"
                )
            random_html = "".join(random_blocks) or "<div class='card'><p>暂无随机摘录。</p></div>"
            body = (
                f"<h1>今日回顾（{today_iso()}）</h1>"
                "<h2>到期摘录</h2>"
                f"{due_html}"
                "<h2>随机重现</h2>"
                f"{random_html}"
            )
            self.respond(HTTPStatus.OK, page_layout("今日回顾", body))

        def log_message(self, fmt: str, *args):
            return

    return Handler


def main():
    parser = argparse.ArgumentParser(description="SnipNote Web UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    args = parser.parse_args()

    app = App(args.db)
    handler = make_handler(app)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"SnipNote Web running at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
