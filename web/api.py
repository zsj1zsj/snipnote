"""FastAPI application for SnipNote Web UI.

This module provides REST API endpoints for the React frontend.
"""
import os
import threading
import time
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional, List

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from storage import connect, HighlightRepository, AnnotationRepository, RssFeedRepository, RssArticleRepository
from scheduler import SM2Scheduler
from services.report_service import ReportService
from ai import summarize as ai_summarize, suggest_tags as ai_suggest_tags
from parser import parse_link_to_markdown


def _config_dir():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


DEFAULT_DB = Path(_config_dir()) / "data" / "readlite.db"


def get_db_path() -> Path:
    """Get database path from environment or default."""
    db_path = os.environ.get("SNIPNOTE_DB")
    if db_path:
        return Path(db_path)
    return DEFAULT_DB


def get_db():
    """Get database connection."""
    conn = connect(get_db_path())
    try:
        yield conn
    finally:
        conn.close()


# Pydantic models
class HighlightCreate(BaseModel):
    text: str
    source: Optional[str] = None
    author: Optional[str] = None
    location: Optional[str] = None
    tags: Optional[str] = None


class HighlightUpdate(BaseModel):
    text: Optional[str] = None
    source: Optional[str] = None
    author: Optional[str] = None
    tags: Optional[str] = None
    summary: Optional[str] = None


class AnnotationCreate(BaseModel):
    highlight_id: int
    selected_text: str = ""
    note: str = ""


class SummarizeRequest(BaseModel):
    text: str


class SuggestTagsRequest(BaseModel):
    text: str
    existing_tags: str = ""


class AnnotationUpdate(BaseModel):
    note: str


class ReviewSubmit(BaseModel):
    quality: int


class TagCreate(BaseModel):
    name: str


class TagRename(BaseModel):
    new_name: str


class ReportGenerate(BaseModel):
    date: Optional[str] = None
    force: bool = False


class ParseLinkRequest(BaseModel):
    url: str


class RssFeedCreate(BaseModel):
    url: str
    category: Optional[str] = None


class RssFeedUpdate(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None


class RssRefreshRequest(BaseModel):
    feed_id: Optional[int] = None


class RssBatchReadRequest(BaseModel):
    feed_id: Optional[int] = None


class RssBatchImportRequest(BaseModel):
    article_ids: List[int]


def _auto_refresh_worker(interval_hours: float, refresh_rss: bool, refresh_podcast: bool):
    """Background thread: refresh feeds every interval_hours."""
    import logging
    log = logging.getLogger("snipnote.auto_refresh")
    while True:
        time.sleep(interval_hours * 3600)
        if refresh_podcast:
            try:
                from services.podcast_service import PodcastService
                svc = PodcastService(str(get_db_path()))
                results = svc.refresh_all()
                total = sum(results.values())
                if total:
                    log.info(f"Auto-refresh: {total} new podcast episodes fetched")
            except Exception as e:
                log.warning(f"Podcast auto-refresh failed: {e}")
        if refresh_rss:
            try:
                from services.rss_service import RssService
                svc = RssService(str(get_db_path()))
                results = svc.refresh_all()
                total = sum(results.values())
                if total:
                    log.info(f"Auto-refresh: {total} new RSS articles fetched")
            except Exception as e:
                log.warning(f"RSS auto-refresh failed: {e}")


def _start_auto_refresh():
    """Start the auto-refresh background thread if configured."""
    import json, logging
    config_path = Path(_config_dir()) / "config" / "config.json"
    try:
        with open(config_path) as f:
            config = json.load(f)
    except Exception:
        config = {}

    podcast_interval = float(config.get("podcast", {}).get("auto_refresh_hours", 0))
    rss_interval = float(config.get("rss", {}).get("auto_refresh_hours", 0))

    # Use the smaller non-zero interval, refresh each type at its own rate
    interval = min(i for i in [podcast_interval, rss_interval] if i > 0) if any(i > 0 for i in [podcast_interval, rss_interval]) else 0

    if interval > 0:
        t = threading.Thread(
            target=_auto_refresh_worker,
            args=(interval, rss_interval > 0, podcast_interval > 0),
            daemon=True,
        )
        t.start()
        parts = []
        if podcast_interval > 0:
            parts.append(f"Podcast every {podcast_interval}h")
        if rss_interval > 0:
            parts.append(f"RSS every {rss_interval}h")
        logging.getLogger("snipnote").info(f"Auto-refresh enabled: {', '.join(parts)}")


@asynccontextmanager
async def lifespan(app):
    _start_auto_refresh()
    yield


# FastAPI app
app = FastAPI(title="SnipNote API", version="2.0.0", lifespan=lifespan)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Helper functions
def highlight_to_dict(h):
    """Convert Highlight to dict."""
    return {
        "id": h.id,
        "text": h.text,
        "source": h.source,
        "author": h.author,
        "location": h.location,
        "tags": h.tags,
        "summary": h.summary,
        "created_at": h.created_at,
        "last_reviewed": h.last_reviewed,
        "next_review": h.next_review,
        "favorite": h.favorite,
        "is_read": h.is_read,
        "repetitions": h.repetitions,
        "interval_days": h.interval_days,
        "efactor": h.efactor,
    }


def annotation_to_dict(a):
    """Convert Annotation to dict."""
    return {
        "id": a.id,
        "highlight_id": a.highlight_id,
        "selected_text": a.selected_text,
        "note": a.note,
        "created_at": a.created_at,
    }


# API Endpoints

@app.get("/api/highlights")
def get_highlights(
    q: str = Query("", description="Search keyword"),
    tag: str = Query("", description="Filter by tag"),
    read: str = Query("all", description="Filter by read status: all, read, unread"),
    limit: int = Query(100, ge=1, le=500),
):
    """Get list of highlights with optional filters."""
    conn = connect(get_db_path())
    repo = HighlightRepository(conn)

    highlights = repo.search(keyword=q, tag=tag, read_filter=read, limit=limit)

    conn.close()

    return [highlight_to_dict(h) for h in highlights]


@app.get("/api/highlights/{highlight_id}")
def get_highlight(highlight_id: int):
    """Get a single highlight by ID."""
    conn = connect(get_db_path())
    repo = HighlightRepository(conn)

    highlight = repo.get_by_id(highlight_id)
    if not highlight:
        conn.close()
        raise HTTPException(status_code=404, detail="Highlight not found")

    # Get annotations
    annotation_repo = AnnotationRepository(conn)
    annotations = annotation_repo.get_by_highlight(highlight_id)

    conn.close()

    return {
        "highlight": highlight_to_dict(highlight),
        "annotations": [annotation_to_dict(a) for a in annotations],
    }


@app.post("/api/highlights")
def create_highlight(highlight: HighlightCreate):
    """Create a new highlight."""
    conn = connect(get_db_path())
    repo = HighlightRepository(conn)

    highlight_id = repo.add(
        text=highlight.text,
        source=highlight.source or "",
        author=highlight.author or "",
        location=highlight.location or "",
        tags=highlight.tags or "",
    )

    created = repo.get_by_id(highlight_id)
    conn.close()

    if not created:
        raise HTTPException(status_code=500, detail="Failed to create highlight")

    return highlight_to_dict(created)


@app.put("/api/highlights/{highlight_id}")
def update_highlight(highlight_id: int, update: HighlightUpdate):
    """Update a highlight."""
    conn = connect(get_db_path())
    repo = HighlightRepository(conn)

    existing = repo.get_by_id(highlight_id)
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Highlight not found")

    # Update fields
    if update.text is not None:
        conn.execute("UPDATE highlights SET text = ? WHERE id = ?", (update.text, highlight_id))
    if update.source is not None:
        conn.execute("UPDATE highlights SET source = ? WHERE id = ?", (update.source, highlight_id))
    if update.author is not None:
        conn.execute("UPDATE highlights SET author = ? WHERE id = ?", (update.author, highlight_id))
    if update.tags is not None:
        conn.execute("UPDATE highlights SET tags = ? WHERE id = ?", (update.tags, highlight_id))
    if update.summary is not None:
        conn.execute("UPDATE highlights SET summary = ? WHERE id = ?", (update.summary, highlight_id))

    conn.commit()

    updated = repo.get_by_id(highlight_id)
    conn.close()

    return highlight_to_dict(updated)


@app.delete("/api/highlights/{highlight_id}")
def delete_highlight(highlight_id: int):
    """Delete a highlight."""
    conn = connect(get_db_path())
    repo = HighlightRepository(conn)

    existing = repo.get_by_id(highlight_id)
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Highlight not found")

    repo.delete(highlight_id)
    conn.close()

    return {"status": "deleted", "id": highlight_id}


@app.post("/api/highlights/{highlight_id}/favorite")
def toggle_favorite(highlight_id: int):
    """Toggle favorite status."""
    conn = connect(get_db_path())
    repo = HighlightRepository(conn)

    highlight = repo.get_by_id(highlight_id)
    if not highlight:
        conn.close()
        raise HTTPException(status_code=404, detail="Highlight not found")

    new_value = 1 if highlight.favorite == 0 else 0
    repo.update_favorite(highlight_id, new_value)

    updated = repo.get_by_id(highlight_id)
    conn.close()

    return highlight_to_dict(updated)


@app.post("/api/highlights/{highlight_id}/read")
def toggle_read(highlight_id: int):
    """Toggle read status."""
    conn = connect(get_db_path())
    repo = HighlightRepository(conn)

    highlight = repo.get_by_id(highlight_id)
    if not highlight:
        conn.close()
        raise HTTPException(status_code=404, detail="Highlight not found")

    new_value = 1 if highlight.is_read == 0 else 0
    repo.update_is_read(highlight_id, new_value)

    updated = repo.get_by_id(highlight_id)
    conn.close()

    return highlight_to_dict(updated)


# Annotations
@app.get("/api/highlights/{highlight_id}/annotations")
def get_annotations(highlight_id: int):
    """Get annotations for a highlight."""
    conn = connect(get_db_path())
    repo = AnnotationRepository(conn)

    annotations = repo.get_by_highlight(highlight_id)
    conn.close()

    return [annotation_to_dict(a) for a in annotations]


@app.post("/api/annotations")
def create_annotation(annotation: AnnotationCreate):
    """Create a new annotation."""
    conn = connect(get_db_path())
    repo = AnnotationRepository(conn)

    annotation_id = repo.add(
        highlight_id=annotation.highlight_id,
        selected_text=annotation.selected_text,
        note=annotation.note,
    )

    # Get the created annotation
    annotations = repo.get_by_highlight(annotation.highlight_id)
    created = next((a for a in annotations if a.id == annotation_id), None)

    conn.close()

    if not created:
        raise HTTPException(status_code=500, detail="Failed to create annotation")

    return annotation_to_dict(created)


@app.put("/api/annotations/{annotation_id}")
def update_annotation(annotation_id: int, update: AnnotationUpdate):
    """Update an annotation."""
    conn = connect(get_db_path())
    repo = AnnotationRepository(conn)

    annotations = conn.execute("SELECT * FROM annotations WHERE id = ?", (annotation_id,)).fetchone()
    if not annotations:
        conn.close()
        raise HTTPException(status_code=404, detail="Annotation not found")

    repo.update_note(annotation_id, update.note)

    # Get updated annotation
    updated_list = repo.get_by_highlight(
        conn.execute("SELECT highlight_id FROM annotations WHERE id = ?", (annotation_id,)).fetchone()[0]
    )
    conn.close()

    updated = next((a for a in updated_list if a.id == annotation_id), None)
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to fetch updated annotation")
    return annotation_to_dict(updated)


@app.delete("/api/annotations/{annotation_id}")
def delete_annotation(annotation_id: int):
    """Delete an annotation."""
    conn = connect(get_db_path())
    repo = AnnotationRepository(conn)

    annotations = conn.execute("SELECT * FROM annotations WHERE id = ?", (annotation_id,)).fetchone()
    if not annotations:
        conn.close()
        raise HTTPException(status_code=404, detail="Annotation not found")

    repo.delete(annotation_id)
    conn.close()

    return {"status": "deleted", "id": annotation_id}


# Tags
@app.get("/api/tags")
def get_tags():
    """Get all tags with counts."""
    conn = connect(get_db_path())

    all_tags = conn.execute("SELECT tags FROM highlights WHERE tags != ''").fetchall()

    tag_counts: dict[str, int] = {}
    for row in all_tags:
        tags_str = row["tags"] or ""
        for tag in tags_str.split(","):
            tag = tag.strip()
            if tag:
                tag = tag.lower()
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

    # Sort by count descending
    sorted_tags = sorted(tag_counts.items(), key=lambda x: (-x[1], x[0]))

    conn.close()

    return [{"name": name, "count": count} for name, count in sorted_tags]


@app.post("/api/tags/rename")
def rename_tag(old_name: str, new_name: str):
    """Rename a tag across all highlights."""
    conn = connect(get_db_path())

    # Get all highlights with the old tag
    highlights = conn.execute(
        "SELECT id, tags FROM highlights WHERE tags LIKE ?",
        (f"%{old_name}%",)
    ).fetchall()

    updated = 0
    for row in highlights:
        tags_list = [t.strip() for t in row["tags"].split(",")]
        if old_name.lower() in [t.lower() for t in tags_list]:
            # Replace the tag
            tags_list = [new_name if t.lower() == old_name.lower() else t for t in tags_list]
            new_tags = ",".join(tags_list)
            conn.execute("UPDATE highlights SET tags = ? WHERE id = ?", (new_tags, row["id"]))
            updated += 1

    conn.commit()
    conn.close()

    return {"status": "updated", "old_name": old_name, "new_name": new_name, "count": updated}


@app.delete("/api/tags/{name}")
def delete_tag(name: str):
    """Delete a tag from all highlights."""
    conn = connect(get_db_path())

    # Get all highlights with the tag
    highlights = conn.execute(
        "SELECT id, tags FROM highlights WHERE tags LIKE ?",
        (f"%{name}%",)
    ).fetchall()

    updated = 0
    for row in highlights:
        tags_list = [t.strip() for t in row["tags"].split(",")]
        if name.lower() in [t.lower() for t in tags_list]:
            # Remove the tag
            tags_list = [t for t in tags_list if t.lower() != name.lower()]
            new_tags = ",".join(tags_list)
            conn.execute("UPDATE highlights SET tags = ? WHERE id = ?", (new_tags, row["id"]))
            updated += 1

    conn.commit()
    conn.close()

    return {"status": "deleted", "name": name, "count": updated}


# Review
@app.get("/api/review/next")
def get_next_review(limit: int = Query(20, ge=1, le=100)):
    """Get highlights due for review."""
    conn = connect(get_db_path())
    repo = HighlightRepository(conn)

    due = repo.get_due(limit=limit)
    conn.close()

    return [highlight_to_dict(h) for h in due]


@app.post("/api/review/{highlight_id}")
def submit_review(highlight_id: int, review: ReviewSubmit):
    """Submit a review score and update scheduling."""
    conn = connect(get_db_path())
    repo = HighlightRepository(conn)

    highlight = repo.get_by_id(highlight_id)
    if not highlight:
        conn.close()
        raise HTTPException(status_code=404, detail="Highlight not found")

    result = SM2Scheduler.next_schedule(
        highlight.repetitions,
        highlight.interval_days,
        highlight.efactor,
        review.quality,
    )

    repo.update_review(
        highlight_id,
        result.repetitions,
        result.interval_days,
        result.efactor,
        result.next_review,
    )

    updated = repo.get_by_id(highlight_id)
    conn.close()

    return highlight_to_dict(updated)


# Favorites
@app.get("/api/favorites")
def get_favorites(
    q: str = Query("", description="Search keyword"),
    tag: str = Query("", description="Filter by tag"),
    limit: int = Query(100, ge=1, le=500),
):
    """Get favorite highlights."""
    conn = connect(get_db_path())
    repo = HighlightRepository(conn)

    favorites = repo.get_favorites(keyword=q, tag=tag, limit=limit)
    conn.close()

    return [highlight_to_dict(h) for h in favorites]


# Reports
@app.get("/api/reports")
def get_reports(limit: int = Query(30, ge=1, le=100)):
    """Get list of daily reports."""
    conn = connect(get_db_path())

    reports = conn.execute(
        "SELECT id, report_date, created_at FROM daily_reports ORDER BY report_date DESC LIMIT ?",
        (limit,),
    ).fetchall()

    conn.close()

    return [
        {
            "id": r["id"],
            "date": r["report_date"],
            "created_at": r["created_at"],
        }
        for r in reports
    ]


@app.get("/api/reports/{report_date}")
def get_report(report_date: str):
    """Get a specific daily report."""
    conn = connect(get_db_path())

    report = conn.execute(
        "SELECT * FROM daily_reports WHERE report_date = ?",
        (report_date,),
    ).fetchone()

    conn.close()

    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    return {
        "id": report["id"],
        "date": report["report_date"],
        "content": report["content"],
        "created_at": report["created_at"],
    }


@app.post("/api/reports")
def generate_report(request: ReportGenerate = None):
    """Generate a daily report."""
    target_date = None
    force = False

    if request:
        if request.date:
            target_date = datetime.strptime(request.date, "%Y-%m-%d").date()
        force = request.force

    service = ReportService(str(get_db_path()))
    filepath = service.generate(target_date=target_date, force=force)

    # Return the report
    report_date = target_date.isoformat() if target_date else (datetime.now().date() - timedelta(days=1)).isoformat()

    conn = connect(get_db_path())
    report = conn.execute(
        "SELECT * FROM daily_reports WHERE report_date = ?",
        (report_date,),
    ).fetchone()
    conn.close()

    if report:
        return {
            "id": report["id"],
            "date": report["report_date"],
            "content": report["content"],
            "created_at": report["created_at"],
        }

    return {"status": "generated", "filepath": filepath}


# Stats
@app.get("/api/stats")
def get_stats():
    """Get overall statistics."""
    conn = connect(get_db_path())

    total = conn.execute("SELECT COUNT(*) as c FROM highlights").fetchone()["c"]
    unread = conn.execute("SELECT COUNT(*) as c FROM highlights WHERE is_read = 0").fetchone()["c"]
    due = conn.execute(
        "SELECT COUNT(*) as c FROM highlights WHERE date(next_review) <= date('now')"
    ).fetchone()["c"]
    favorites = conn.execute("SELECT COUNT(*) as c FROM highlights WHERE favorite = 1").fetchone()["c"]

    conn.close()

    return {
        "total": total,
        "unread": unread,
        "due": due,
        "favorites": favorites,
    }


# AI endpoints
@app.post("/api/ai/summarize")
def summarize_text(request: SummarizeRequest):
    """Summarize text using AI."""
    try:
        summary = ai_summarize(request.text)
        return {"summary": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI summarization failed: {str(e)}")


@app.post("/api/ai/suggest-tags")
def suggest_tags_request(request: SuggestTagsRequest):
    """Suggest tags using AI."""
    try:
        tags = ai_suggest_tags(request.text, request.existing_tags or "")
        return {"tags": tags}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI tag suggestion failed: {str(e)}")


# Parser endpoint
@app.post("/api/parse")
def parse_url(request: ParseLinkRequest):
    """Parse a URL and extract content as markdown."""
    try:
        result = parse_link_to_markdown(request.url)
        return {"title": result.title, "content": result.markdown}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Parsing failed: {str(e)}")


def _parse_and_update_highlight(highlight_id: int, url: str, db_path):
    """Background task: parse URL and update highlight with real content."""
    try:
        result = parse_link_to_markdown(url)
        conn = connect(db_path)
        conn.execute(
            "UPDATE highlights SET text = ?, source = ? WHERE id = ?",
            (result.markdown, result.title, highlight_id),
        )
        conn.commit()
        conn.close()
    except Exception:
        # On failure, mark the placeholder so user knows parsing failed
        try:
            conn = connect(db_path)
            conn.execute(
                "UPDATE highlights SET text = ? WHERE id = ? AND text = ?",
                ("（解析失败，请删除后重新添加）", highlight_id, "（正在解析中，请稍后刷新查看…）"),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass


@app.post("/api/highlights/from-url")
def create_highlight_from_url(request: ParseLinkRequest, background_tasks: BackgroundTasks):
    """Create a highlight from a URL immediately, parse content in background."""
    from urllib.parse import urlparse
    host = urlparse(request.url).netloc or request.url
    placeholder = "（正在解析中，请稍后刷新查看…）"

    db_path = get_db_path()
    conn = connect(db_path)
    repo = HighlightRepository(conn)
    highlight_id = repo.add(
        text=placeholder,
        source=host,
        location=request.url,
    )
    conn.close()

    background_tasks.add_task(_parse_and_update_highlight, highlight_id, request.url, db_path)

    return {"id": highlight_id}


# ── RSS Endpoints ──────────────────────────────────────────────

def _rss_service():
    from services.rss_service import RssService
    return RssService(str(get_db_path()))


@app.get("/api/rss/feeds")
def list_rss_feeds():
    conn = connect(get_db_path())
    feed_repo = RssFeedRepository(conn)
    article_repo = RssArticleRepository(conn)
    feeds = feed_repo.list_all()
    result = []
    for f in feeds:
        counts = article_repo.count_by_feed(f.id)
        result.append({
            "id": f.id, "title": f.title, "url": f.url,
            "site_url": f.site_url, "description": f.description,
            "category": f.category,
            "created_at": f.created_at, "last_fetched_at": f.last_fetched_at,
            "total_articles": counts["total"], "unread_articles": counts["unread"],
            "error_count": f.error_count, "last_error": f.last_error,
        })
    conn.close()
    return result


@app.get("/api/rss/categories")
def list_rss_categories():
    conn = connect(get_db_path())
    categories = RssFeedRepository(conn).list_categories()
    conn.close()
    return categories


@app.get("/api/rss/unread-count")
def rss_unread_count():
    conn = connect(get_db_path())
    count = RssArticleRepository(conn).total_unread()
    conn.close()
    return {"count": count}


@app.post("/api/rss/feeds")
def subscribe_rss_feed(request: RssFeedCreate):
    try:
        result = _rss_service().subscribe(request.url, category=request.category or "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"无法获取 RSS 源: {e}")
    return result


@app.put("/api/rss/feeds/{feed_id}")
def update_rss_feed(feed_id: int, update: RssFeedUpdate):
    conn = connect(get_db_path())
    feed_repo = RssFeedRepository(conn)
    feed = feed_repo.get_by_id(feed_id)
    if not feed:
        conn.close()
        raise HTTPException(status_code=404, detail="Feed not found")
    if update.title is not None:
        feed_repo.update_title(feed_id, update.title)
    if update.category is not None:
        feed_repo.update_category(feed_id, update.category)
    conn.close()
    return {"ok": True}


@app.delete("/api/rss/feeds/{feed_id}")
def unsubscribe_rss_feed(feed_id: int):
    _rss_service().unsubscribe(feed_id)
    return {"ok": True}


@app.post("/api/rss/refresh")
def refresh_rss(request: RssRefreshRequest):
    svc = _rss_service()
    try:
        if request.feed_id:
            count = svc.refresh_feed(request.feed_id)
            return {"results": {str(request.feed_id): count}}
        else:
            results = svc.refresh_all()
            return {"results": {str(k): v for k, v in results.items()}}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/rss/articles")
def list_rss_articles(
    feed_id: int = Query(0),
    is_read: str = Query("all"),
    search: str = Query(""),
    sort: str = Query("published_at"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    conn = connect(get_db_path())
    article_repo = RssArticleRepository(conn)
    feed_repo = RssFeedRepository(conn)
    articles = article_repo.list_all(feed_id=feed_id, is_read=is_read, search=search, sort=sort, limit=limit, offset=offset)
    # Build feed name lookup
    feeds = {f.id: f.title for f in feed_repo.list_all()}
    result = []
    for a in articles:
        result.append({
            "id": a.id, "feed_id": a.feed_id,
            "feed_title": feeds.get(a.feed_id, ""),
            "title": a.title, "url": a.url,
            "author": a.author, "summary": a.summary,
            "published_at": a.published_at, "fetched_at": a.fetched_at,
            "is_read": a.is_read, "is_imported": a.is_imported,
            "highlight_id": a.highlight_id,
        })
    conn.close()
    return result


@app.get("/api/rss/articles/{article_id}")
def get_rss_article(article_id: int):
    conn = connect(get_db_path())
    article_repo = RssArticleRepository(conn)
    article = article_repo.get_by_id(article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    feed_repo = RssFeedRepository(conn)
    feed = feed_repo.get_by_id(article.feed_id)
    conn.close()
    return {
        "id": article.id, "feed_id": article.feed_id,
        "feed_title": feed.title if feed else "",
        "title": article.title, "url": article.url,
        "author": article.author, "summary": article.summary,
        "published_at": article.published_at, "fetched_at": article.fetched_at,
        "is_read": article.is_read, "is_imported": article.is_imported,
        "highlight_id": article.highlight_id,
    }


@app.post("/api/rss/articles/{article_id}/read")
def toggle_rss_article_read(article_id: int):
    conn = connect(get_db_path())
    article_repo = RssArticleRepository(conn)
    article = article_repo.get_by_id(article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    new_status = 0 if article.is_read else 1
    article_repo.mark_read(article_id, new_status)
    conn.close()
    return {"id": article_id, "is_read": new_status}


@app.post("/api/rss/articles/{article_id}/import")
def import_rss_article(article_id: int, background_tasks: BackgroundTasks):
    conn = connect(get_db_path())
    article_repo = RssArticleRepository(conn)
    article = article_repo.get_by_id(article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    if article.is_imported and article.highlight_id:
        conn.close()
        return {"article_id": article_id, "highlight_id": article.highlight_id, "already_imported": True}
    conn.close()

    def _do_import():
        svc = _rss_service()
        svc.import_article(article_id)

    background_tasks.add_task(_do_import)
    return {"article_id": article_id, "importing": True}


@app.post("/api/rss/articles/mark-all-read")
def mark_all_rss_read(request: RssBatchReadRequest):
    conn = connect(get_db_path())
    article_repo = RssArticleRepository(conn)
    count = article_repo.mark_all_read(feed_id=request.feed_id or 0)
    conn.close()
    return {"marked": count}


@app.post("/api/rss/articles/batch-import")
def batch_import_rss_articles(request: RssBatchImportRequest, background_tasks: BackgroundTasks):
    def _do_batch():
        svc = _rss_service()
        for aid in request.article_ids:
            try:
                svc.import_article(aid)
            except Exception:
                pass

    background_tasks.add_task(_do_batch)
    return {"importing": True, "count": len(request.article_ids)}


@app.get("/api/rss/opml")
def export_rss_opml():
    from fastapi.responses import Response
    xml = _rss_service().export_opml()
    return Response(
        content=xml,
        media_type='text/xml',
        headers={'Content-Disposition': 'attachment; filename="rss-subscriptions.opml"'},
    )


@app.post("/api/rss/opml")
async def import_rss_opml(request: Request, background_tasks: BackgroundTasks):
    body = await request.body()
    svc = _rss_service()
    try:
        feed_urls = svc.import_opml(body.decode('utf-8'))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not feed_urls:
        raise HTTPException(status_code=400, detail="OPML 中未找到任何订阅源")

    def _do_import():
        for url in feed_urls:
            try:
                svc.subscribe(url)
            except Exception:
                pass

    background_tasks.add_task(_do_import)
    return {"importing": True, "count": len(feed_urls)}


# ── Podcast endpoints ──────────────────────────────────────────────────────────

class PodcastShowCreate(BaseModel):
    url: str

class PodcastRefreshRequest(BaseModel):
    show_id: Optional[int] = None

class PlayProgressUpdate(BaseModel):
    position: int  # seconds


def _podcast_service():
    from services.podcast_service import PodcastService
    return PodcastService(str(get_db_path()))


@app.get("/api/podcast/shows")
def list_podcast_shows():
    """List all podcast subscriptions with episode counts."""
    conn = connect(get_db_path())
    from podcast.repository import PodcastShowRepository, PodcastEpisodeRepository
    show_repo = PodcastShowRepository(conn)
    ep_repo = PodcastEpisodeRepository(conn)
    shows = show_repo.list_all()
    result = []
    for show in shows:
        counts = ep_repo.count_by_show(show.id)
        result.append({**show.__dict__, **counts})
    conn.close()
    return result


@app.post("/api/podcast/shows")
def add_podcast_show(body: PodcastShowCreate):
    """Subscribe to a new podcast feed."""
    try:
        return _podcast_service().subscribe(body.url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"订阅失败: {e}")


@app.delete("/api/podcast/shows/{show_id}")
def delete_podcast_show(show_id: int):
    """Unsubscribe from a podcast."""
    _podcast_service().unsubscribe(show_id)
    return {"ok": True}


@app.post("/api/podcast/refresh")
def refresh_podcast(body: PodcastRefreshRequest):
    """Refresh one or all podcast shows."""
    svc = _podcast_service()
    try:
        if body.show_id:
            count = svc.refresh_show(body.show_id)
            return {"show_id": body.show_id, "new_episodes": count}
        else:
            results = svc.refresh_all()
            return {"results": results, "total_new": sum(results.values())}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"刷新失败: {e}")


@app.get("/api/podcast/episodes")
def list_podcast_episodes(
    show_id: int = Query(0),
    is_listened: str = Query("all"),
    limit: int = Query(50),
    offset: int = Query(0),
):
    """List podcast episodes with optional filters."""
    conn = connect(get_db_path())
    from podcast.repository import PodcastEpisodeRepository, PodcastShowRepository
    ep_repo = PodcastEpisodeRepository(conn)
    show_repo = PodcastShowRepository(conn)
    episodes = ep_repo.list_all(show_id=show_id, is_listened=is_listened, limit=limit, offset=offset)

    # Build show_id → title map for display
    shows = {s.id: s.title for s in show_repo.list_all()}
    conn.close()

    result = []
    for ep in episodes:
        d = ep.__dict__.copy()
        d["show_title"] = shows.get(ep.show_id, "")
        result.append(d)
    return result


@app.get("/api/podcast/episodes/{episode_id}")
def get_podcast_episode(episode_id: int):
    """Get a single episode with show title."""
    conn = connect(get_db_path())
    from podcast.repository import PodcastEpisodeRepository, PodcastShowRepository
    ep = PodcastEpisodeRepository(conn).get_by_id(episode_id)
    if not ep:
        conn.close()
        raise HTTPException(status_code=404, detail="Episode not found")
    show = PodcastShowRepository(conn).get_by_id(ep.show_id)
    conn.close()
    d = ep.__dict__.copy()
    d["show_title"] = show.title if show else ""
    d["show_image_url"] = show.image_url if show else ""
    return d


@app.post("/api/podcast/episodes/{episode_id}/listened")
def toggle_episode_listened(episode_id: int):
    """Toggle listened status for an episode."""
    try:
        return _podcast_service().toggle_listened(episode_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/podcast/episodes/{episode_id}/progress")
def update_play_progress(episode_id: int, body: PlayProgressUpdate):
    """Update playback position for an episode."""
    _podcast_service().update_play_progress(episode_id, body.position)
    return {"ok": True}


@app.get("/api/podcast/search")
def search_podcasts(q: str = Query(..., min_length=1)):
    """Search podcasts via iTunes Search API."""
    import json as _json
    import urllib.parse
    import urllib.request as _req
    encoded = urllib.parse.quote(q)
    url = f"https://itunes.apple.com/search?term={encoded}&media=podcast&entity=podcast&limit=15"
    request = _req.Request(url, headers={"User-Agent": "SnipNote/1.0"})
    try:
        with _req.urlopen(request, timeout=10) as resp:
            data = _json.loads(resp.read())
        results = []
        for item in data.get("results", []):
            feed_url = item.get("feedUrl")
            if not feed_url:
                continue
            results.append({
                "title": item.get("trackName", ""),
                "author": item.get("artistName", ""),
                "feed_url": feed_url,
                "image_url": item.get("artworkUrl100", "").replace("100x100bb", "300x300bb"),
                "genre": item.get("primaryGenreName", ""),
                "episode_count": item.get("trackCount", 0),
            })
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"搜索失败: {e}")


@app.get("/api/podcast/stats")
def get_podcast_stats():
    """Return global podcast listening statistics."""
    conn = connect(get_db_path())
    from podcast.repository import PodcastEpisodeRepository
    stats = PodcastEpisodeRepository(conn).get_global_stats()
    conn.close()
    return stats


@app.get("/api/podcast/shows/{show_id}")
def get_podcast_show(show_id: int):
    """Get a single podcast show with episode list grouped by season."""
    conn = connect(get_db_path())
    from podcast.repository import PodcastShowRepository, PodcastEpisodeRepository
    show = PodcastShowRepository(conn).get_by_id(show_id)
    if not show:
        conn.close()
        raise HTTPException(status_code=404, detail="Show not found")
    ep_repo = PodcastEpisodeRepository(conn)
    episodes = ep_repo.list_by_show(show_id, limit=500)
    counts = ep_repo.count_by_show(show_id)
    conn.close()
    return {**show.__dict__, **counts, "episodes": [e.__dict__ for e in episodes]}


@app.get("/api/podcast/episodes/{episode_id}/bookmarks")
def list_bookmarks(episode_id: int):
    conn = connect(get_db_path())
    from podcast.repository import PodcastBookmarkRepository
    bms = PodcastBookmarkRepository(conn).list_by_episode(episode_id)
    conn.close()
    return [b.__dict__ for b in bms]


class BookmarkCreate(BaseModel):
    position_seconds: int
    note: str = ""


@app.post("/api/podcast/episodes/{episode_id}/bookmarks")
def add_bookmark(episode_id: int, body: BookmarkCreate):
    conn = connect(get_db_path())
    from podcast.repository import PodcastBookmarkRepository
    bid = PodcastBookmarkRepository(conn).add(episode_id, body.position_seconds, body.note)
    conn.close()
    return {"id": bid}


class BookmarkUpdate(BaseModel):
    note: str


@app.patch("/api/podcast/bookmarks/{bookmark_id}")
def update_bookmark(bookmark_id: int, body: BookmarkUpdate):
    conn = connect(get_db_path())
    from podcast.repository import PodcastBookmarkRepository
    PodcastBookmarkRepository(conn).update_note(bookmark_id, body.note)
    conn.close()
    return {"ok": True}


@app.delete("/api/podcast/bookmarks/{bookmark_id}")
def delete_bookmark(bookmark_id: int):
    conn = connect(get_db_path())
    from podcast.repository import PodcastBookmarkRepository
    PodcastBookmarkRepository(conn).delete(bookmark_id)
    conn.close()
    return {"ok": True}


@app.get("/api/podcast/opml")
def export_opml():
    """Export podcast subscriptions as OPML."""
    from fastapi.responses import Response
    conn = connect(get_db_path())
    from podcast.repository import PodcastShowRepository
    shows = PodcastShowRepository(conn).list_all()
    conn.close()

    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<opml version="2.0">',
             '  <head><title>SnipNote Podcast Subscriptions</title></head>',
             '  <body>',
             '    <outline text="Podcasts" title="Podcasts">']
    for s in shows:
        title = s.title.replace('"', '&quot;')
        url = s.url.replace('"', '&quot;')
        site = s.site_url.replace('"', '&quot;') if s.site_url else ''
        lines.append(
            f'      <outline type="rss" text="{title}" title="{title}" '
            f'xmlUrl="{url}" htmlUrl="{site}"/>'
        )
    lines += ['    </outline>', '  </body>', '</opml>']
    return Response(content='\n'.join(lines), media_type='text/xml',
                    headers={'Content-Disposition': 'attachment; filename="podcasts.opml"'})


@app.post("/api/podcast/opml")
async def import_opml(request: Request, background_tasks: BackgroundTasks):
    """Import podcast subscriptions from OPML file (multipart or raw XML body)."""
    import xml.etree.ElementTree as ET
    body = await request.body()
    try:
        root = ET.fromstring(body)
    except ET.ParseError as e:
        raise HTTPException(status_code=400, detail=f"OPML 解析失败: {e}")

    feed_urls = []
    for outline in root.iter('outline'):
        url = outline.get('xmlUrl') or outline.get('xmlurl')
        if url:
            feed_urls.append(url.strip())

    if not feed_urls:
        raise HTTPException(status_code=400, detail="OPML 中未找到任何订阅源")

    def _do_import():
        from services.podcast_service import PodcastService
        svc = PodcastService(str(get_db_path()))
        for url in feed_urls:
            try:
                svc.subscribe(url)
            except Exception:
                pass

    background_tasks.add_task(_do_import)
    return {"importing": True, "count": len(feed_urls)}


@app.post("/api/podcast/episodes/{episode_id}/save-highlight")
def save_podcast_highlight(episode_id: int):
    """Save podcast episode AI summary (or description) as a highlight."""
    conn = connect(get_db_path())
    from podcast.repository import PodcastEpisodeRepository, PodcastShowRepository
    ep = PodcastEpisodeRepository(conn).get_by_id(episode_id)
    if not ep:
        conn.close()
        raise HTTPException(status_code=404, detail="Episode not found")
    show = PodcastShowRepository(conn).get_by_id(ep.show_id)
    show_title = show.title if show else ""
    conn.close()

    text = ep.ai_summary or ep.description
    if not text:
        raise HTTPException(status_code=400, detail="暂无可保存的内容，请先生成 AI 总结")

    conn2 = connect(get_db_path())
    highlight_id = HighlightRepository(conn2).add(
        text=text,
        source=ep.title,
        author=show_title,
        location=ep.audio_url,
        tags="podcast",
    )
    conn2.close()
    return {"highlight_id": highlight_id}


@app.post("/api/podcast/episodes/{episode_id}/summarize")
def summarize_podcast_episode(episode_id: int, background_tasks: BackgroundTasks):
    """Trigger AI summarization for a podcast episode (runs in background)."""
    conn = connect(get_db_path())
    from podcast.repository import PodcastEpisodeRepository
    ep = PodcastEpisodeRepository(conn).get_by_id(episode_id)
    conn.close()
    if not ep:
        raise HTTPException(status_code=404, detail="Episode not found")
    if ep.ai_summary:
        return {"episode_id": episode_id, "summary": ep.ai_summary, "cached": True}

    def _do_summarize():
        from ai import summarize_podcast_episode as ai_summarize_ep
        from podcast.repository import PodcastEpisodeRepository
        summary = ai_summarize_ep(ep)
        conn2 = connect(get_db_path())
        PodcastEpisodeRepository(conn2).update_ai_summary(episode_id, summary)
        conn2.close()

    background_tasks.add_task(_do_summarize)
    return {"episode_id": episode_id, "summarizing": True}


# Health check
@app.get("/api/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


# Determine frontend dist path
# _config_dir() returns project root (parent of web/)
FRONTEND_DIST = Path(_config_dir()) / "frontend" / "dist"


def _get_frontend_dist():
    """Get frontend dist path, fallback to empty if not built."""
    if FRONTEND_DIST.exists():
        return FRONTEND_DIST
    return None


# Serve static files if frontend is built
frontend_dist = _get_frontend_dist()
if frontend_dist:
    # Mount assets directory (Vite outputs to dist/assets)
    if (frontend_dist / "assets").exists():
        app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")

    # Catch-all for SPA routing - serve index.html for non-API routes
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve the SPA for any non-API route."""
        # If it's an API route, let it 404
        if full_path.startswith("api"):
            raise HTTPException(status_code=404, detail="Not found")

        # Try to serve the file directly
        file_path = frontend_dist / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)

        # Fallback to index.html for SPA routing
        return FileResponse(str(frontend_dist / "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8787)
