import sqlite3
from pathlib import Path


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS highlights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    source TEXT DEFAULT '',
    author TEXT DEFAULT '',
    location TEXT DEFAULT '',
    tags TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    last_reviewed TEXT,
    next_review TEXT NOT NULL,
    favorite INTEGER NOT NULL DEFAULT 0,
    is_read INTEGER NOT NULL DEFAULT 0,
    repetitions INTEGER NOT NULL DEFAULT 0,
    interval_days INTEGER NOT NULL DEFAULT 0,
    efactor REAL NOT NULL DEFAULT 2.5
);
CREATE TABLE IF NOT EXISTS annotations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    highlight_id INTEGER NOT NULL,
    selected_text TEXT DEFAULT '',
    note TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY(highlight_id) REFERENCES highlights(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_highlights_next_review ON highlights(next_review);
CREATE INDEX IF NOT EXISTS idx_annotations_highlight_id ON annotations(highlight_id);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    """Connect to the SQLite database and run migrations."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_SQL)
    # Backward-compatible migration for existing databases.
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(highlights)").fetchall()}
    if "favorite" not in cols:
        conn.execute("ALTER TABLE highlights ADD COLUMN favorite INTEGER NOT NULL DEFAULT 0")
    if "is_read" not in cols:
        conn.execute("ALTER TABLE highlights ADD COLUMN is_read INTEGER NOT NULL DEFAULT 0")
    if "summary" not in cols:
        conn.execute("ALTER TABLE highlights ADD COLUMN summary TEXT DEFAULT ''")

    # Podcast episodes migration
    ep_cols = {row["name"] for row in conn.execute("PRAGMA table_info(podcast_episodes)").fetchall()}
    if ep_cols and "ai_summary" not in ep_cols:
        conn.execute("ALTER TABLE podcast_episodes ADD COLUMN ai_summary TEXT DEFAULT ''")

    # Create daily_reports table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_date TEXT NOT NULL UNIQUE,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    # Create RSS tables
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS rss_feeds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            url TEXT NOT NULL UNIQUE,
            site_url TEXT DEFAULT '',
            description TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            last_fetched_at TEXT
        );
        CREATE TABLE IF NOT EXISTS rss_articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            feed_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            url TEXT NOT NULL UNIQUE,
            author TEXT DEFAULT '',
            summary TEXT DEFAULT '',
            published_at TEXT DEFAULT '',
            fetched_at TEXT NOT NULL,
            is_read INTEGER NOT NULL DEFAULT 0,
            is_imported INTEGER NOT NULL DEFAULT 0,
            highlight_id INTEGER,
            FOREIGN KEY(feed_id) REFERENCES rss_feeds(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_rss_articles_feed_id ON rss_articles(feed_id);
    """)
    # Create Podcast tables
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS podcast_shows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            url TEXT NOT NULL UNIQUE,
            site_url TEXT DEFAULT '',
            description TEXT DEFAULT '',
            image_url TEXT DEFAULT '',
            author TEXT DEFAULT '',
            language TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            last_fetched_at TEXT
        );
        CREATE TABLE IF NOT EXISTS podcast_episodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            show_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            guid TEXT NOT NULL,
            audio_url TEXT NOT NULL,
            audio_type TEXT DEFAULT '',
            audio_length INTEGER DEFAULT 0,
            description TEXT DEFAULT '',
            image_url TEXT DEFAULT '',
            author TEXT DEFAULT '',
            duration TEXT DEFAULT '',
            duration_seconds INTEGER DEFAULT 0,
            episode_number INTEGER,
            season_number INTEGER,
            published_at TEXT DEFAULT '',
            fetched_at TEXT NOT NULL,
            is_listened INTEGER NOT NULL DEFAULT 0,
            play_position INTEGER NOT NULL DEFAULT 0,
            ai_summary TEXT DEFAULT '',
            FOREIGN KEY(show_id) REFERENCES podcast_shows(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_podcast_episodes_show_id ON podcast_episodes(show_id);
        CREATE INDEX IF NOT EXISTS idx_podcast_episodes_guid ON podcast_episodes(guid);
        CREATE TABLE IF NOT EXISTS podcast_bookmarks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            episode_id INTEGER NOT NULL,
            position_seconds INTEGER NOT NULL,
            note TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY(episode_id) REFERENCES podcast_episodes(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_podcast_bookmarks_episode_id ON podcast_bookmarks(episode_id);
    """)
    # RSS feeds migration: add category, error_count, last_error columns
    rss_cols = {row["name"] for row in conn.execute("PRAGMA table_info(rss_feeds)").fetchall()}
    if "category" not in rss_cols:
        conn.execute("ALTER TABLE rss_feeds ADD COLUMN category TEXT DEFAULT ''")
    if "error_count" not in rss_cols:
        conn.execute("ALTER TABLE rss_feeds ADD COLUMN error_count INTEGER NOT NULL DEFAULT 0")
    if "last_error" not in rss_cols:
        conn.execute("ALTER TABLE rss_feeds ADD COLUMN last_error TEXT DEFAULT ''")

    conn.commit()
    return conn
