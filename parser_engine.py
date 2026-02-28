import html as html_std
import json
import os
import re
from typing import Any
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import parse_qsl, quote, urljoin, urlparse, urlsplit
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass
class ParseOutput:
    title: str
    markdown: str


DEFAULT_PARSER_RULES: dict[str, Any] = {
    "blocked_script_sources": [],
    "rules": {},
}


def _merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        base_value = merged.get(key)
        if isinstance(base_value, dict) and isinstance(value, dict):
            merged[key] = _merge_dict(base_value, value)
        else:
            merged[key] = value
    return merged


def load_parser_rules() -> dict[str, Any]:
    config_path = os.path.join(os.path.dirname(__file__), "parser_rules.json")
    if not os.path.exists(config_path):
        return DEFAULT_PARSER_RULES
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            user_config = json.load(f)
    except (OSError, json.JSONDecodeError):
        return DEFAULT_PARSER_RULES
    if not isinstance(user_config, dict):
        return DEFAULT_PARSER_RULES
    return _merge_dict(DEFAULT_PARSER_RULES, user_config)


PARSER_RULES = load_parser_rules()
BLOCKED_SCRIPT_SOURCES = tuple(PARSER_RULES.get("blocked_script_sources", []))


def load_cookies() -> dict[str, dict[str, str]]:
    """从 cookies.json 读取用户配置的 cookie。

    格式:  { "domain": { "cookie_name": "value", ... }, ... }
    """
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies.json")
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        result: dict[str, dict[str, str]] = {}
        for domain, cookies in data.items():
            if isinstance(cookies, dict):
                result[str(domain)] = {str(k): str(v) for k, v in cookies.items()}
        return result
    except (json.JSONDecodeError, OSError):
        return {}


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
        self.current_code_lang = ""

    def _detect_code_lang(self, attrs) -> str:
        attr_map = {k.lower(): (v or "") for k, v in attrs}
        probe = " ".join(
            [
                attr_map.get("class", ""),
                attr_map.get("data-lang", ""),
                attr_map.get("lang", ""),
            ]
        ).lower()
        if not probe:
            return ""
        m = re.search(r"(?:language|lang|brush)[:\s-]+([a-z0-9+#]+)", probe)
        if m:
            lang = m.group(1).lower()
            if lang == "js":
                return "javascript"
            if lang == "ts":
                return "typescript"
            if lang in {"shell", "sh"}:
                return "bash"
            if lang in {"c#", "cs"}:
                return "csharp"
            if lang == "c++":
                return "cpp"
            return lang
        tokens = set(re.findall(r"[a-z0-9+#]+", probe))
        aliases = {
            "java": {"java"},
            "python": {"python", "py"},
            "javascript": {"javascript", "js"},
            "typescript": {"typescript", "ts"},
            "bash": {"bash", "shell", "sh"},
            "json": {"json"},
            "xml": {"xml", "html"},
            "sql": {"sql"},
            "go": {"go", "golang"},
            "rust": {"rust"},
            "csharp": {"csharp", "cs", "c#"},
            "cpp": {"cpp", "c++"},
        }
        for lang, keys in aliases.items():
            if tokens & keys:
                return lang
        return ""

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
        if tag == "pre":
            self.current_tag = "pre"
            self.current_chunks = []
            self.current_code_lang = self._detect_code_lang(attrs)
            return
        if self.current_tag and tag in {"strong", "b"}:
            self.current_chunks.append("**")
        if self.current_tag and tag in {"em", "i"}:
            self.current_chunks.append("*")
        if self.current_tag and tag == "br":
            self.current_chunks.append("\n")
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
        if tag == "pre" and self.current_tag == "pre":
            text = "".join(self.current_chunks).replace("\r\n", "\n").replace("\r", "\n").strip("\n")
            if text.strip():
                code_tag = f"pre:{self.current_code_lang}" if self.current_code_lang else "pre"
                self.blocks.append((code_tag, text))
            self.current_tag = ""
            self.current_chunks = []
            self.current_code_lang = ""
            return
        if self.current_tag and tag in {"strong", "b"}:
            self.current_chunks.append("**")
        if self.current_tag and tag in {"em", "i"}:
            self.current_chunks.append("*")
        if tag == self.current_tag and self.current_chunks:
            text = " ".join(self.current_chunks).strip()
            if text:
                self.blocks.append((tag, re.sub(r"\s+", " ", text)))
            self.current_tag = ""
            self.current_chunks = []

    def handle_data(self, data: str):
        if self.skip_depth > 0:
            return
        if self.current_tag == "pre":
            self.current_chunks.append(data)
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


class BaseSiteRule:
    domains: tuple[str, ...] = ()

    def __init__(self, domains: tuple[str, ...] | None = None):
        if domains is not None:
            self.domains = domains

    def matches(self, host: str) -> bool:
        h = host.lower()
        return any(h == d or h.endswith(f".{d}") for d in self.domains)

    def primary_blocks(self, raw_html: str) -> list[tuple[str, str]]:
        return []

    def clean_blocks(self, blocks: list[tuple[str, str]]) -> list[tuple[str, str]]:
        return blocks

    def clean_images(self, images: list[str]) -> list[str]:
        return images

    def request_headers(self, url: str, referer: str) -> list[dict[str, str]]:
        return []

    def post_parse_blocks(self, blocks: list[tuple[str, str]]) -> list[tuple[str, str]]:
        return blocks

    def min_blocks(self) -> int:
        return 0

    def min_blocks_error(self) -> str:
        return "页面中没有可提取的正文段落"


def extract_balanced_tag_inner(raw_html: str, start_match: re.Match) -> str | None:
    tag = (start_match.group("tag") or "").lower()
    if not tag:
        return None
    start = start_match.end()
    token_re = re.compile(rf"(?is)</?{re.escape(tag)}\b[^>]*>")
    depth = 1
    for token in token_re.finditer(raw_html, start):
        token_text = token.group(0)
        is_end = token_text.startswith("</")
        is_self_closing = token_text.endswith("/>")
        if is_end:
            depth -= 1
            if depth == 0:
                return raw_html[start:token.start()]
        elif not is_self_closing:
            depth += 1
    return None


def extract_container_by_id(raw_html: str, container_id: str) -> str | None:
    cid = re.escape(container_id)
    pat = re.compile(
        rf'(?is)<(?P<tag>[a-z0-9]+)\b[^>]*\bid=["\']?{cid}["\']?[^>]*>',
    )
    m = pat.search(raw_html)
    if not m:
        return None
    return extract_balanced_tag_inner(raw_html, m)


def action_blog_semantic_filter(blocks: list[tuple[str, str]]) -> list[tuple[str, str]]:
    if not blocks:
        return []

    def looks_like_sentence(s: str) -> bool:
        if len(s) < 20:
            return False
        if re.search(r"[。！？；：，,.!?;:]", s):
            return True
        cjk_count = len(re.findall(r"[\u4e00-\u9fff]", s))
        return cjk_count >= 8 and len(s) >= 28

    result: list[tuple[str, str]] = []
    for tag, cleaned in blocks:
        if looks_like_sentence(cleaned):
            result.append((tag, cleaned))
            continue
        if tag in {"h1", "h2", "h3"} and 6 <= len(cleaned) <= 80:
            if not re.search(r"(blogjava|paulwong|rss|首页|联系|管理)", cleaned, re.I):
                result.append((tag, cleaned))
            continue
        if re.match(r"^[A-Z0-9\-\s/]+\(?\d*\)?$", cleaned):
            continue
    pollution_hits = sum(
        1 for _, t in result if re.search(r"(我的随笔|我的评论|给我留言|查看公开留言|查看私人留言|最新评论)", t)
    )
    if pollution_hits > 0:
        result = [(tag, t) for tag, t in result if looks_like_sentence(t)]
    return result


def action_headline_tail_cut(blocks: list[tuple[str, str]]) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    body_like_count = 0
    headline_run = 0

    def is_headline_like(s: str) -> bool:
        if len(s) < 18 or len(s) > 120:
            return False
        if re.search(r"[。！？]", s):
            return False
        if re.search(r"(配信|最終更新|コメント|アクセスランキング)", s):
            return False
        return True

    for tag, cleaned in blocks:
        if re.match(r"^\d+\s", cleaned) and "ランキング" in cleaned:
            break
        if re.search(r"[。！？]", cleaned):
            body_like_count += 1
            headline_run = 0
        elif is_headline_like(cleaned):
            headline_run += 1
            if body_like_count >= 3 and headline_run >= 2:
                break
        else:
            headline_run = 0
        result.append((tag, cleaned))
    return result


PRE_PRIMARY_ACTIONS: dict[str, Any] = {}

POST_CLEAN_ACTIONS = {
    "blog_semantic_filter": action_blog_semantic_filter,
    "headline_tail_cut": action_headline_tail_cut,
}

POST_PARSE_ACTIONS: dict[str, Any] = {}


def extract_discuz_thread_blocks(raw_html: str) -> list[tuple[str, str]]:
    # Discuz thread pages store each floor body in id="postmessage_xxx".
    blocks: list[tuple[str, str]] = []

    title_match = re.search(r"(?is)<h1\b[^>]*>(.*?)</h1>", raw_html)
    if title_match:
        title = _strip_tags(title_match.group(1))
        if title:
            blocks.append(("h2", title))

    floor_entries: list[tuple[str, str, str]] = []
    table_pat = re.compile(r'(?is)<(?P<tag>table)\b[^>]*\bid=["\']pid(\d+)["\'][^>]*>')
    post_pat = re.compile(r'(?is)<(?P<tag>div)\b[^>]*\bid=["\']postmessage_\d+["\'][^>]*>')

    for tm in table_pat.finditer(raw_html):
        table_html = extract_balanced_tag_inner(raw_html, tm)
        if not table_html:
            continue
        floor_m = re.search(r'(?is)<strong\b[^>]*>\s*(\d+)\s*<sup>\s*#\s*</sup>\s*</strong>', table_html)
        if not floor_m:
            continue
        floor = floor_m.group(1).strip()

        author = ""
        # Extract postauthor cell first, then resolve author anchor within it.
        td_author_m = re.search(r'(?is)<(?P<tag>td)\b[^>]*\bclass\s*=\s*["\']?postauthor["\']?[^>]*>', table_html)
        td_author_html = extract_balanced_tag_inner(table_html, td_author_m) if td_author_m else None
        scope_html = td_author_html or table_html
        # Discuz floor author anchor is usually like:
        # <a ... id="userinfo34824502" ...>用户名</a>
        # Allow quoted/unquoted attribute values.
        author_m = re.search(
            r'(?is)<a\b[^>]*\bid\s*=\s*["\']?userinfo\d+["\']?[^>]*>(.*?)</a>',
            scope_html,
        )
        if author_m:
            author = _strip_tags(author_m.group(1))
        if not author:
            author_m = re.search(
                r'(?is)<cite\b[^>]*>\s*<a\b[^>]*>(.*?)</a>',
                scope_html,
            )
            if author_m:
                author = _strip_tags(author_m.group(1))
        if not author:
            # Guest pages can have plain text inside <cite> without an anchor.
            author_m = re.search(r'(?is)<cite\b[^>]*>(.*?)</cite>', scope_html)
            if author_m:
                author = _strip_tags(author_m.group(1))
        author = re.sub(r"\s+", " ", (author or "")).strip()
        if re.fullmatch(r"\d+", author or ""):
            author = ""
        if not author:
            author = "未知用户"

        pm = post_pat.search(table_html)
        if not pm:
            continue
        post_html = extract_balanced_tag_inner(table_html, pm)
        if not post_html:
            continue
        floor_entries.append((floor, author, post_html))

    if not floor_entries:
        return []

    noise_patterns = [
        r"^本帖最后由.+编辑$",
        r"^附件:\s*您所在的用户组无法下载或查看附件$",
        r"^\[\s*本帖最后由.+编辑\s*\]$",
        r"^发表于\s+\d{4}-\d{1,2}-\d{1,2}.*$",
        r"^只看该作者$",
    ]

    seen: set[str] = set()
    seen: set[str] = set()
    for floor, author, post_html in floor_entries:
        # Normalize line breaks first so each floor remains readable.
        normalized = re.sub(r"(?is)<br\s*/?>", "\n", post_html)
        normalized = re.sub(r"(?is)</p\s*>", "\n", normalized)
        normalized = re.sub(r"(?is)</blockquote\s*>", "\n", normalized)
        normalized = re.sub(r"(?is)</div\s*>", "\n", normalized)
        plain = re.sub(r"(?is)<[^>]+>", "", normalized)
        plain = html_std.unescape(plain or "")
        if not plain:
            continue
        lines = [re.sub(r"\s+", " ", ln).strip() for ln in plain.splitlines()]

        cleaned_lines: list[str] = []
        for line in lines:
            t = line.strip()
            if not t:
                continue
            # Drop forum structural actions/buttons.
            if re.search(r"(发短消息|加为好友|使用道具|报告|评分|回复 # 的帖子)$", t):
                continue
            if any(re.search(pat, t, re.I) for pat in noise_patterns):
                continue
            # Keep platform line optional, but keep real content.
            if re.match(r"^posted by wap,\s*platform:", t, re.I):
                continue
            if len(t) < 6:
                continue
            cleaned_lines.append(t)
        if not cleaned_lines:
            continue
        merged = "\n".join(cleaned_lines)
        key = f"{floor}|{author}|{merged}".lower()
        if key in seen:
            continue
        seen.add(key)
        blocks.append(("h3", f"{floor}楼 @{author}"))
        blocks.append(("p", merged))

    return blocks[:220]


PRE_PRIMARY_ACTIONS["discuz_thread_posts"] = extract_discuz_thread_blocks


class ConfigSiteRule(BaseSiteRule):
    def __init__(self, rule_key: str, cfg: dict[str, Any]):
        self.rule_key = rule_key
        self.cfg = cfg
        domains_raw = cfg.get("domains", [])
        domains = tuple(str(d).lower() for d in domains_raw if str(d).strip())
        super().__init__(domains)

    def primary_blocks(self, raw_html: str) -> list[tuple[str, str]]:
        for action_name in self.cfg.get("pre_primary_actions", []) or []:
            action = PRE_PRIMARY_ACTIONS.get(str(action_name))
            if action is None and str(action_name) == "yahoo_preloaded_state":
                action = extract_yahoo_preloaded_blocks
            if not action:
                continue
            blocks = action(raw_html)
            if blocks:
                return blocks
        for container_id in self.cfg.get("primary_container_ids", []) or []:
            container_html = extract_container_by_id(raw_html, str(container_id))
            if container_html:
                blocks = fallback_extract_blocks(container_html)
                if blocks:
                    return blocks
        patterns = self.cfg.get("primary_html_patterns", []) or []
        for pat in patterns:
            m = re.search(str(pat), raw_html)
            if m:
                blocks = fallback_extract_blocks(m.group(1))
                if blocks:
                    return blocks
        return []

    def clean_blocks(self, blocks: list[tuple[str, str]]) -> list[tuple[str, str]]:
        drop_exact = {str(x) for x in (self.cfg.get("drop_exact", []) or [])}
        drop_patterns = [str(x) for x in (self.cfg.get("drop_patterns", []) or [])]
        stop_patterns = [str(x) for x in (self.cfg.get("stop_patterns", []) or [])]
        replacements = self.cfg.get("text_replacements", []) or []
        skip_rel_links = bool(self.cfg.get("skip_relative_markdown_links", False))

        result: list[tuple[str, str]] = []
        for tag, text in blocks:
            is_pre = tag == "pre" or str(tag).startswith("pre:")
            if is_pre:
                cleaned = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip("\n")
            else:
                cleaned = re.sub(r"\s+", " ", (text or "")).strip()
            if not cleaned:
                continue
            if skip_rel_links and re.match(r"^\[[^\]]*\]\(/[^)]+\)$", cleaned):
                continue
            if cleaned in drop_exact:
                continue
            if any(re.search(pat, cleaned, re.I) for pat in stop_patterns):
                break
            if any(re.search(pat, cleaned, re.I) for pat in drop_patterns):
                continue
            for repl in replacements:
                if not isinstance(repl, dict):
                    continue
                pat = str(repl.get("pattern") or "")
                to = str(repl.get("to") or "")
                if pat:
                    cleaned = re.sub(pat, to, cleaned, flags=re.I)
            cleaned = cleaned.strip()
            if not cleaned:
                continue
            if (not is_pre) and is_too_short(cleaned, tag):
                continue
            result.append((tag, cleaned))

        for action_name in self.cfg.get("post_clean_actions", []) or []:
            action = POST_CLEAN_ACTIONS.get(str(action_name))
            if action:
                result = action(result)
        return result

    def clean_images(self, images: list[str]) -> list[str]:
        keywords = [str(k).lower() for k in (self.cfg.get("image_drop_keywords", []) or [])]
        max_images = int(self.cfg.get("max_images", 4))
        filtered = []
        for u in images:
            lower = u.lower()
            if any(k in lower for k in keywords):
                continue
            filtered.append(u)
        return filtered[:max_images]

    def request_headers(self, url: str, referer: str) -> list[dict[str, str]]:
        request_headers = self.cfg.get("request_headers", {})
        headers = dict(request_headers) if isinstance(request_headers, dict) else {}
        cookie_env_var = str(self.cfg.get("cookie_env_var") or "").strip()
        if cookie_env_var:
            cookie = os.environ.get(cookie_env_var, "").strip()
            if cookie:
                headers["Cookie"] = cookie
        if headers:
            if "Referer" not in headers:
                headers["Referer"] = referer
            return [headers]
        return []

    def post_parse_blocks(self, blocks: list[tuple[str, str]]) -> list[tuple[str, str]]:
        result = blocks
        for action_name in self.cfg.get("post_parse_actions", []) or []:
            action = POST_PARSE_ACTIONS.get(str(action_name))
            if action is None and str(action_name) == "hard_filter_blogjava_blocks":
                action = hard_filter_blogjava_blocks
            if action:
                result = action(result)
        return result

    def min_blocks(self) -> int:
        return int(self.cfg.get("min_blocks", 0))

    def min_blocks_error(self) -> str:
        return str(self.cfg.get("min_blocks_error") or "页面中没有可提取的正文段落")


def build_rules() -> list[BaseSiteRule]:
    rules_cfg = PARSER_RULES.get("rules", {})
    if not isinstance(rules_cfg, dict):
        return []
    built: list[BaseSiteRule] = []
    for rule_key, cfg in rules_cfg.items():
        if isinstance(cfg, dict):
            built.append(ConfigSiteRule(str(rule_key), cfg))
    return built


RULES: list[BaseSiteRule] = build_rules()


def choose_rule(host: str) -> BaseSiteRule | None:
    for rule in RULES:
        if rule.matches(host):
            return rule
    return None


def _attempt_fetch(url: str, headers: dict[str, str], timeout: int) -> bytes:
    req = Request(url, headers=headers)
    with urlopen(req, timeout=timeout) as resp:
        content_type = (resp.headers.get("Content-Type") or "").lower()
        if "text/html" not in content_type and content_type:
            raise ValueError(f"不支持的内容类型: {content_type}")
        return resp.read()


def _attempt_fetch_with_cookies(
    url: str,
    cookies: dict[str, str],
    timeout: int = 10,
) -> tuple[str, bytes]:
    """使用 requests 库抓取需要 cookie 认证的页面。"""
    import requests as _requests

    parsed = urlparse(url)
    host = parsed.netloc
    referer = f"{parsed.scheme}://{host}/"
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
                  "image/avif,image/webp,image/apng,*/*;q=0.8,"
                  "application/signed-exchange;v=b3;q=0.7",
        "accept-language": "en,zh;q=0.9,zh-CN;q=0.8,zh-TW;q=0.7,ja;q=0.6",
        "cache-control": "max-age=0",
        "dnt": "1",
        "referer": referer,
        "sec-ch-ua": '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "same-origin",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        "user-agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/145.0.0.0 Safari/537.36"
        ),
    }
    resp = _requests.get(url, headers=headers, cookies=cookies, timeout=timeout)
    resp.raise_for_status()
    ct = (resp.headers.get("Content-Type") or "").lower()
    if "text/html" not in ct and ct:
        raise ValueError(f"不支持的内容类型: {ct}")
    return resp.url, resp.content


def fetch_html_with_retry(url: str, timeout: int = 10) -> tuple[str, bytes]:
    parsed = urlparse(url)
    host = parsed.netloc
    referer = f"{parsed.scheme}://{host}/" if parsed.scheme and host else "https://www.google.com/"

    # ── Cookie 认证路径（使用 requests 库）──────────────────────
    cookies_dict = load_cookies()
    domain_cookies: dict[str, str] | None = None
    for domain_key, cookie_val in cookies_dict.items():
        if host == domain_key or host.endswith(f".{domain_key}"):
            domain_cookies = cookie_val
            break
    if domain_cookies:
        try:
            return _attempt_fetch_with_cookies(url, domain_cookies, timeout=timeout)
        except Exception as exc:
            raise RuntimeError(f"Cookie 认证抓取失败: {exc}") from exc

    # ── 普通路径（原有 urllib 逻辑，零改动）─────────────────────
    candidates = [url]
    if host.endswith("economist.com") and not url.rstrip("/").endswith("/amp"):
        candidates.append(url.rstrip("/") + "/amp")

    header_profiles = [
        {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": referer,
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
        {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": referer,
        },
    ]
    rule = choose_rule(host)
    if rule:
        # Rule-specific profiles are prepended (higher priority) but never hardcode credentials.
        header_profiles = rule.request_headers(url, referer) + header_profiles

    last_err: Exception | None = None
    for target in candidates:
        for headers in header_profiles:
            try:
                return target, _attempt_fetch(target, headers, timeout)
            except HTTPError as exc:
                last_err = exc
                # Keep trying other header profiles/URLs for common blocks.
                if exc.code in {401, 403, 429, 503}:
                    continue
                raise
            except URLError as exc:
                last_err = exc
                continue
    if isinstance(last_err, HTTPError) and last_err.code == 403:
        raise PermissionError(
            "目标站点拒绝抓取（HTTP 403）。这通常是反爬或付费墙限制；可尝试该文章的 AMP 页面，或手动粘贴正文。"
        )
    if last_err is not None:
        raise RuntimeError(f"抓取失败: {last_err}")
    raise RuntimeError("抓取失败: 未知网络错误")


def _extract_meta_charset(raw: bytes) -> str:
    # Parse charset from early HTML bytes using latin-1 to avoid decode failures.
    head = raw[:8192].decode("latin-1", errors="ignore")
    m = re.search(r'(?is)<meta[^>]+charset=["\']?\s*([a-zA-Z0-9._-]+)\s*["\']?', head)
    if m:
        return m.group(1).strip().lower()
    m = re.search(r'(?is)<meta[^>]+content=["\'][^"\']*charset=([a-zA-Z0-9._-]+)[^"\']*["\']', head)
    if m:
        return m.group(1).strip().lower()
    return ""


def _decode_html_bytes(raw: bytes, preferred_encoding: str = "") -> str:
    candidates: list[str] = []
    pref = (preferred_encoding or "").strip().lower()
    if pref:
        candidates.append(pref)
    meta_charset = _extract_meta_charset(raw)
    if meta_charset and meta_charset not in candidates:
        candidates.append(meta_charset)
    for enc in ("utf-8", "gb18030", "big5", "latin-1"):
        if enc not in candidates:
            candidates.append(enc)

    for enc in candidates:
        try:
            return raw.decode(enc, errors="strict")
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", errors="replace")


def _strip_tags(value: str) -> str:
    s = re.sub(r"(?is)<[^>]+>", " ", value or "")
    s = html_std.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _extract_archive_snapshot_url(raw_html: str) -> str | None:
    blue_pat = r'<a\s+[^>]*style=["\'][^"\']*color:\s*blue[^"\']*["\'][^>]*href=["\']?([^"\'> ]+)["\']?'
    blue_match = re.search(blue_pat, raw_html, re.IGNORECASE | re.DOTALL)
    if blue_match:
        candidate = blue_match.group(1).strip()
        if candidate:
            return urljoin("https://archive.is/", candidate)
    thumb_pat = r'<a\s+style=["\']text-decoration:\s*none["\']\s+href=["\']([^"\']+)["\']'
    thumb_matches = re.findall(thumb_pat, raw_html, flags=re.IGNORECASE)
    if thumb_matches:
        return urljoin("https://archive.is/", thumb_matches[-1].strip())
    return None


def _get_archive_snapshot_url(url: str, timeout: int) -> str | None:
    import requests as _requests

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Referer": "https://archive.is/",
    }
    check_url = f"https://archive.is/{quote(url, safe='')}"
    try:
        r = _requests.get(check_url, headers=headers, timeout=timeout, allow_redirects=True)
        if r.status_code != 200:
            return None
        html = r.text
    except Exception:
        return None
    return _extract_archive_snapshot_url(html)


def _is_probable_economist_paywall(blocks: list[tuple[str, str]]) -> bool:
    if not blocks:
        return True
    joined = " ".join(text for _, text in blocks[:30]).lower()
    # Strong paywall signals: if any of these appear, it's definitely paywalled.
    strong_signals = [
        "explore the edition",
        "appeared in the",
        "reuse this content",
        "list of contents",
    ]
    if any(sig in joined for sig in strong_signals):
        return True
    paywall_terms = [
        "subscribe",
        "subscriber-only",
        "already a subscriber",
        "log in",
        "sign in",
        "to continue reading",
        "start your subscription",
    ]
    long_body_count = sum(
        1
        for tag, text in blocks
        if tag not in {"h1", "h2", "h3"} and len((text or "").strip()) >= 120
    )
    if any(term in joined for term in paywall_terms) and long_body_count < 2:
        return True
    if long_body_count == 0 and len(blocks) <= 3:
        return True
    return False


def _extract_economist_snapshot_blocks(snapshot_html: str) -> tuple[str, list[tuple[str, str]]]:
    # Detect CAPTCHA / bot-check pages from archive.is
    lower_html = snapshot_html[:3000].lower()
    if "captcha" in lower_html or "security check" in lower_html or "one more step" in lower_html:
        return "", []
    h1_match = re.search(r"(?is)<h1[^>]*>(.*?)</h1>", snapshot_html)
    title = _strip_tags(h1_match.group(1)) if h1_match else ""
    container_html = extract_container_by_id(snapshot_html, "new-article-template")
    if not container_html:
        container_html = extract_container_by_id(snapshot_html, "CONTENT")
    blocks = fallback_extract_blocks(container_html or snapshot_html)

    noise_words = (
        "subscribe",
        "log in",
        "sign in",
        "menu",
        "share",
        "photograph:",
        "©",
        "copyright",
    )
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for tag, text in blocks:
        cleaned = re.sub(r"\s+", " ", (text or "")).strip()
        if len(cleaned) < 30:
            continue
        lower = cleaned.lower()
        if any(w in lower for w in noise_words):
            continue
        key = f"{tag}|{cleaned}"
        if key in seen:
            continue
        seen.add(key)
        result.append((tag, cleaned))

    if result:
        return title, result[:180]

    # Final fallback: extract plain <p> content.
    paras = re.findall(r"(?is)<p[^>]*>(.*?)</p>", snapshot_html)
    plain: list[tuple[str, str]] = []
    for raw in paras:
        cleaned = _strip_tags(raw)
        if len(cleaned) >= 40:
            plain.append(("p", cleaned))
    return title, plain[:180]


def _try_economist_archive_snapshot(url: str, timeout: int = 10) -> tuple[str, list[tuple[str, str]]] | None:
    import requests as _requests

    snapshot_url = _get_archive_snapshot_url(url, timeout)
    if not snapshot_url:
        return None
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    }
    try:
        resp = _requests.get(snapshot_url, headers=headers, timeout=timeout)
        if resp.status_code != 200:
            return None
        html = resp.text
    except Exception:
        return None
    title, blocks = _extract_economist_snapshot_blocks(html)
    if not blocks:
        return None
    return title, blocks


def parse_link_to_markdown(url: str, timeout: int = 10) -> ParseOutput:
    fetched_url, raw = fetch_html_with_retry(url, timeout=timeout)
    parsed = urlparse(fetched_url)
    host = parsed.netloc
    rule = choose_rule(host)
    preferred_encoding = ""
    if isinstance(rule, ConfigSiteRule):
        preferred_encoding = str(rule.cfg.get("preferred_encoding") or "").strip()

    text = _decode_html_bytes(raw, preferred_encoding=preferred_encoding)
    text = strip_blocked_scripts(text)

    parser = ArticleExtractor()
    parser.feed(text)
    parser.close()

    title = parser.title or host or "Untitled Page"
    blocks = parser.blocks[:180]
    fallback_blocks = fallback_extract_blocks(text)[:180]
    jsonld_blocks = extract_jsonld_blocks(text)[:180]
    meta_blocks = extract_meta_description(text)
    rule_blocks = rule.primary_blocks(text)[:180] if rule else []
    image_urls = extract_image_urls(text, fetched_url)[:4]

    if rule_blocks:
        chosen_blocks = rule_blocks
    else:
        candidates = [blocks, fallback_blocks, jsonld_blocks, meta_blocks]
        chosen_blocks = max(candidates, key=blocks_quality)
    if rule:
        chosen_blocks = rule.clean_blocks(chosen_blocks)
        image_urls = rule.clean_images(image_urls)
        chosen_blocks = rule.post_parse_blocks(chosen_blocks)
    if host.endswith("economist.com"):
        min_required = rule.min_blocks() if rule else 0
        if _is_probable_economist_paywall(chosen_blocks) or (min_required and len(chosen_blocks) < min_required):
            snapshot = _try_economist_archive_snapshot(url, timeout=timeout)
            if snapshot is not None:
                snapshot_title, snapshot_blocks = snapshot
                if snapshot_title:
                    title = snapshot_title
                chosen_blocks = snapshot_blocks
                if rule:
                    chosen_blocks = rule.clean_blocks(chosen_blocks)
                    chosen_blocks = rule.post_parse_blocks(chosen_blocks)

    if rule and len(chosen_blocks) < rule.min_blocks():
        raise ValueError(rule.min_blocks_error())

    if not chosen_blocks:
        raise ValueError("页面中没有可提取的正文段落")

    lines = [f"# {title}", "", f"来源: [{host or fetched_url}]({fetched_url})", ""]
    for idx, img in enumerate(image_urls, start=1):
        lines.append(f"![图片 {idx}]({img})")
        lines.append("")
    total_chars = 0
    max_chars = 45000
    for tag, block in chosen_blocks:
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
        elif tag == "pre" or str(tag).startswith("pre:"):
            lang = "java"
            if ":" in str(tag):
                parsed_lang = str(tag).split(":", 1)[1].strip().lower()
                if parsed_lang:
                    lang = parsed_lang
            fence = f"```{lang}" if lang else "```"
            lines.append(fence)
            lines.append(chunk)
            lines.append("```")
        elif tag == "li":
            lines.append(f"- {chunk}")
        else:
            lines.append(chunk)
        lines.append("")
    markdown = "\n".join(lines).strip()
    return ParseOutput(title=title, markdown=markdown)


def extract_js_object_by_marker(raw_html: str, marker: str) -> dict[str, Any] | None:
    pos = raw_html.find(marker)
    if pos < 0:
        return None
    start = raw_html.find("{", pos)
    if start < 0:
        return None

    depth = 0
    in_str = False
    esc = False
    quote = ""
    end = -1
    for i in range(start, len(raw_html)):
        ch = raw_html[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == quote:
                in_str = False
            continue
        if ch in {"'", '"'}:
            in_str = True
            quote = ch
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end <= start:
        return None

    payload = raw_html[start:end]
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return None


def extract_yahoo_preloaded_blocks(raw_html: str) -> list[tuple[str, str]]:
    state = extract_js_object_by_marker(raw_html, "window.__PRELOADED_STATE__")
    if not isinstance(state, dict):
        return []
    page_data = state.get("pageData")
    article_detail = page_data.get("articleDetail") if isinstance(page_data, dict) else None
    if not isinstance(article_detail, dict):
        return []

    blocks: list[tuple[str, str]] = []
    headline = str(article_detail.get("headline") or "").strip()
    if headline:
        blocks.append(("h2", headline))

    paragraphs = article_detail.get("paragraphs")
    if isinstance(paragraphs, list):
        for para in paragraphs:
            if not isinstance(para, dict):
                continue
            text_details = para.get("textDetails")
            if isinstance(text_details, list):
                for td in text_details:
                    if not isinstance(td, dict):
                        continue
                    text = str(td.get("text") or "").strip()
                    if not text:
                        continue
                    for line in text.split("\n"):
                        cleaned = re.sub(r"\s+", " ", line).strip()
                        if cleaned:
                            blocks.append(("p", cleaned))

    # De-duplicate while preserving order.
    seen: set[str] = set()
    deduped: list[tuple[str, str]] = []
    for tag, text in blocks:
        key = f"{tag}|{text}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append((tag, text))
    return deduped


def hard_filter_blogjava_blocks(blocks: list[tuple[str, str]]) -> list[tuple[str, str]]:
    nav_words = {
        "首页",
        "联系",
        "管理",
        "我的随笔",
        "我的评论",
        "我的参与",
        "最新评论",
        "给我留言",
        "查看公开留言",
        "查看私人留言",
    }

    def sentence_like(s: str) -> bool:
        if len(s) < 20:
            return False
        if re.search(r"[。！？；：，,.!?;:]", s):
            return True
        return len(re.findall(r"[\u4e00-\u9fff]", s)) >= 10

    result: list[tuple[str, str]] = []
    for tag, text in blocks:
        t = re.sub(r"\s+", " ", (text or "")).strip()
        if not t:
            continue
        lower = t.lower()
        if t in nav_words:
            continue
        if re.search(r"\(rss\)\s*$", t, re.I):
            continue
        if re.search(r"^\d{4}年\d{1,2}月\s*\(\d+\)\s*$", t):
            continue
        if re.search(r"^www\.blogjava\.net\s+-", t, re.I):
            continue
        if re.search(r"^\s*图片(\s*\d+)?\s*$", t, re.I):
            continue
        if re.search(r"^paulwong\s*$", t, re.I):
            continue
        if re.search(r"聚合", t, re.I):
            continue
        if not sentence_like(t) and tag in {"p", "li", "blockquote"}:
            continue
        result.append((tag, t))
    return result


def strip_blocked_scripts(raw_html: str) -> str:
    cleaned = raw_html
    for src in BLOCKED_SCRIPT_SOURCES:
        escaped = re.escape(src)
        cleaned = re.sub(
            rf'(?is)<script[^>]*src=["\']{escaped}["\'][^>]*>.*?</script>',
            "",
            cleaned,
        )
        cleaned = re.sub(
            rf'(?is)<script[^>]*src=["\']{escaped}["\'][^>]*/?>',
            "",
            cleaned,
        )
    return cleaned


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
            if not isinstance(item, dict):
                continue
            headline = str(item.get("headline") or item.get("name") or "").strip()
            body = str(item.get("articleBody") or item.get("text") or item.get("description") or "").strip()
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

    meta_patterns = [
        r'(?is)<meta[^>]*property=["\']og:image(?::secure_url)?["\'][^>]*content=["\'](.*?)["\'][^>]*>',
        r'(?is)<meta[^>]*name=["\']twitter:image(?::src)?["\'][^>]*content=["\'](.*?)["\'][^>]*>',
    ]
    for pat in meta_patterns:
        for m in re.finditer(pat, raw_html):
            add(m.group(1))

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
            if not isinstance(item, dict):
                continue
            image_value = item.get("image")
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

    area_match = re.search(r"(?is)<(article|main)[^>]*>(.*?)</\1>", raw_html)
    area = area_match.group(2) if area_match else raw_html
    for m in re.finditer(r"(?is)<img[^>]+>", area):
        tag = m.group(0)
        src_match = re.search(r'(?i)\b(?:src|data-src|data-original|data-lazy-src)=["\'](.*?)["\']', tag)
        if src_match:
            add(src_match.group(1))

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
    code_blocks: list[tuple[str, str]] = []

    def detect_lang_from_attr(attr_text: str) -> str:
        probe = (attr_text or "").lower()
        m = re.search(r"(?:language|lang|brush)[:\s-]+([a-z0-9+#]+)", probe)
        if m:
            lang = m.group(1).lower()
            if lang == "js":
                return "javascript"
            if lang == "ts":
                return "typescript"
            if lang in {"shell", "sh"}:
                return "bash"
            if lang in {"c#", "cs"}:
                return "csharp"
            if lang == "c++":
                return "cpp"
            return lang
        tokens = set(re.findall(r"[a-z0-9+#]+", probe))
        aliases = {
            "java": {"java"},
            "python": {"python", "py"},
            "javascript": {"javascript", "js"},
            "typescript": {"typescript", "ts"},
            "bash": {"bash", "shell", "sh"},
            "json": {"json"},
            "xml": {"xml", "html"},
            "sql": {"sql"},
            "go": {"go", "golang"},
            "rust": {"rust"},
            "csharp": {"csharp", "cs", "c#"},
            "cpp": {"cpp", "c++"},
        }
        for lang, keys in aliases.items():
            if tokens & keys:
                return lang
        return ""

    def pre_repl(match: re.Match) -> str:
        attrs = match.group(1) or ""
        inner = match.group(2)
        inner = re.sub(r"(?is)<\s*br\s*/?\s*>", "\n", inner)
        inner = re.sub(r"(?is)</p\s*>", "\n", inner)
        inner = re.sub(r"(?is)<[^>]+>", "", inner)
        code = html_std.unescape(inner).replace("\r\n", "\n").replace("\r", "\n").strip("\n")
        if not code.strip():
            return "\n"
        code_blocks.append((detect_lang_from_attr(attrs), code))
        return f"\n__CODE_BLOCK_{len(code_blocks)-1}__\n"

    content = re.sub(r"(?is)<pre([^>]*)>(.*?)</pre>", pre_repl, content)
    main_match = re.search(r"(?is)<(article|main)[^>]*>(.*?)</\1>", content)
    if main_match:
        content = main_match.group(2)
    else:
        body_match = re.search(r"(?is)<body[^>]*>(.*?)</body>", content)
        if body_match:
            content = body_match.group(1)
    # Preserve a subset of inline formatting as markdown.
    content = re.sub(r"(?is)<\s*br\s*/?\s*>", "\n", content)
    content = re.sub(r"(?is)<\s*/?\s*(strong|b)\s*>", "**", content)
    content = re.sub(r"(?is)<\s*/?\s*(em|i)\s*>", "*", content)
    content = re.sub(
        r'(?is)<a[^>]*href=["\'](.*?)["\'][^>]*>(.*?)</a>',
        lambda m: f"[{re.sub(r'(?is)<[^>]+>', ' ', m.group(2)).strip()}]({m.group(1).strip()})",
        content,
    )
    content = re.sub(r"(?i)</(p|li|h1|h2|h3|h4|h5|h6|blockquote|div|section|article)>", "\n", content)
    content = re.sub(r"(?is)<[^>]+>", " ", content)
    content = html_std.unescape(content)
    lines = []
    for part in content.splitlines():
        cleaned = re.sub(r"[ \t]+", " ", part).strip()
        code_m = re.match(r"^__CODE_BLOCK_(\d+)__$", cleaned)
        if code_m:
            idx = int(code_m.group(1))
            if 0 <= idx < len(code_blocks):
                lang, code_text = code_blocks[idx]
                code_tag = f"pre:{lang}" if lang else "pre"
                lines.append((code_tag, code_text[:8000]))
            continue
        cleaned = re.sub(r"\*{3,}", "**", cleaned)
        cleaned = re.sub(r"\*{2}\s+\*{2}", "", cleaned).strip()
        if is_too_short(cleaned, "p"):
            continue
        if re.search(r"(cookie|privacy|subscribe|newsletter|advertis|all rights reserved)", cleaned, re.I):
            continue
        lines.append(("p", cleaned[:1400]))
    return lines


def is_too_short(text: str, tag: str) -> bool:
    if tag not in {"p", "li", "blockquote"}:
        return False
    pure = re.sub(r"[*`_\[\]\(\)#>-]", "", text).strip()
    if not pure:
        return True
    has_cjk = bool(re.search(r"[\u4e00-\u9fff]", pure))
    min_len = 10 if has_cjk else 25
    return len(pure) < min_len
