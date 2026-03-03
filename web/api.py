"""FastAPI application for SnipNote Web UI.

This module provides REST API endpoints for the React frontend.
"""
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from storage import connect, HighlightRepository, AnnotationRepository
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


# FastAPI app
app = FastAPI(title="SnipNote API", version="2.0.0")

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
    updated = conn.execute("SELECT * FROM annotations WHERE id = ?", (annotation_id,)).fetchone()
    conn.close()

    return annotation_to_dict(dict(updated))


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
