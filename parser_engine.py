import html as html_std
import json
import os
import re
from typing import Any
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urljoin, urlparse, urlsplit
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass
class ParseOutput:
    title: str
    markdown: str


DEFAULT_PARSER_RULES: dict[str, Any] = {
    "blocked_script_sources": [
        "https://wall-ui-cdn.p.aws.economist.com/latest/wall-ui.js",
        "https://cdn.eu.amplitude.com/script/f3474234bacde7a4dcbceaf2e21dfbad.experiment.js",
    ],
    "rules": {
        "solidot": {
            "domains": ["solidot.org"],
            "primary_html_patterns": [
                r"(?is)<div[^>]*class=[\"'][^\"']*p_mainnew[^\"']*[\"'][^>]*>(.*?)</div>",
                r"(?is)<div[^>]*class=[\"'][^\"']*content[^\"']*[\"'][^>]*>(.*?)</div>",
                r"(?is)<article[^>]*>(.*?)</article>",
            ],
            "drop_patterns": [
                r"发表于\s+\d{4}年\d{2}月\d{2}日",
                r"新浪微博分享",
                r"本站提到的所有注册商标",
                r"京ICP",
                r"备案号",
                r"举报电话",
                r"举报邮箱",
                r"www\.solidot\.org\s+-",
            ],
            "image_drop_keywords": ["logo", "avatar", "icon", "wechat", "weibo", "rss"],
            "max_images": 2,
        },
        "ifanr": {
            "domains": ["ifanr.com"],
            "primary_html_patterns": [
                r"(?is)<article[^>]*>(.*?)</article>",
                r"(?is)<div[^>]*class=[\"'][^\"']*(?:post-content|article-content|single-content|c-single-content)[^\"']*[\"'][^>]*>(.*?)</div>",
                r"(?is)<section[^>]*class=[\"'][^\"']*(?:post-content|article-content|single-content)[^\"']*[\"'][^>]*>(.*?)</section>",
            ],
            "drop_patterns": [
                r"^\s*登录\s*$",
                r"^\s*注册\s*$",
                r"媒体品牌",
                r"制糖工厂",
                r"扫描小程序码",
                r"为您查询到.*篇文章",
                r"上一篇",
                r"小时前",
                r"爱范儿 App",
                r"爱范儿,?让未来触手可及",
                r"关注爱范儿微信号",
                r"关注玩物志微信号",
                r"小程序开发快人一步",
                r"微信新商业服务平台",
                r"京ICP",
                r"备案号",
                r"举报电话",
                r"www\.ifanr\.com\s+-",
                r"^\s*图片(\s*\d+)?\s*$",
            ],
            "image_drop_keywords": ["logo", "icon", "avatar", "wechat", "weibo", "favicon", "qrcode"],
            "max_images": 6,
        },
        "playno1": {
            "domains": ["playno1.com"],
            "primary_html_patterns": [
                r"(?is)<div[^>]*id=[\"']?article_content[\"']?[^>]*>(.*?)</div>",
                r"(?is)<td[^>]*id=[\"']?article_content[\"']?[^>]*>(.*?)</td>",
                r"(?is)<div[^>]*class=[\"'][^\"']*(?:article-content|article|content|t_f)[^\"']*[\"'][^>]*>(.*?)</div>",
                r"(?is)<article[^>]*>(.*?)</article>",
            ],
            "drop_patterns": [
                r"^\s*登录\s*$",
                r"^\s*注册\s*$",
                r"^\s*返回首页\s*$",
                r"^\s*免责声明\s*$",
                r"^\s*上一篇\s*$",
                r"^\s*下一篇\s*$",
                r"^\s*相关阅读\s*$",
                r"Powered by Discuz",
                r"Copyright",
                r"广告",
                r"本站",
                r"forbid\.htm",
                r"请先.*验证",
            ],
            "request_headers": {
                "Referer": "http://www.playno1.com/forbid.htm",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            },
            "image_drop_keywords": ["logo", "icon", "avatar", "ads", "banner", "qrcode"],
            "max_images": 12,
        },
        "blogjava": {
            "domains": ["blogjava.net"],
            "primary_html_patterns": [
                r"(?is)<div[^>]*id=[\"']?(?:cnblogs_post_body|blog_post_body|BlogPostContent|post_body|postBody)[\"']?[^>]*>(.*?)</div>",
                r"(?is)<div[^>]*class=[\"'][^\"']*(?:postCon|postBody|post-body|entry-content|article-content)[^\"']*[\"'][^>]*>(.*?)</div>",
                r"(?is)<div[^>]*class=[\"'][^\"']*post[^\"']*[\"'][^>]*>.*?<div[^>]*class=[\"'][^\"']*(?:postBody|postCon|entry)[^\"']*[\"'][^>]*>(.*?)</div>.*?</div>",
            ],
            "drop_exact": [
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
            ],
            "drop_patterns": [
                r"\(rss\)\s*$",
                r"^\d{4}年\d{1,2}月\s*\(\d+\)\s*$",
                r"^www\.blogjava\.net\s+-",
                r"^paulwong\s*$",
                r"聚合",
                r"^\s*图片(\s*\d+)?\s*$",
            ],
            "image_drop_keywords": ["logo", "avatar", "icon", "rss", "banner", "ads", "qrcode"],
            "max_images": 3,
        },
        "yahoo_news_jp": {
            "domains": ["news.yahoo.co.jp"],
            "primary_html_patterns": [
                r"(?is)<article[^>]*>(.*?)</article>",
                r"(?is)<div[^>]*class=[\"'][^\"']*(?:article|Article|articleBody|mainContents|contentsBody)[^\"']*[\"'][^>]*>(.*?)</div>",
                r"(?is)<main[^>]*>(.*?)</main>",
            ],
            "drop_patterns": [
                r"^\s*\d+\s*コメント",
                r"^\s*\d{1,2}/\d{1,2}\([^)]+\)\s*\d{1,2}:\d{2}\s*配信\s*$",
                r"^最終更新[:：]",
                r"アクセスランキング",
                r"Yahoo!ニュース オリジナル",
                r"雑誌アクセスランキング",
                r"^\[\]\(https?://(x\.com|www\.facebook\.com)/",
                r"^\[日テレNEWS NNN\]\(/media/",
                r"^\*{6,}",
                r"^\s*画像\s*",
                r"^【画像】",
                r"^news\.yahoo\.co\.jp\s+-",
                r"^日テレNEWS NNN$",
            ],
            "stop_patterns": [
                r"アクセスランキング",
                r"Yahoo!ニュース オリジナル",
                r"雑誌アクセスランキング",
                r"関連記事",
            ],
            "image_drop_keywords": ["icon", "logo", "sprite", "avatar", "banner", "thumbnail"],
            "max_images": 1,
        },
    },
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


def get_rule_config(rule_key: str) -> dict[str, Any]:
    rules = PARSER_RULES.get("rules", {})
    if isinstance(rules, dict):
        cfg = rules.get(rule_key, {})
        if isinstance(cfg, dict):
            return cfg
    return {}


def get_rule_list(rule_key: str, key: str, default: list[str] | tuple[str, ...] = ()) -> list[str]:
    value = get_rule_config(rule_key).get(key, default)
    if isinstance(value, list):
        return [str(x) for x in value]
    if isinstance(value, tuple):
        return [str(x) for x in value]
    return [str(x) for x in default]


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


class SolidotRule(BaseSiteRule):
    RULE_KEY = "solidot"

    def __init__(self):
        domains = tuple(get_rule_list(self.RULE_KEY, "domains", ("solidot.org",)))
        super().__init__(domains)

    def primary_blocks(self, raw_html: str) -> list[tuple[str, str]]:
        patterns = get_rule_list(self.RULE_KEY, "primary_html_patterns")
        for pat in patterns:
            m = re.search(pat, raw_html)
            if m:
                blocks = fallback_extract_blocks(m.group(1))
                if blocks:
                    return blocks
        return []

    def clean_blocks(self, blocks: list[tuple[str, str]]) -> list[tuple[str, str]]:
        noise_patterns = get_rule_list(self.RULE_KEY, "drop_patterns")
        result: list[tuple[str, str]] = []
        for tag, text in blocks:
            if not text:
                continue
            if any(re.search(pat, text, re.I) for pat in noise_patterns):
                continue
            cleaned = re.sub(r"\s+", " ", text).strip()
            if is_too_short(cleaned, tag):
                continue
            result.append((tag, cleaned))
        return result

    def clean_images(self, images: list[str]) -> list[str]:
        keywords = [k.lower() for k in get_rule_list(self.RULE_KEY, "image_drop_keywords")]
        max_images = int(get_rule_config(self.RULE_KEY).get("max_images", 2))
        filtered = []
        for u in images:
            lower = u.lower()
            if any(k in lower for k in keywords):
                continue
            filtered.append(u)
        return filtered[:max_images]


class IfanrRule(BaseSiteRule):
    RULE_KEY = "ifanr"

    def __init__(self):
        domains = tuple(get_rule_list(self.RULE_KEY, "domains", ("ifanr.com",)))
        super().__init__(domains)

    def primary_blocks(self, raw_html: str) -> list[tuple[str, str]]:
        patterns = get_rule_list(self.RULE_KEY, "primary_html_patterns")
        for pat in patterns:
            m = re.search(pat, raw_html)
            if m:
                blocks = fallback_extract_blocks(m.group(1))
                if blocks:
                    return blocks
        return []

    def clean_blocks(self, blocks: list[tuple[str, str]]) -> list[tuple[str, str]]:
        noise_patterns = get_rule_list(self.RULE_KEY, "drop_patterns")
        result: list[tuple[str, str]] = []
        for tag, text in blocks:
            if not text:
                continue
            cleaned = re.sub(r"\s+", " ", text).strip()
            if any(re.search(pat, cleaned, re.I) for pat in noise_patterns):
                continue
            if is_too_short(cleaned, tag):
                continue
            result.append((tag, cleaned))
        return result

    def clean_images(self, images: list[str]) -> list[str]:
        keywords = [k.lower() for k in get_rule_list(self.RULE_KEY, "image_drop_keywords")]
        max_images = int(get_rule_config(self.RULE_KEY).get("max_images", 6))
        filtered = []
        for u in images:
            lower = u.lower()
            if any(k in lower for k in keywords):
                continue
            filtered.append(u)
        return filtered[:max_images]


class Playno1Rule(BaseSiteRule):
    RULE_KEY = "playno1"

    def __init__(self):
        domains = tuple(get_rule_list(self.RULE_KEY, "domains", ("playno1.com",)))
        super().__init__(domains)

    def request_headers(self, url: str, referer: str) -> list[dict[str, str]]:
        cookie = os.environ.get("PLAYNO1_COOKIE", "").strip()
        headers = dict(get_rule_config(self.RULE_KEY).get("request_headers", {}))
        if "Referer" not in headers:
            headers["Referer"] = "http://www.playno1.com/forbid.htm"
        if cookie:
            headers["Cookie"] = cookie
        return [headers]

    def primary_blocks(self, raw_html: str) -> list[tuple[str, str]]:
        patterns = get_rule_list(self.RULE_KEY, "primary_html_patterns")
        for pat in patterns:
            m = re.search(pat, raw_html)
            if m:
                blocks = fallback_extract_blocks(m.group(1))
                if blocks:
                    return blocks
        return []

    def clean_blocks(self, blocks: list[tuple[str, str]]) -> list[tuple[str, str]]:
        noise_patterns = get_rule_list(self.RULE_KEY, "drop_patterns")
        result: list[tuple[str, str]] = []
        for tag, text in blocks:
            if not text:
                continue
            cleaned = re.sub(r"\s+", " ", text).strip()
            if any(re.search(pat, cleaned, re.I) for pat in noise_patterns):
                continue
            if is_too_short(cleaned, tag):
                continue
            result.append((tag, cleaned))
        return result

    def clean_images(self, images: list[str]) -> list[str]:
        keywords = [k.lower() for k in get_rule_list(self.RULE_KEY, "image_drop_keywords")]
        max_images = int(get_rule_config(self.RULE_KEY).get("max_images", 12))
        filtered = []
        for u in images:
            lower = u.lower()
            if any(k in lower for k in keywords):
                continue
            filtered.append(u)
        return filtered[:max_images]


class BlogJavaRule(BaseSiteRule):
    RULE_KEY = "blogjava"

    def __init__(self):
        domains = tuple(get_rule_list(self.RULE_KEY, "domains", ("blogjava.net",)))
        super().__init__(domains)

    def primary_blocks(self, raw_html: str) -> list[tuple[str, str]]:
        patterns = get_rule_list(self.RULE_KEY, "primary_html_patterns")
        for pat in patterns:
            m = re.search(pat, raw_html)
            if m:
                blocks = fallback_extract_blocks(m.group(1))
                if blocks:
                    return blocks
        return []

    def clean_blocks(self, blocks: list[tuple[str, str]]) -> list[tuple[str, str]]:
        noise_exact = set(get_rule_list(self.RULE_KEY, "drop_exact"))
        noise_patterns = get_rule_list(self.RULE_KEY, "drop_patterns")
        stage1: list[tuple[str, str]] = []
        for tag, text in blocks:
            if not text:
                continue
            cleaned = re.sub(r"\s+", " ", text).strip()
            lower = cleaned.lower()
            if cleaned in noise_exact:
                continue
            if any(re.search(pat, cleaned, re.I) for pat in noise_patterns):
                continue
            if "(rss)" in lower:
                continue
            # Typical sidebar taxonomy line like: SPRING(44) (rss)
            if re.match(r"^[\w\u4e00-\u9fff\-/\s\(\)]+\(rss\)\s*$", cleaned, re.I):
                continue
            if re.match(r"^[A-Z][A-Z0-9\-\s/]{2,}\(\d+\)$", cleaned):
                continue
            if re.match(r"^\d{4}年\d{1,2}月\s*\(\d+\)$", cleaned):
                continue
            if is_too_short(cleaned, tag):
                continue
            stage1.append((tag, cleaned))

        # Fallback semantic filter: drop sidebar-like tag names and keep sentence-like article text.
        if not stage1:
            return []

        def looks_like_sentence(s: str) -> bool:
            if len(s) < 20:
                return False
            if re.search(r"[。！？；：，,.!?;:]", s):
                return True
            cjk_count = len(re.findall(r"[\u4e00-\u9fff]", s))
            return cjk_count >= 8 and len(s) >= 28

        result: list[tuple[str, str]] = []
        for tag, cleaned in stage1:
            if looks_like_sentence(cleaned):
                result.append((tag, cleaned))
                continue
            # Keep short headings if they look like article section titles.
            if tag in {"h1", "h2", "h3"} and 6 <= len(cleaned) <= 80:
                if not re.search(r"(blogjava|paulwong|rss|首页|联系|管理)", cleaned, re.I):
                    result.append((tag, cleaned))
                continue
            # Drop category-like uppercase/tag lines.
            if re.match(r"^[A-Z0-9\-\s/]+\(?\d*\)?$", cleaned):
                continue
        # If still looks polluted by sidebar keywords, keep only sentence-like lines.
        pollution_hits = sum(
            1 for _, t in result if re.search(r"(我的随笔|我的评论|给我留言|查看公开留言|查看私人留言|最新评论)", t)
        )
        if pollution_hits > 0:
            result = [(tag, t) for tag, t in result if looks_like_sentence(t)]
        return result

    def clean_images(self, images: list[str]) -> list[str]:
        keywords = [k.lower() for k in get_rule_list(self.RULE_KEY, "image_drop_keywords")]
        max_images = int(get_rule_config(self.RULE_KEY).get("max_images", 3))
        filtered = []
        for u in images:
            lower = u.lower()
            if any(k in lower for k in keywords):
                continue
            filtered.append(u)
        return filtered[:max_images]


class YahooNewsJPRule(BaseSiteRule):
    RULE_KEY = "yahoo_news_jp"

    def __init__(self):
        domains = tuple(get_rule_list(self.RULE_KEY, "domains", ("news.yahoo.co.jp",)))
        super().__init__(domains)

    def primary_blocks(self, raw_html: str) -> list[tuple[str, str]]:
        state_blocks = extract_yahoo_preloaded_blocks(raw_html)
        if state_blocks:
            return state_blocks

        patterns = get_rule_list(self.RULE_KEY, "primary_html_patterns")
        for pat in patterns:
            m = re.search(pat, raw_html)
            if m:
                blocks = fallback_extract_blocks(m.group(1))
                if blocks:
                    return blocks
        return []

    def clean_blocks(self, blocks: list[tuple[str, str]]) -> list[tuple[str, str]]:
        drop_patterns = get_rule_list(self.RULE_KEY, "drop_patterns")
        stop_patterns = get_rule_list(self.RULE_KEY, "stop_patterns")
        result: list[tuple[str, str]] = []
        body_like_count = 0
        headline_run = 0

        def is_headline_like(s: str) -> bool:
            # Short single-line titles (often related-news list items).
            if len(s) < 18 or len(s) > 120:
                return False
            if re.search(r"[。！？]", s):
                return False
            if re.search(r"(配信|最終更新|コメント|アクセスランキング)", s):
                return False
            return True

        for tag, text in blocks:
            cleaned = re.sub(r"\s+", " ", (text or "")).strip()
            if not cleaned:
                continue
            if any(re.search(pat, cleaned, re.I) for pat in stop_patterns):
                break
            if any(re.search(pat, cleaned, re.I) for pat in drop_patterns):
                continue
            if re.match(r"^\d+\s", cleaned) and "ランキング" in cleaned:
                break
            if is_too_short(cleaned, tag):
                continue

            if re.search(r"[。！？]", cleaned):
                body_like_count += 1
                headline_run = 0
            elif is_headline_like(cleaned):
                headline_run += 1
                # After core body starts, two consecutive headline-like lines imply related list.
                if body_like_count >= 3 and headline_run >= 2:
                    break
            else:
                headline_run = 0

            result.append((tag, cleaned))
        return result

    def clean_images(self, images: list[str]) -> list[str]:
        keywords = [k.lower() for k in get_rule_list(self.RULE_KEY, "image_drop_keywords")]
        max_images = int(get_rule_config(self.RULE_KEY).get("max_images", 1))
        filtered = []
        for u in images:
            lower = u.lower()
            if any(k in lower for k in keywords):
                continue
            # Prefer canonical Yahoo article image domains.
            if "newsatcl-pctr.c.yimg.jp" in lower or "news-pctr.c.yimg.jp" in lower:
                filtered.append(u)
                continue
            filtered.append(u)
        return filtered[:max_images]


RULES: list[BaseSiteRule] = [SolidotRule(), IfanrRule(), Playno1Rule(), BlogJavaRule(), YahooNewsJPRule()]


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


def fetch_html_with_retry(url: str, timeout: int = 10) -> tuple[str, bytes]:
    parsed = urlparse(url)
    host = parsed.netloc
    referer = f"{parsed.scheme}://{host}/" if parsed.scheme and host else "https://www.google.com/"
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


def parse_link_to_markdown(url: str, timeout: int = 10) -> ParseOutput:
    fetched_url, raw = fetch_html_with_retry(url, timeout=timeout)
    text = raw.decode("utf-8", errors="replace")
    text = strip_blocked_scripts(text)

    parsed = urlparse(fetched_url)
    host = parsed.netloc
    rule = choose_rule(host)

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
        # Prefer explicit failure over storing obvious sidebar noise.
        if isinstance(rule, BlogJavaRule) and len(chosen_blocks) < 2:
            raise ValueError("未识别到 BlogJava 正文容器，请尝试手动粘贴正文或提供页面源码片段。")

    # Host-level hard filter: prevent template/sidebar pollution from being stored.
    if "blogjava.net" in host.lower():
        chosen_blocks = hard_filter_blogjava_blocks(chosen_blocks)
        if len(chosen_blocks) < 2:
            raise ValueError("BlogJava 页面仍被模板干扰，未提取到有效正文。请提供页面源码以完成精准规则。")

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
