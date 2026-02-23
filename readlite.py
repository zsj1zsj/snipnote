#!/usr/bin/env python3
import argparse
import csv
import datetime as dt
import json
import random
import sqlite3
from pathlib import Path


DEFAULT_DB = Path("data/readlite.db")


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


def today() -> dt.date:
    return dt.date.today()


def iso_date(value: dt.date) -> str:
    return value.isoformat()


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_SQL)
    return conn


def add_highlight(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    now = dt.datetime.now().isoformat(timespec="seconds")
    conn.execute(
        """
        INSERT INTO highlights (text, source, author, location, tags, created_at, next_review)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            args.text.strip(),
            args.source or "",
            args.author or "",
            args.location or "",
            args.tags or "",
            now,
            iso_date(today()),
        ),
    )
    conn.commit()
    print("Added 1 highlight.")


def _parse_import_file(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if path.suffix.lower() == ".jsonl":
        rows = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        raise ValueError("JSON file must be a list of objects.")
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))
    raise ValueError("Unsupported format. Use .jsonl, .json, or .csv")


def import_highlights(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    rows = _parse_import_file(Path(args.file))
    now = dt.datetime.now().isoformat(timespec="seconds")
    values = []
    for row in rows:
        text = (row.get("text") or "").strip()
        if not text:
            continue
        values.append(
            (
                text,
                row.get("source", ""),
                row.get("author", ""),
                row.get("location", ""),
                row.get("tags", ""),
                now,
                iso_date(today()),
            )
        )
    if not values:
        print("No valid highlights found.")
        return
    conn.executemany(
        """
        INSERT INTO highlights (text, source, author, location, tags, created_at, next_review)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        values,
    )
    conn.commit()
    print(f"Imported {len(values)} highlights.")


def list_highlights(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    query = """
        SELECT id, text, source, author, tags, next_review, repetitions
        FROM highlights
    """
    params: list = []
    if args.due:
        query += " WHERE date(next_review) <= date(?)"
        params.append(iso_date(today()))
    query += " ORDER BY id DESC"
    if args.limit:
        query += " LIMIT ?"
        params.append(args.limit)

    rows = conn.execute(query, params).fetchall()
    if not rows:
        print("No highlights.")
        return
    for row in rows:
        source = f"{row['author']} - {row['source']}".strip(" -")
        tags = f" #{row['tags'].replace(',', ' #')}" if row["tags"] else ""
        print(
            f"[{row['id']}] (due {row['next_review']}) reps={row['repetitions']}\n"
            f"{row['text']}\n"
            f"{source}{tags}\n"
        )


def _next_schedule(repetitions: int, interval_days: int, efactor: float, quality: int) -> tuple[int, int, float]:
    if quality < 3:
        repetitions = 0
        interval_days = 1
    else:
        if repetitions == 0:
            interval_days = 1
        elif repetitions == 1:
            interval_days = 6
        else:
            interval_days = max(1, round(interval_days * efactor))
        repetitions += 1

    efactor = efactor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    efactor = max(1.3, efactor)
    return repetitions, interval_days, efactor


def _due_items(conn: sqlite3.Connection, limit: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT id, text, source, author, repetitions, interval_days, efactor, next_review
        FROM highlights
        WHERE date(next_review) <= date(?)
        ORDER BY next_review ASC, id ASC
        LIMIT ?
        """,
        (iso_date(today()), limit),
    ).fetchall()


def review(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    rows = _due_items(conn, args.limit)
    if not rows:
        print("No due highlights today.")
        return

    reviewed = 0
    for row in rows:
        print(f"\n[{row['id']}] {row['author']} - {row['source']}".strip(" -"))
        print(row["text"])
        if args.quality is None:
            raw = input("Score recall 0-5 (q to quit): ").strip().lower()
            if raw == "q":
                break
            if raw not in {"0", "1", "2", "3", "4", "5"}:
                print("Invalid score. Skipping.")
                continue
            quality = int(raw)
        else:
            quality = args.quality

        reps, interval, ef = _next_schedule(
            row["repetitions"], row["interval_days"], row["efactor"], quality
        )
        next_review = today() + dt.timedelta(days=interval)
        conn.execute(
            """
            UPDATE highlights
            SET repetitions = ?, interval_days = ?, efactor = ?,
                last_reviewed = ?, next_review = ?
            WHERE id = ?
            """,
            (
                reps,
                interval,
                ef,
                dt.datetime.now().isoformat(timespec="seconds"),
                iso_date(next_review),
                row["id"],
            ),
        )
        reviewed += 1
        if args.quality is not None:
            print(f"Scored {quality}, next review on {iso_date(next_review)}")
    conn.commit()
    print(f"\nReviewed {reviewed} highlight(s).")


def daily(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    due = conn.execute(
        "SELECT id, text, source, author FROM highlights WHERE date(next_review) <= date(?) ORDER BY next_review LIMIT ?",
        (iso_date(today()), args.due_limit),
    ).fetchall()
    resurfaced = conn.execute(
        "SELECT id, text, source, author FROM highlights ORDER BY RANDOM() LIMIT ?",
        (args.random_limit,),
    ).fetchall()
    date_str = iso_date(today())
    print(f"# Daily Review ({date_str})\n")
    print("## Due Today")
    if not due:
        print("- None")
    for row in due:
        meta = f"{row['author']} - {row['source']}".strip(" -")
        print(f"- [{row['id']}] {row['text']} ({meta})")
    print("\n## Random Resurface")
    if not resurfaced:
        print("- None")
    for row in resurfaced:
        meta = f"{row['author']} - {row['source']}".strip(" -")
        print(f"- [{row['id']}] {row['text']} ({meta})")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Readlite: a lightweight Readwise alternative.")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="SQLite database path.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="Add one highlight.")
    p_add.add_argument("--text", required=True, help="Highlight content.")
    p_add.add_argument("--source", default="", help="Book/article source.")
    p_add.add_argument("--author", default="", help="Author.")
    p_add.add_argument("--location", default="", help="Page/chapter/url location.")
    p_add.add_argument("--tags", default="", help="Comma-separated tags.")
    p_add.set_defaults(func=add_highlight)

    p_import = sub.add_parser("import", help="Import highlights from json/jsonl/csv.")
    p_import.add_argument("--file", required=True, help="Input file path.")
    p_import.set_defaults(func=import_highlights)

    p_list = sub.add_parser("list", help="List highlights.")
    p_list.add_argument("--due", action="store_true", help="Only show due highlights.")
    p_list.add_argument("--limit", type=int, default=20, help="Max items.")
    p_list.set_defaults(func=list_highlights)

    p_review = sub.add_parser("review", help="Review due highlights.")
    p_review.add_argument("--limit", type=int, default=10, help="Max due items.")
    p_review.add_argument(
        "--quality", type=int, choices=[0, 1, 2, 3, 4, 5], help="Apply one score for non-interactive mode."
    )
    p_review.set_defaults(func=review)

    p_daily = sub.add_parser("daily", help="Print today's review digest in Markdown.")
    p_daily.add_argument("--due-limit", type=int, default=10, help="Due items in digest.")
    p_daily.add_argument("--random-limit", type=int, default=5, help="Random resurfaced items.")
    p_daily.set_defaults(func=daily)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    conn = connect(Path(args.db))
    args.func(conn, args)
    conn.close()


if __name__ == "__main__":
    main()
