"""RSS Service - feed management, sync, import, and OPML."""

import datetime as dt
import xml.etree.ElementTree as ET
from pathlib import Path

from storage import connect, RssFeedRepository, RssArticleRepository, HighlightRepository
from rss.parser import fetch_feed


class RssService:
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)

    def _conn(self):
        return connect(self.db_path)

    def subscribe(self, feed_url: str, category: str = "") -> dict:
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
        if category:
            feed_repo.update_category(feed_id, category)

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
        """Refresh a single feed. Returns count of new articles. Tracks errors."""
        conn = self._conn()
        feed_repo = RssFeedRepository(conn)
        article_repo = RssArticleRepository(conn)

        feed = feed_repo.get_by_id(feed_id)
        if not feed:
            raise ValueError(f"Feed {feed_id} not found")

        try:
            feed_data = fetch_feed(feed.url)
        except Exception as e:
            feed_repo.update_error(feed_id, feed.error_count + 1, str(e)[:200])
            raise

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
        # Clear error state on success
        if feed.error_count > 0:
            feed_repo.clear_error(feed_id)
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

    def export_opml(self) -> str:
        """Export RSS subscriptions as OPML XML string."""
        conn = self._conn()
        feeds = RssFeedRepository(conn).list_all()

        # Group by category
        categories: dict[str, list] = {}
        for f in feeds:
            cat = f.category or ""
            categories.setdefault(cat, []).append(f)

        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<opml version="2.0">',
            '  <head><title>SnipNote RSS Subscriptions</title></head>',
            '  <body>',
        ]

        for cat, cat_feeds in sorted(categories.items(), key=lambda x: (x[0] == "", x[0])):
            if cat:
                cat_escaped = cat.replace('"', '&quot;')
                lines.append(f'    <outline text="{cat_escaped}" title="{cat_escaped}">')
                indent = '      '
            else:
                indent = '    '
            for f in cat_feeds:
                title = f.title.replace('"', '&quot;')
                url = f.url.replace('"', '&quot;')
                site = (f.site_url or '').replace('"', '&quot;')
                lines.append(
                    f'{indent}<outline type="rss" text="{title}" title="{title}" '
                    f'xmlUrl="{url}" htmlUrl="{site}"/>'
                )
            if cat:
                lines.append('    </outline>')

        lines += ['  </body>', '</opml>']
        return '\n'.join(lines)

    def import_opml(self, xml_content: str) -> list[str]:
        """Import RSS subscriptions from OPML. Returns list of feed URLs found."""
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as e:
            raise ValueError(f"OPML 解析失败: {e}")

        feed_urls = []
        for outline in root.iter('outline'):
            url = outline.get('xmlUrl') or outline.get('xmlurl')
            if url:
                feed_urls.append(url.strip())

        return feed_urls
