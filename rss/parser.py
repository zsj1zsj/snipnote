"""RSS/Atom feed parser using only the standard library."""

from dataclasses import dataclass, field
from datetime import datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

ATOM_NS = "{http://www.w3.org/2005/Atom}"
DC_NS = "{http://purl.org/dc/elements/1.1/}"
CONTENT_NS = "{http://purl.org/rss/1.0/modules/content/}"

USER_AGENT = (
    "Mozilla/5.0 (compatible; SnipNote/1.0; +https://github.com/zsj1zsj/snipnote)"
)


class _TagStripper(HTMLParser):
    """Strip HTML tags, keeping only text."""

    def __init__(self):
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str):
        self._parts.append(data)

    def get_text(self) -> str:
        return "".join(self._parts).strip()


def _strip_html(html: str) -> str:
    if not html:
        return ""
    s = _TagStripper()
    s.feed(html)
    return s.get_text()


def _parse_date(raw: str) -> str:
    """Best-effort date parsing to ISO format."""
    if not raw:
        return ""
    raw = raw.strip()
    # RFC 2822 (common in RSS 2.0)
    try:
        return parsedate_to_datetime(raw).isoformat()
    except Exception:
        pass
    # ISO 8601 variants (common in Atom)
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).isoformat()
        except ValueError:
            continue
    return raw


def _text(el: ET.Element | None, tag: str, ns: str = "") -> str:
    """Get text content of a child element."""
    child = el.find(f"{ns}{tag}") if el is not None else None
    return (child.text or "").strip() if child is not None else ""


@dataclass
class ArticleData:
    title: str = ""
    url: str = ""
    author: str = ""
    summary: str = ""
    published_at: str = ""


@dataclass
class FeedData:
    title: str = ""
    site_url: str = ""
    description: str = ""
    articles: list[ArticleData] = field(default_factory=list)


def _parse_rss2(root: ET.Element) -> FeedData:
    """Parse RSS 2.0 format."""
    channel = root.find("channel")
    if channel is None:
        channel = root  # some feeds omit <channel>

    feed = FeedData(
        title=_text(channel, "title"),
        site_url=_text(channel, "link"),
        description=_text(channel, "description"),
    )

    for item in channel.findall("item"):
        link = _text(item, "link")
        # Some feeds use <guid> as permalink
        if not link:
            guid_el = item.find("guid")
            if guid_el is not None and guid_el.get("isPermaLink", "true") != "false":
                link = (guid_el.text or "").strip()
        if not link:
            continue

        author = _text(item, "author") or _text(item, "creator", DC_NS)
        summary_raw = _text(item, "description")
        if not summary_raw:
            summary_raw = _text(item, "encoded", CONTENT_NS)

        feed.articles.append(ArticleData(
            title=_text(item, "title") or link,
            url=link,
            author=author,
            summary=_strip_html(summary_raw)[:500],
            published_at=_parse_date(_text(item, "pubDate")),
        ))

    return feed


def _parse_atom(root: ET.Element) -> FeedData:
    """Parse Atom format."""
    feed = FeedData(
        title=_text(root, "title", ATOM_NS),
        description=_text(root, "subtitle", ATOM_NS),
    )

    # site_url from <link rel="alternate">
    for link_el in root.findall(f"{ATOM_NS}link"):
        rel = link_el.get("rel", "alternate")
        if rel == "alternate":
            feed.site_url = link_el.get("href", "")
            break

    for entry in root.findall(f"{ATOM_NS}entry"):
        url = ""
        for link_el in entry.findall(f"{ATOM_NS}link"):
            rel = link_el.get("rel", "alternate")
            if rel == "alternate":
                url = link_el.get("href", "")
                break
        if not url:
            # fallback: first link
            first_link = entry.find(f"{ATOM_NS}link")
            if first_link is not None:
                url = first_link.get("href", "")
        if not url:
            continue

        author_el = entry.find(f"{ATOM_NS}author")
        author = _text(author_el, "name", ATOM_NS) if author_el is not None else ""

        summary_raw = _text(entry, "summary", ATOM_NS)
        if not summary_raw:
            summary_raw = _text(entry, "content", ATOM_NS)

        published = _text(entry, "published", ATOM_NS) or _text(entry, "updated", ATOM_NS)

        feed.articles.append(ArticleData(
            title=_text(entry, "title", ATOM_NS) or url,
            url=url,
            author=author,
            summary=_strip_html(summary_raw)[:500],
            published_at=_parse_date(published),
        ))

    return feed


def fetch_feed(feed_url: str, timeout: int = 15) -> FeedData:
    """Fetch and parse an RSS/Atom feed URL.

    Raises ValueError if the URL is not a valid feed.
    """
    req = Request(feed_url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=timeout) as resp:
        data = resp.read()

    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        raise ValueError(f"无法解析 XML: {e}")

    tag = root.tag.lower().split("}")[-1]  # strip namespace

    if tag == "rss" or tag == "rdf":
        return _parse_rss2(root)
    elif tag == "feed":
        return _parse_atom(root)
    else:
        raise ValueError(f"不支持的 feed 格式: {root.tag}")
