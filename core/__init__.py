# Domain models
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional


@dataclass
class Highlight:
    """Core domain model for a highlight."""
    id: Optional[int] = None
    text: str = ""
    source: str = ""
    author: str = ""
    location: str = ""
    tags: str = ""
    summary: str = ""
    created_at: str = ""
    last_reviewed: Optional[str] = None
    next_review: str = ""
    favorite: int = 0
    is_read: int = 0
    repetitions: int = 0
    interval_days: int = 0
    efactor: float = 2.5


@dataclass
class Annotation:
    """Core domain model for an annotation (note/highlight on highlight)."""
    id: Optional[int] = None
    highlight_id: int = 0
    selected_text: str = ""
    note: str = ""
    created_at: str = ""


@dataclass
class ReviewSchedule:
    """Review scheduling data for SM-2 algorithm."""
    repetitions: int = 0
    interval_days: int = 0
    efactor: float = 2.5
    next_review: date = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.next_review is None:
            self.next_review = date.today()


@dataclass
class RssFeed:
    """An RSS/Atom feed subscription."""
    id: Optional[int] = None
    title: str = ""
    url: str = ""
    site_url: str = ""
    description: str = ""
    created_at: str = ""
    last_fetched_at: Optional[str] = None


@dataclass
class RssArticle:
    """An article from an RSS feed."""
    id: Optional[int] = None
    feed_id: int = 0
    title: str = ""
    url: str = ""
    author: str = ""
    summary: str = ""
    published_at: str = ""
    fetched_at: str = ""
    is_read: int = 0
    is_imported: int = 0
    highlight_id: Optional[int] = None


@dataclass
class PodcastShow:
    """A podcast show subscription."""
    id: Optional[int] = None
    title: str = ""
    url: str = ""
    site_url: str = ""
    description: str = ""
    image_url: str = ""
    author: str = ""
    language: str = ""
    created_at: str = ""
    last_fetched_at: Optional[str] = None


@dataclass
class PodcastEpisode:
    """A single episode from a podcast show."""
    id: Optional[int] = None
    show_id: int = 0
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
    published_at: str = ""
    fetched_at: str = ""
    is_listened: int = 0
    play_position: int = 0
