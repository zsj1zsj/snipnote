import datetime as dt
import sqlite3
from datetime import date
from pathlib import Path
from typing import Optional

from core import Highlight, Annotation


def today() -> date:
    return dt.date.today()


def iso_date(value: date) -> str:
    return value.isoformat()


class HighlightRepository:
    """Repository for Highlight CRUD operations."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def add(self, text: str, source: str = "", author: str = "", location: str = "", tags: str = "") -> int:
        """Add a new highlight."""
        now = dt.datetime.now().isoformat(timespec="seconds")
        cursor = self.conn.execute(
            """
            INSERT INTO highlights (text, source, author, location, tags, created_at, next_review)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (text.strip(), source or "", author or "", location or "", tags or "", now, iso_date(today())),
        )
        self.conn.commit()
        return cursor.lastrowid

    def add_batch(self, items: list[tuple]) -> int:
        """Batch add highlights from values list."""
        if not items:
            return 0
        now = dt.datetime.now().isoformat(timespec="seconds")
        # Prepend created_at and next_review to each item
        values = [(text, source, author, location, tags, now, iso_date(today()))
                  for text, source, author, location, tags in items]
        self.conn.executemany(
            """
            INSERT INTO highlights (text, source, author, location, tags, created_at, next_review)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )
        self.conn.commit()
        return len(values)

    def get_by_id(self, highlight_id: int) -> Optional[Highlight]:
        """Get a highlight by ID."""
        row = self.conn.execute(
            "SELECT * FROM highlights WHERE id = ?", (highlight_id,)
        ).fetchone()
        if row:
            return Highlight(**dict(row))
        return None

    def list_all(self, limit: int = 20, due_only: bool = False) -> list[Highlight]:
        """List all highlights, optionally filtered by due date."""
        query = "SELECT * FROM highlights"
        params: list = []
        if due_only:
            query += " WHERE date(next_review) <= date(?)"
            params.append(iso_date(today()))
        query += " ORDER BY id DESC"
        if limit:
            query += " LIMIT ?"
            params.append(limit)

        rows = self.conn.execute(query, params).fetchall()
        return [Highlight(**dict(row)) for row in rows]

    def get_due(self, limit: int = 10) -> list[Highlight]:
        """Get highlights that are due for review."""
        rows = self.conn.execute(
            """
            SELECT * FROM highlights
            WHERE date(next_review) <= date(?)
            ORDER BY next_review ASC, id ASC
            LIMIT ?
            """,
            (iso_date(today()), limit),
        ).fetchall()
        return [Highlight(**dict(row)) for row in rows]

    def update_review(self, highlight_id: int, repetitions: int, interval_days: int,
                      efactor: float, next_review: date) -> None:
        """Update review scheduling data."""
        self.conn.execute(
            """
            UPDATE highlights
            SET repetitions = ?, interval_days = ?, efactor = ?,
                last_reviewed = ?, next_review = ?
            WHERE id = ?
            """,
            (
                repetitions,
                interval_days,
                efactor,
                dt.datetime.now().isoformat(timespec="seconds"),
                iso_date(next_review),
                highlight_id,
            ),
        )
        self.conn.commit()

    def update_favorite(self, highlight_id: int, favorite: int) -> None:
        """Toggle favorite status."""
        self.conn.execute(
            "UPDATE highlights SET favorite = ? WHERE id = ?",
            (favorite, highlight_id),
        )
        self.conn.commit()

    def update_is_read(self, highlight_id: int, is_read: int) -> None:
        """Toggle read status."""
        self.conn.execute(
            "UPDATE highlights SET is_read = ? WHERE id = ?",
            (is_read, highlight_id),
        )
        self.conn.commit()

    def update_summary(self, highlight_id: int, summary: str) -> None:
        """Update the summary of a highlight."""
        self.conn.execute(
            "UPDATE highlights SET summary = ? WHERE id = ?",
            (summary, highlight_id),
        )
        self.conn.commit()

    def delete(self, highlight_id: int) -> None:
        """Delete a highlight (annotations are cascade deleted)."""
        self.conn.execute("DELETE FROM highlights WHERE id = ?", (highlight_id,))
        self.conn.commit()

    def search(self, keyword: str = "", tag: str = "", read_filter: str = "unread", limit: int = 100) -> list[Highlight]:
        """Search highlights with filters."""
        query = "SELECT * FROM highlights WHERE 1=1"
        params: list = []

        if keyword:
            query += " AND text LIKE ?"
            params.append(f"%{keyword}%")

        if tag:
            query += " AND tags LIKE ?"
            params.append(f"%{tag}%")

        if read_filter == "unread":
            query += " AND is_read = 0"
        elif read_filter == "read":
            query += " AND is_read = 1"

        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        rows = self.conn.execute(query, params).fetchall()
        return [Highlight(**dict(row)) for row in rows]

    def get_favorites(self, keyword: str = "", tag: str = "", limit: int = 100) -> list[Highlight]:
        """Get favorite highlights."""
        query = "SELECT * FROM highlights WHERE favorite = 1"
        params: list = []

        if keyword:
            query += " AND text LIKE ?"
            params.append(f"%{keyword}%")

        if tag:
            query += " AND tags LIKE ?"
            params.append(f"%{tag}%")

        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        rows = self.conn.execute(query, params).fetchall()
        return [Highlight(**dict(row)) for row in rows]

    def url_exists(self, url: str) -> Optional[Highlight]:
        """Check if a URL already exists in highlights."""
        row = self.conn.execute(
            "SELECT * FROM highlights WHERE location = ?",
            (url,),
        ).fetchone()
        if row:
            return Highlight(**dict(row))
        return None


class AnnotationRepository:
    """Repository for Annotation CRUD operations."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def add(self, highlight_id: int, selected_text: str = "", note: str = "") -> int:
        """Add a new annotation."""
        now = dt.datetime.now().isoformat(timespec="seconds")
        cursor = self.conn.execute(
            """
            INSERT INTO annotations (highlight_id, selected_text, note, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (highlight_id, selected_text, note, now),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_by_highlight(self, highlight_id: int) -> list[Annotation]:
        """Get all annotations for a highlight."""
        rows = self.conn.execute(
            "SELECT * FROM annotations WHERE highlight_id = ? ORDER BY id",
            (highlight_id,),
        ).fetchall()
        return [Annotation(**dict(row)) for row in rows]

    def update_note(self, annotation_id: int, note: str) -> None:
        """Update annotation note."""
        self.conn.execute(
            "UPDATE annotations SET note = ? WHERE id = ?",
            (note, annotation_id),
        )
        self.conn.commit()

    def delete(self, annotation_id: int) -> None:
        """Delete an annotation."""
        self.conn.execute("DELETE FROM annotations WHERE id = ?", (annotation_id,))
        self.conn.commit()
