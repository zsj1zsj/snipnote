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
