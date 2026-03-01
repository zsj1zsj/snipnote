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
    conn.commit()
    return conn
