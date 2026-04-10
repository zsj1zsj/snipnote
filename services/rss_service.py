"""RSS Service - feed management, sync, and import."""

import datetime as dt
from pathlib import Path

from storage import connect, RssFeedRepository, RssArticleRepository, HighlightRepository
from rss.parser import fetch_feed


class RssService:
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)

    def _conn(self):
        return connect(self.db_path)

    def subscribe(self, feed_url: str) -> dict:
        """Subscribe to an RSS feed. Fetches metadata and initial articles."""
        conn = self._conn()
        feed_repo = RssFeedRepository(conn)

        existing = feed_repo.get_by_url(feed_url)
        if existing:
            return {"feed_id": existing.id, "title": existing.title, "new_articles": 0, "already_subscribed": True}

        feed_data = fetch_feed(feed_url)
        feed_id = feed_repo.add(
            title=feed_data.title or feed_url,
            url=feed_url,
            site_url=feed_data.site_url,
            description=feed_data.description,
        )

        article_repo = RssArticleRepository(conn)
        count = 0
        for article in feed_data.articles:
            if not article.url or article_repo.url_exists(article.url):
                continue
            article_repo.add(
                feed_id=feed_id,
                title=article.title,
                url=article.url,
                author=article.author,
                summary=article.summary,
                published_at=article.published_at,
            )
            count += 1

        feed_repo.update_last_fetched(feed_id)
        return {"feed_id": feed_id, "title": feed_data.title, "new_articles": count, "already_subscribed": False}

    def unsubscribe(self, feed_id: int) -> None:
        conn = self._conn()
        RssFeedRepository(conn).delete(feed_id)

    def refresh_feed(self, feed_id: int) -> int:
        """Refresh a single feed. Returns count of new articles."""
        conn = self._conn()
        feed_repo = RssFeedRepository(conn)
        article_repo = RssArticleRepository(conn)

        feed = feed_repo.get_by_id(feed_id)
        if not feed:
            raise ValueError(f"Feed {feed_id} not found")

        feed_data = fetch_feed(feed.url)
        count = 0
        for article in feed_data.articles:
            if not article.url or article_repo.url_exists(article.url):
                continue
            article_repo.add(
                feed_id=feed_id,
                title=article.title,
                url=article.url,
                author=article.author,
                summary=article.summary,
                published_at=article.published_at,
            )
            count += 1

        feed_repo.update_last_fetched(feed_id)
        return count

    def refresh_all(self) -> dict:
        """Refresh all feeds. Returns {feed_id: new_article_count}."""
        conn = self._conn()
        feeds = RssFeedRepository(conn).list_all()
        results = {}
        for feed in feeds:
            try:
                results[feed.id] = self.refresh_feed(feed.id)
            except Exception:
                results[feed.id] = 0
        return results

    def import_article(self, article_id: int) -> int:
        """Import an RSS article as a highlight. Returns highlight_id."""
        conn = self._conn()
        article_repo = RssArticleRepository(conn)
        article = article_repo.get_by_id(article_id)
        if not article:
            raise ValueError(f"Article {article_id} not found")
        if article.is_imported and article.highlight_id:
            return article.highlight_id

        from parser.engine import parse_link_to_markdown
        result = parse_link_to_markdown(article.url)

        highlight_repo = HighlightRepository(conn)
        highlight_id = highlight_repo.add(
            text=result.markdown,
            source=result.title or article.title,
            author=article.author,
            location=article.url,
            tags="rss",
        )
        article_repo.mark_imported(article_id, highlight_id)
        article_repo.mark_read(article_id)
        return highlight_id
