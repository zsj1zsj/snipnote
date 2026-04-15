import datetime as dt
import sqlite3
from typing import Optional

from core import PodcastShow, PodcastEpisode, PodcastBookmark


class PodcastShowRepository:
    """Repository for PodcastShow CRUD operations."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def add(self, title: str, url: str, site_url: str = "", description: str = "",
            image_url: str = "", author: str = "", language: str = "") -> int:
        now = dt.datetime.now().isoformat(timespec="seconds")
        cursor = self.conn.execute(
            """INSERT INTO podcast_shows (title, url, site_url, description, image_url, author, language, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (title, url, site_url, description, image_url, author, language, now),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_by_id(self, show_id: int) -> Optional[PodcastShow]:
        row = self.conn.execute("SELECT * FROM podcast_shows WHERE id = ?", (show_id,)).fetchone()
        return PodcastShow(**dict(row)) if row else None

    def get_by_url(self, url: str) -> Optional[PodcastShow]:
        row = self.conn.execute("SELECT * FROM podcast_shows WHERE url = ?", (url,)).fetchone()
        return PodcastShow(**dict(row)) if row else None

    def list_all(self) -> list[PodcastShow]:
        rows = self.conn.execute("SELECT * FROM podcast_shows ORDER BY id DESC").fetchall()
        return [PodcastShow(**dict(row)) for row in rows]

    def update_last_fetched(self, show_id: int) -> None:
        now = dt.datetime.now().isoformat(timespec="seconds")
        self.conn.execute("UPDATE podcast_shows SET last_fetched_at = ? WHERE id = ?", (now, show_id))
        self.conn.commit()

    def delete(self, show_id: int) -> None:
        self.conn.execute("DELETE FROM podcast_shows WHERE id = ?", (show_id,))
        self.conn.commit()


class PodcastEpisodeRepository:
    """Repository for PodcastEpisode CRUD operations."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def add(self, show_id: int, title: str, guid: str, audio_url: str,
            audio_type: str = "", audio_length: int = 0, description: str = "",
            image_url: str = "", author: str = "", duration: str = "",
            duration_seconds: int = 0, episode_number: Optional[int] = None,
            season_number: Optional[int] = None, episode_type: str = "",
            published_at: str = "") -> int:
        now = dt.datetime.now().isoformat(timespec="seconds")
        cursor = self.conn.execute(
            """INSERT INTO podcast_episodes
               (show_id, title, guid, audio_url, audio_type, audio_length, description,
                image_url, author, duration, duration_seconds, episode_number,
                season_number, published_at, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (show_id, title, guid, audio_url, audio_type, audio_length, description,
             image_url, author, duration, duration_seconds, episode_number,
             season_number, published_at, now),
        )
        self.conn.commit()
        return cursor.lastrowid

    def guid_exists(self, show_id: int, guid: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM podcast_episodes WHERE show_id = ? AND guid = ?",
            (show_id, guid),
        ).fetchone()
        return row is not None

    def get_by_id(self, episode_id: int) -> Optional[PodcastEpisode]:
        row = self.conn.execute(
            "SELECT * FROM podcast_episodes WHERE id = ?", (episode_id,)
        ).fetchone()
        return PodcastEpisode(**dict(row)) if row else None

    def list_by_show(self, show_id: int, limit: int = 50, offset: int = 0) -> list[PodcastEpisode]:
        rows = self.conn.execute(
            "SELECT * FROM podcast_episodes WHERE show_id = ? ORDER BY published_at DESC, id DESC LIMIT ? OFFSET ?",
            (show_id, limit, offset),
        ).fetchall()
        return [PodcastEpisode(**dict(row)) for row in rows]

    def list_all(self, show_id: int = 0, is_listened: str = "all",
                 limit: int = 50, offset: int = 0) -> list[PodcastEpisode]:
        query = "SELECT * FROM podcast_episodes WHERE 1=1"
        params: list = []
        if show_id:
            query += " AND show_id = ?"
            params.append(show_id)
        if is_listened == "unlistened":
            query += " AND is_listened = 0"
        elif is_listened == "listened":
            query += " AND is_listened = 1"
        query += " ORDER BY published_at DESC, id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = self.conn.execute(query, params).fetchall()
        return [PodcastEpisode(**dict(row)) for row in rows]

    def mark_listened(self, episode_id: int, is_listened: int = 1) -> None:
        self.conn.execute(
            "UPDATE podcast_episodes SET is_listened = ? WHERE id = ?",
            (is_listened, episode_id),
        )
        self.conn.commit()

    def update_ai_summary(self, episode_id: int, summary: str) -> None:
        self.conn.execute(
            "UPDATE podcast_episodes SET ai_summary = ? WHERE id = ?",
            (summary, episode_id),
        )
        self.conn.commit()

    def update_play_position(self, episode_id: int, position_seconds: int) -> None:
        self.conn.execute(
            "UPDATE podcast_episodes SET play_position = ? WHERE id = ?",
            (position_seconds, episode_id),
        )
        self.conn.commit()

    def count_by_show(self, show_id: int) -> dict:
        row = self.conn.execute(
            """SELECT COUNT(*) as total,
                      SUM(CASE WHEN is_listened = 0 THEN 1 ELSE 0 END) as unlistened
               FROM podcast_episodes WHERE show_id = ?""",
            (show_id,),
        ).fetchone()
        return {"total": row["total"] or 0, "unlistened": row["unlistened"] or 0}

    def get_global_stats(self) -> dict:
        """Return listening statistics across all shows."""
        row = self.conn.execute("""
            SELECT
                COUNT(*) as total_episodes,
                SUM(CASE WHEN is_listened = 1 THEN 1 ELSE 0 END) as listened_episodes,
                SUM(CASE WHEN is_listened = 1 THEN duration_seconds ELSE 0 END) as total_seconds_listened,
                SUM(CASE WHEN is_listened = 0 AND play_position > 0 THEN play_position ELSE 0 END) as in_progress_seconds
            FROM podcast_episodes
        """).fetchone()
        # This week (last 7 days)
        week_row = self.conn.execute("""
            SELECT COUNT(*) as this_week
            FROM podcast_episodes
            WHERE is_listened = 1
              AND fetched_at >= datetime('now', '-7 days')
        """).fetchone()
        total_sec = (row["total_seconds_listened"] or 0) + (row["in_progress_seconds"] or 0)
        return {
            "total_episodes": row["total_episodes"] or 0,
            "listened_episodes": row["listened_episodes"] or 0,
            "total_hours_listened": round(total_sec / 3600, 1),
            "this_week_listened": week_row["this_week"] or 0,
        }


class PodcastBookmarkRepository:
    """Repository for podcast bookmark (timestamp) operations."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def add(self, episode_id: int, position_seconds: int, note: str = "") -> int:
        now = dt.datetime.now().isoformat(timespec="seconds")
        cursor = self.conn.execute(
            "INSERT INTO podcast_bookmarks (episode_id, position_seconds, note, created_at) VALUES (?, ?, ?, ?)",
            (episode_id, position_seconds, note, now),
        )
        self.conn.commit()
        return cursor.lastrowid

    def list_by_episode(self, episode_id: int) -> list[PodcastBookmark]:
        rows = self.conn.execute(
            "SELECT * FROM podcast_bookmarks WHERE episode_id = ? ORDER BY position_seconds ASC",
            (episode_id,),
        ).fetchall()
        return [PodcastBookmark(**dict(row)) for row in rows]

    def update_note(self, bookmark_id: int, note: str) -> None:
        self.conn.execute("UPDATE podcast_bookmarks SET note = ? WHERE id = ?", (note, bookmark_id))
        self.conn.commit()

    def delete(self, bookmark_id: int) -> None:
        self.conn.execute("DELETE FROM podcast_bookmarks WHERE id = ?", (bookmark_id,))
        self.conn.commit()
