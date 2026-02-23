#!/usr/bin/env python3
import argparse
import datetime as dt
import html
import html as html_std
import json
import re
import sqlite3
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, parse_qsl, urljoin, urlparse, urlsplit
from urllib.request import Request, urlopen

from parser_engine import parse_link_to_markdown
from readlite import DEFAULT_DB, _next_schedule, connect


def today_iso() -> str:
    return dt.date.today().isoformat()


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
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
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
    return "".join(out) if out else "<p></p>"


def page_layout(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(title)}</title>
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
      <a href="/add-link" title="快捷键 A">添加链接</a>
      <a href="/review">复习</a>
      <a href="/highlights">全部摘录</a>
      <a href="/daily">今日回顾</a>
    </div>
    {body}
  </div>
  <script>
    (function () {{
      function isTypingTarget(el) {{
        if (!el) return false;
        var tag = (el.tagName || '').toLowerCase();
        return tag === 'input' || tag === 'textarea' || el.isContentEditable;
      }}

      document.addEventListener('keydown', function (e) {{
        if (e.metaKey || e.ctrlKey || e.altKey) return;
        if (isTypingTarget(e.target)) return;
        if ((e.key || '').toLowerCase() === 'a') {{
          e.preventDefault();
          window.location.href = '/add-link';
        }}
      }});

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


def fetch_due(conn: sqlite3.Connection, limit: int = 20) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT id, text, source, author, tags, repetitions, next_review, interval_days, efactor
        FROM highlights
        WHERE date(next_review) <= date(?)
        ORDER BY next_review, id
        LIMIT ?
        """,
        (today_iso(), limit),
    ).fetchall()


def fetch_recent(conn: sqlite3.Connection, limit: int = 20) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT id, text, source, author, tags, repetitions, next_review
        FROM highlights
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def fetch_recent_filtered(conn: sqlite3.Connection, keyword: str, limit: int = 100) -> list[sqlite3.Row]:
    kw = keyword.strip()
    if not kw:
        return fetch_recent(conn, limit)
    like = f"%{kw}%"
    return conn.execute(
        """
        SELECT id, text, source, author, tags, repetitions, next_review
        FROM highlights
        WHERE text LIKE ? OR source LIKE ? OR author LIKE ? OR tags LIKE ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (like, like, like, like, limit),
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
    tag = f"<span class='tag'>{html.escape(tag_value)}</span>" if tag_value else ""
    return f"{html.escape(src) if src else 'Unknown'}{tag}"


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
            if path == "/review/score":
                return self.handle_score_submit()
            self.respond(HTTPStatus.NOT_FOUND, page_layout("404", "<h1>Not found</h1>"))

        def read_form(self) -> dict:
            length = int(self.headers.get("Content-Length", "0"))
            data = self.rfile.read(length).decode("utf-8")
            parsed = parse_qs(data)
            return {k: v[0] for k, v in parsed.items()}

        def respond(self, status: HTTPStatus, body: str, content_type: str = "text/html; charset=utf-8"):
            raw = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def redirect(self, location: str):
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", location)
            self.end_headers()

        def handle_home(self):
            with app.conn() as conn:
                counts = fetch_counts(conn)
                due = fetch_due(conn, 6)
            cards = []
            for row in due:
                title_label = f"#{row['id']}（复习 {row['repetitions']} 次）"
                actions = (
                    "<div class='row-actions'>"
                    f"<a href='/highlight?id={row['id']}'>查看并批注</a>"
                    f"{delete_button(row['id'], '/')}"
                    "</div>"
                )
                cards.append(
                    f"<div class='card'><h2>{detail_title_link(row['id'], title_label)}</h2>"
                    f"<div class='md'>{render_markdown(row['text'])}</div><p class='meta'>{row_meta(row)}</p>{actions}</div>"
                )
            due_html = "".join(cards) if cards else "<div class='card'><p>今天没有到期摘录。</p></div>"
            body = (
                "<h1>Readlite Web</h1>"
                f"<div class='grid'>"
                f"<div class='card'><h2>总摘录</h2><p>{counts['total']}</p></div>"
                f"<div class='card'><h2>今日到期</h2><p>{counts['due']}</p></div>"
                "</div>"
                "<h2 style='margin-top:14px;'>待复习</h2>"
                f"{due_html}"
            )
            self.respond(HTTPStatus.OK, page_layout("Readlite Web", body))

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
                <p><input name="tags" placeholder="标签（逗号分隔）" /></p>
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
              <p><input name="url" placeholder="https://example.com/article" required /></p>
              <div class="grid">
                <p><input name="author" placeholder="作者（可选，留空自动）" /></p>
                <p><input name="tags" placeholder="标签（逗号分隔，可选）" /></p>
              </div>
              <button type="submit">抓取并保存</button>
            </form>
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
                        form.get("tags", ""),
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
            tags = form.get("tags", "").strip()
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
                        url,
                        tags,
                        now,
                        today_iso(),
                    ),
                )
                conn.commit()
            self.redirect("/highlights")

        def handle_highlights(self):
            parsed = urlparse(self.path)
            keyword = parse_qs(parsed.query).get("q", [""])[0].strip()
            with app.conn() as conn:
                rows = fetch_recent_filtered(conn, keyword, 100)
            if not rows:
                body = (
                    "<h1>全部摘录</h1>"
                    "<form method='get' action='/highlights' class='inline-form'>"
                    f"<input name='q' placeholder='搜索关键词并高亮' value='{html.escape(keyword)}' />"
                    "<button type='submit'>搜索</button></form>"
                    "<div class='card'>暂无数据。</div>"
                )
                self.respond(HTTPStatus.OK, page_layout("全部摘录", body))
                return
            blocks = []
            for row in rows:
                title_label = f"#{row['id']}（下次 {row['next_review']}）"
                actions = (
                    "<div class='row-actions'>"
                    f"<a href='/highlight?id={row['id']}'>查看并批注</a>"
                    f"{delete_button(row['id'], '/highlights')}"
                    "</div>"
                )
                blocks.append(
                    f"<div class='card'><h2>{detail_title_link(row['id'], title_label)}</h2>"
                    f"<div class='md'>{render_markdown(row['text'], keyword)}</div>"
                    f"<p class='meta'>{row_meta(row)}</p>"
                    f"{actions}</div>"
                )
            body = (
                "<h1>全部摘录</h1>"
                "<form method='get' action='/highlights' class='inline-form'>"
                f"<input name='q' placeholder='搜索关键词并高亮' value='{html.escape(keyword)}' />"
                "<button type='submit'>搜索</button></form>"
                "<p class='meta'>支持高亮语法：在文本里使用 <code>==需要高亮的内容==</code>。</p>"
                + "".join(blocks)
            )
            self.respond(HTTPStatus.OK, page_layout("全部摘录", body))

        def handle_highlight_detail(self):
            parsed = urlparse(self.path)
            try:
                highlight_id = int(parse_qs(parsed.query).get("id", ["0"])[0])
            except ValueError:
                highlight_id = 0
            if highlight_id <= 0:
                self.respond(HTTPStatus.BAD_REQUEST, page_layout("错误", "<h1>参数错误</h1>"))
                return

            with app.conn() as conn:
                row = conn.execute(
                    """
                    SELECT id, text, source, author, location, tags, next_review
                    FROM highlights
                    WHERE id = ?
                    """,
                    (highlight_id,),
                ).fetchone()
                if row is None:
                    self.respond(HTTPStatus.NOT_FOUND, page_layout("错误", "<h1>摘录不存在</h1>"))
                    return
                annotations = fetch_annotations(conn, highlight_id)

            selected_quotes = [a["selected_text"] for a in annotations if a["selected_text"]]
            rendered = render_markdown(row["text"], selected_quotes=selected_quotes)
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
            location_html = ""
            if row["location"]:
                safe_link = html.escape(row["location"], quote=True)
                location_html = (
                    f"<p class='meta'>原文链接："
                    f"<a href='{safe_link}' target='_blank' rel='noopener noreferrer'>{safe_link}</a></p>"
                )
            interaction_html = f"""
                <div class='card'>
                  <h2>交互批注</h2>
                  <p class='meta'>在正文里先选中文本，再右键。可直接选择“高亮选中”或“写批注”。</p>
                  <p class='meta'>提示：批注会保存到下方批注记录，并自动在正文中高亮对应片段。</p>
                  <p class='meta'>快捷键：<code>H</code> 高亮，<code>M</code> 批注，<code>J/K</code> 切换高亮，<code>Enter</code> 编辑，<code>Delete</code> 删除，<code>Z</code> 返回全部摘录，<code>⌘/Ctrl+S</code> 保存，<code>⌘/Ctrl+F</code> 搜索。</p>
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
                  var form = document.getElementById('annotate-form');
                  var deleteForm = document.getElementById('delete-annotation-form');
                  var selectedInput = document.getElementById('selected-text-input');
                  var noteInput = document.getElementById('note-input');
                  var deleteAnnotationIdInput = document.getElementById('delete-annotation-id');
                  var annIndex = {ann_index_json};
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
                    var key = e.key || '';
                    var lower = key.toLowerCase();
                    var metaOrCtrl = !!(e.metaKey || e.ctrlKey);
                    var target = e.target;
                    var typing = isTypingTarget(target);

                    if (metaOrCtrl && lower === 's') {{
                      e.preventDefault();
                      if (noteModal.style.display === 'flex') {{
                        noteModal.style.display = 'none';
                        submitAnnotation((noteTextarea.value || '').trim());
                      }}
                      return;
                    }}

                    if (metaOrCtrl && lower === 'f') {{
                      e.preventDefault();
                      quickFindInput.focus();
                      quickFindInput.select();
                      return;
                    }}

                    if (typing) return;

                    if (lower === 'j') {{
                      e.preventDefault();
                      moveMark(1);
                      return;
                    }}
                    if (lower === 'z') {{
                      e.preventDefault();
                      window.location.href = '/highlights';
                      return;
                    }}
                    if (lower === 'k') {{
                      e.preventDefault();
                      moveMark(-1);
                      return;
                    }}
                    if (lower === 'h') {{
                      e.preventDefault();
                      currentSelection = resolveCurrentSelection();
                      if (!currentSelection) return;
                      submitAnnotation('');
                      return;
                    }}
                    if (lower === 'm') {{
                      e.preventDefault();
                      currentSelection = resolveCurrentSelection();
                      if (!currentSelection) return;
                      var entry = annIndex[currentSelection];
                      openNoteModal(entry && entry.note ? entry.note : '');
                      return;
                    }}
                    if (key === 'Enter') {{
                      e.preventDefault();
                      currentSelection = resolveCurrentSelection();
                      if (!currentSelection) return;
                      var entry2 = annIndex[currentSelection];
                      openNoteModal(entry2 && entry2.note ? entry2.note : '');
                      return;
                    }}
                    if (key === 'Delete' || key === 'Backspace') {{
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
                f"{location_html}"
                f"<div class='md' id='article-content'>{rendered}</div>"
                f"<div class='row-actions'>{delete_button(row['id'], '/highlights')}</div>"
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

        def handle_review(self):
            with app.conn() as conn:
                rows = fetch_due(conn, 1)
                due_count = fetch_counts(conn)["due"]
            if not rows:
                body = "<h1>复习</h1><div class='card'><p>今天没有到期摘录。</p></div>"
                self.respond(HTTPStatus.OK, page_layout("复习", body))
                return
            row = rows[0]
            title_label = f"#{row['id']}（当前间隔 {row['interval_days']} 天）"
            buttons = "".join(
                f"<button name='quality' value='{q}' type='submit'>{q}</button>" for q in range(6)
            )
            body = (
                f"<h1>复习 <span class='tag'>剩余 {due_count}</span></h1>"
                f"<div class='card'>"
                f"<h2>{detail_title_link(row['id'], title_label)}</h2>"
                f"<div class='md'>{render_markdown(row['text'])}</div>"
                f"<p class='meta'>{row_meta(row)}</p>"
                f"<div class='row-actions'><a href='/highlight?id={row['id']}'>查看并批注</a>{delete_button(row['id'], '/review')}</div>"
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
                reps, interval, ef = _next_schedule(
                    row["repetitions"], row["interval_days"], row["efactor"], quality
                )
                next_review = dt.date.today() + dt.timedelta(days=interval)
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
                    "SELECT id, text, source, author, tags FROM highlights ORDER BY RANDOM() LIMIT 5"
                ).fetchall()
            due_blocks = []
            for r in due:
                title_label = f"#{r['id']}"
                due_blocks.append(
                    f"<div class='card'><h2>{detail_title_link(r['id'], title_label)}</h2><div class='md'>{render_markdown(r['text'])}</div><p class='meta'>{row_meta(r)}</p><div class='row-actions'><a href='/highlight?id={r['id']}'>查看并批注</a>{delete_button(r['id'], '/daily')}</div></div>"
                )
            due_html = "".join(due_blocks) or "<div class='card'><p>今天没有到期摘录。</p></div>"
            random_blocks = []
            for r in random_rows:
                title_label = f"#{r['id']}"
                random_blocks.append(
                    f"<div class='card'><h2>{detail_title_link(r['id'], title_label)}</h2><div class='md'>{render_markdown(r['text'])}</div><p class='meta'>{row_meta(r)}</p><div class='row-actions'><a href='/highlight?id={r['id']}'>查看并批注</a>{delete_button(r['id'], '/daily')}</div></div>"
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
    parser = argparse.ArgumentParser(description="Readlite Web UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    args = parser.parse_args()

    app = App(args.db)
    handler = make_handler(app)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Readlite Web running at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
