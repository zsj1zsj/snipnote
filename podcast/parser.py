"""Podcast RSS parser with iTunes namespace support. Standard library only."""

from dataclasses import dataclass, field
from datetime import datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Optional
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

ITUNES_NS = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"
GOOGLEPLAY_NS = "{http://www.google.com/schemas/play-podcasts/1.0}"
DC_NS = "{http://purl.org/dc/elements/1.1/}"

USER_AGENT = (
    "Mozilla/5.0 (compatible; SnipNote/1.0; +https://github.com/zsj1zsj/snipnote)"
)


class _TagStripper(HTMLParser):
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
    if not raw:
        return ""
    raw = raw.strip()
    try:
        return parsedate_to_datetime(raw).isoformat()
    except Exception:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).isoformat()
        except ValueError:
            continue
    return raw


def _text(el: Optional[ET.Element], tag: str, ns: str = "") -> str:
    child = el.find(f"{ns}{tag}") if el is not None else None
    return (child.text or "").strip() if child is not None else ""


def _parse_duration(raw: str) -> int:
    """Convert itunes:duration string to total seconds."""
    if not raw:
        return 0
    raw = raw.strip()
    if raw.isdigit():
        return int(raw)
    parts = raw.split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
    except ValueError:
        pass
    return 0


def _itunes(el: Optional[ET.Element], tag: str) -> str:
    return _text(el, tag, ITUNES_NS)


def _itunes_int(el: Optional[ET.Element], tag: str) -> Optional[int]:
    val = _itunes(el, tag)
    if val and val.isdigit():
        return int(val)
    return None


@dataclass
class EpisodeData:
    title: str = ""
    guid: str = ""
    audio_url: str = ""
    audio_type: str = ""
    audio_length: int = 0
    description: str = ""
    image_url: str = ""
    author: str = ""
    duration: str = ""
    duration_seconds: int = 0
    episode_number: Optional[int] = None
    season_number: Optional[int] = None
    episode_type: str = ""
    published_at: str = ""


@dataclass
class ShowData:
    title: str = ""
    site_url: str = ""
    description: str = ""
    image_url: str = ""
    author: str = ""
    language: str = ""
    episodes: list[EpisodeData] = field(default_factory=list)


def fetch_podcast(feed_url: str, timeout: int = 15) -> ShowData:
    """Fetch and parse a Podcast RSS feed URL.

    Raises ValueError if the URL is not a valid podcast feed (no audio enclosures found).
    """
    req = Request(feed_url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=timeout) as resp:
        data = resp.read()

    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        raise ValueError(f"无法解析 XML: {e}")

    tag = root.tag.lower().split("}")[-1]
    if tag not in ("rss", "rdf"):
        raise ValueError(f"Podcast feed 必须是 RSS 2.0 格式，当前格式: {root.tag}")

    channel = root.find("channel")
    if channel is None:
        channel = root

    # Show-level itunes:image
    show_image = ""
    image_el = channel.find(f"{ITUNES_NS}image")
    if image_el is not None:
        show_image = image_el.get("href", "") or _text(image_el, "href")
    # Fallback to <image><url>
    if not show_image:
        img_tag = channel.find("image")
        if img_tag is not None:
            show_image = _text(img_tag, "url")

    show = ShowData(
        title=_text(channel, "title"),
        site_url=_text(channel, "link"),
        description=_strip_html(_itunes(channel, "summary") or _text(channel, "description")),
        image_url=show_image,
        author=_itunes(channel, "author") or _itunes(channel, "owner"),
        language=_text(channel, "language"),
    )

    for item in channel.findall("item"):
        # Only process items with audio enclosure
        enclosure = item.find("enclosure")
        if enclosure is None:
            continue
        audio_type = enclosure.get("type", "")
        if not audio_type.startswith("audio/"):
            continue

        audio_url = enclosure.get("url", "").strip()
        if not audio_url:
            continue

        audio_length = 0
        try:
            audio_length = int(enclosure.get("length", 0))
        except (ValueError, TypeError):
            pass

        # guid
        guid_el = item.find("guid")
        guid = (guid_el.text or "").strip() if guid_el is not None else audio_url

        # Episode-level image
        ep_image = ""
        ep_image_el = item.find(f"{ITUNES_NS}image")
        if ep_image_el is not None:
            ep_image = ep_image_el.get("href", "")

        # Description: prefer itunes:summary, fallback to description
        description_raw = _itunes(item, "summary") or _text(item, "description")

        duration_raw = _itunes(item, "duration")

        show.episodes.append(EpisodeData(
            title=_text(item, "title") or audio_url,
            guid=guid,
            audio_url=audio_url,
            audio_type=audio_type,
            audio_length=audio_length,
            description=_strip_html(description_raw)[:1000],
            image_url=ep_image,
            author=_itunes(item, "author") or _text(item, f"{DC_NS}creator"),
            duration=duration_raw,
            duration_seconds=_parse_duration(duration_raw),
            episode_number=_itunes_int(item, "episode"),
            season_number=_itunes_int(item, "season"),
            episode_type=_itunes(item, "episodeType"),
            published_at=_parse_date(_text(item, "pubDate")),
        ))

    if not show.episodes:
        raise ValueError("该 Feed 中未找到音频内容（非 Podcast 类 RSS）")

    return show
