"""Podcast Service - show management, sync, and playback tracking."""

from pathlib import Path

from storage import connect
from podcast.parser import fetch_podcast
from podcast.repository import PodcastShowRepository, PodcastEpisodeRepository


class PodcastService:
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)

    def _conn(self):
        return connect(self.db_path)

    def subscribe(self, feed_url: str) -> dict:
        """Subscribe to a podcast feed. Fetches metadata and initial episodes."""
        conn = self._conn()
        show_repo = PodcastShowRepository(conn)

        existing = show_repo.get_by_url(feed_url)
        if existing:
            return {"show_id": existing.id, "title": existing.title, "new_episodes": 0, "already_subscribed": True}

        show_data = fetch_podcast(feed_url)
        show_id = show_repo.add(
            title=show_data.title or feed_url,
            url=feed_url,
            site_url=show_data.site_url,
            description=show_data.description,
            image_url=show_data.image_url,
            author=show_data.author,
            language=show_data.language,
        )

        ep_repo = PodcastEpisodeRepository(conn)
        count = 0
        for ep in show_data.episodes:
            if not ep.audio_url or ep_repo.guid_exists(show_id, ep.guid):
                continue
            ep_repo.add(
                show_id=show_id,
                title=ep.title,
                guid=ep.guid,
                audio_url=ep.audio_url,
                audio_type=ep.audio_type,
                audio_length=ep.audio_length,
                description=ep.description,
                image_url=ep.image_url,
                author=ep.author,
                duration=ep.duration,
                duration_seconds=ep.duration_seconds,
                episode_number=ep.episode_number,
                season_number=ep.season_number,
                published_at=ep.published_at,
            )
            count += 1

        show_repo.update_last_fetched(show_id)
        return {"show_id": show_id, "title": show_data.title, "new_episodes": count, "already_subscribed": False}

    def unsubscribe(self, show_id: int) -> None:
        conn = self._conn()
        PodcastShowRepository(conn).delete(show_id)

    def refresh_show(self, show_id: int) -> int:
        """Refresh a single podcast show. Returns count of new episodes."""
        conn = self._conn()
        show_repo = PodcastShowRepository(conn)
        ep_repo = PodcastEpisodeRepository(conn)

        show = show_repo.get_by_id(show_id)
        if not show:
            raise ValueError(f"Show {show_id} not found")

        show_data = fetch_podcast(show.url)
        count = 0
        for ep in show_data.episodes:
            if not ep.audio_url or ep_repo.guid_exists(show_id, ep.guid):
                continue
            ep_repo.add(
                show_id=show_id,
                title=ep.title,
                guid=ep.guid,
                audio_url=ep.audio_url,
                audio_type=ep.audio_type,
                audio_length=ep.audio_length,
                description=ep.description,
                image_url=ep.image_url,
                author=ep.author,
                duration=ep.duration,
                duration_seconds=ep.duration_seconds,
                episode_number=ep.episode_number,
                season_number=ep.season_number,
                published_at=ep.published_at,
            )
            count += 1

        show_repo.update_last_fetched(show_id)
        return count

    def refresh_all(self) -> dict:
        """Refresh all podcast shows. Returns {show_id: new_episode_count}."""
        conn = self._conn()
        shows = PodcastShowRepository(conn).list_all()
        results = {}
        for show in shows:
            try:
                results[show.id] = self.refresh_show(show.id)
            except Exception:
                results[show.id] = 0
        return results

    def toggle_listened(self, episode_id: int) -> dict:
        """Toggle listened status. Returns {id, is_listened}."""
        conn = self._conn()
        ep_repo = PodcastEpisodeRepository(conn)
        ep = ep_repo.get_by_id(episode_id)
        if not ep:
            raise ValueError(f"Episode {episode_id} not found")
        new_status = 0 if ep.is_listened else 1
        ep_repo.mark_listened(episode_id, new_status)
        return {"id": episode_id, "is_listened": new_status}

    def update_play_progress(self, episode_id: int, position_seconds: int) -> None:
        """Update playback position for an episode."""
        conn = self._conn()
        PodcastEpisodeRepository(conn).update_play_position(episode_id, position_seconds)
