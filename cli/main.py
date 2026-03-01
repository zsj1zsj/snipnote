#!/usr/bin/env python3
"""SnipNote CLI - Command line interface for managing highlights."""
import argparse
import csv
import datetime as dt
import json
import random
import sqlite3
from pathlib import Path

from storage import connect, HighlightRepository
from scheduler import SM2Scheduler
from services.report_service import ReportService


DEFAULT_DB = Path("data/readlite.db")


def today() -> dt.date:
    return dt.date.today()


def iso_date(value: dt.date) -> str:
    return value.isoformat()


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


def add_highlight(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    repo = HighlightRepository(conn)
    repo.add(
        text=args.text.strip(),
        source=args.source or "",
        author=args.author or "",
        location=args.location or "",
        tags=args.tags or "",
    )
    print("Added 1 highlight.")


def import_highlights(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    rows = _parse_import_file(Path(args.file))
    values = []
    for row in rows:
        text = (row.get("text") or "").strip()
        if not text:
            continue
        values.append((
            text,
            row.get("source", ""),
            row.get("author", ""),
            row.get("location", ""),
            row.get("tags", ""),
        ))
    if not values:
        print("No valid highlights found.")
        return

    repo = HighlightRepository(conn)
    count = repo.add_batch(values)
    print(f"Imported {count} highlights.")


def list_highlights(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    repo = HighlightRepository(conn)
    highlights = repo.list_all(limit=args.limit, due_only=args.due)

    if not highlights:
        print("No highlights.")
        return

    for h in highlights:
        source = f"{h.author} - {h.source}".strip(" -")
        tags = f" #{h.tags.replace(',', ' #')}" if h.tags else ""
        print(
            f"[{h.id}] (due {h.next_review}) reps={h.repetitions}\n"
            f"{h.text}\n"
            f"{source}{tags}\n"
        )


def review(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    repo = HighlightRepository(conn)
    rows = repo.get_due(limit=args.limit)

    if not rows:
        print("No due highlights today.")
        return

    reviewed = 0
    for row in rows:
        print(f"\n[{row.id}] {row.author} - {row.source}".strip(" -"))
        print(row.text)

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

        result = SM2Scheduler.next_schedule(
            row.repetitions, row.interval_days, row.efactor, quality
        )
        repo.update_review(row.id, result.repetitions, result.interval_days,
                          result.efactor, result.next_review)
        reviewed += 1
        if args.quality is not None:
            print(f"Scored {quality}, next review on {iso_date(result.next_review)}")

    print(f"\nReviewed {reviewed} highlight(s).")


def daily(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    repo = HighlightRepository(conn)
    due = repo.get_due(limit=args.due_limit)

    # Random resurfaced items
    all_highlights = repo.list_all(limit=args.random_limit)
    random.shuffle(all_highlights)
    resurfaced = all_highlights[:args.random_limit]

    date_str = iso_date(today())
    print(f"# Daily Review ({date_str})\n")
    print("## Due Today")
    if not due:
        print("- None")
    for h in due:
        meta = f"{h.author} - {h.source}".strip(" -")
        print(f"- [{h.id}] {h.text} ({meta})")

    print("\n## Random Resurface")
    if not resurfaced:
        print("- None")
    for h in resurfaced:
        meta = f"{h.author} - {h.source}".strip(" -")
        print(f"- [{h.id}] {h.text} ({meta})")


def generate_report(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    target_date = None
    if args.date:
        from datetime import datetime
        target_date = datetime.strptime(args.date, "%Y-%m-%d").date()

    service = ReportService(args.db)
    filepath = service.generate(target_date=target_date, force=args.force)
    print(f"Report generated: {filepath}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SnipNote: a lightweight Readwise alternative.")
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

    # Report commands
    p_report = sub.add_parser("report", help="Generate daily report.")
    p_report.add_argument("--date", default="", help="Report date (YYYY-MM-DD), defaults to yesterday.")
    p_report.add_argument("--force", action="store_true", help="Force regenerate if exists.")
    p_report.set_defaults(func=generate_report)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    conn = connect(Path(args.db))
    args.func(conn, args)
    conn.close()


if __name__ == "__main__":
    main()
