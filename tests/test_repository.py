import os
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from storage.db import connect
from storage.repository import HighlightRepository, AnnotationRepository


class TestHighlightRepository(unittest.TestCase):
    """Tests for HighlightRepository."""

    @classmethod
    def setUpClass(cls):
        """Create a temporary database for testing."""
        cls.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        cls.temp_db.close()
        cls.conn = connect(Path(cls.temp_db.name))
        cls.repo = HighlightRepository(cls.conn)

    @classmethod
    def tearDownClass(cls):
        """Clean up temporary database."""
        cls.conn.close()
        os.unlink(cls.temp_db.name)

    def setUp(self):
        """Clear highlights before each test."""
        self.conn.execute("DELETE FROM highlights")
        self.conn.commit()

    def test_add_single_highlight(self):
        """Should add a single highlight and return its ID."""
        highlight_id = self.repo.add(
            text="Test highlight",
            source="Test Source",
            author="Test Author",
            tags="test,example"
        )

        self.assertIsNotNone(highlight_id)
        self.assertGreater(highlight_id, 0)

    def test_get_by_id(self):
        """Should retrieve a highlight by ID."""
        highlight_id = self.repo.add(text="Test highlight")
        highlight = self.repo.get_by_id(highlight_id)

        self.assertIsNotNone(highlight)
        self.assertEqual(highlight.id, highlight_id)
        self.assertEqual(highlight.text, "Test highlight")

    def test_get_by_id_not_found(self):
        """Should return None for non-existent ID."""
        highlight = self.repo.get_by_id(99999)
        self.assertIsNone(highlight)

    def test_list_all(self):
        """Should list all highlights."""
        self.repo.add(text="First")
        self.repo.add(text="Second")
        self.repo.add(text="Third")

        highlights = self.repo.list_all()

        self.assertEqual(len(highlights), 3)

    def test_list_all_with_limit(self):
        """Should respect limit parameter."""
        for i in range(10):
            self.repo.add(text=f"Highlight {i}")

        highlights = self.repo.list_all(limit=5)

        self.assertEqual(len(highlights), 5)

    def test_add_batch(self):
        """Should batch add multiple highlights."""
        items = [
            ("Text 1", "Source 1", "Author 1", "", "tag1"),
            ("Text 2", "Source 2", "Author 2", "", "tag2"),
            ("Text 3", "Source 3", "Author 3", "", "tag3"),
        ]

        count = self.repo.add_batch(items)

        self.assertEqual(count, 3)
        highlights = self.repo.list_all()
        self.assertEqual(len(highlights), 3)

    def test_add_batch_empty(self):
        """Should return 0 for empty list."""
        count = self.repo.add_batch([])
        self.assertEqual(count, 0)

    def test_update_favorite(self):
        """Should toggle favorite status."""
        highlight_id = self.repo.add(text="Test")
        self.repo.update_favorite(highlight_id, 1)

        highlight = self.repo.get_by_id(highlight_id)
        self.assertEqual(highlight.favorite, 1)

        self.repo.update_favorite(highlight_id, 0)
        highlight = self.repo.get_by_id(highlight_id)
        self.assertEqual(highlight.favorite, 0)

    def test_update_is_read(self):
        """Should toggle read status."""
        highlight_id = self.repo.add(text="Test")
        self.repo.update_is_read(highlight_id, 1)

        highlight = self.repo.get_by_id(highlight_id)
        self.assertEqual(highlight.is_read, 1)

    def test_delete(self):
        """Should delete a highlight."""
        highlight_id = self.repo.add(text="Test to delete")
        self.repo.delete(highlight_id)

        highlight = self.repo.get_by_id(highlight_id)
        self.assertIsNone(highlight)

    def test_search_by_keyword(self):
        """Should search by keyword."""
        self.repo.add(text="Python is awesome")
        self.repo.add(text="Java is good")
        self.repo.add(text="Python rules")

        results = self.repo.search(keyword="Python")

        self.assertEqual(len(results), 2)

    def test_search_by_tag(self):
        """Should search by tag."""
        self.repo.add(text="Highlight 1", tags="python,coding")
        self.repo.add(text="Highlight 2", tags="java,coding")
        self.repo.add(text="Highlight 3", tags="python")

        results = self.repo.search(tag="python")

        self.assertEqual(len(results), 2)

    def test_search_read_filter(self):
        """Should filter by read status."""
        id1 = self.repo.add(text="Unread 1")
        id2 = self.repo.add(text="Read 1")
        self.repo.update_is_read(id2, 1)

        unread = self.repo.search(read_filter="unread")
        read = self.repo.search(read_filter="read")

        self.assertEqual(len(unread), 1)
        self.assertEqual(unread[0].id, id1)
        self.assertEqual(len(read), 1)
        self.assertEqual(read[0].id, id2)

    def test_get_favorites(self):
        """Should get favorite highlights."""
        id1 = self.repo.add(text="Favorite 1")
        id2 = self.repo.add(text="Not favorite")
        self.repo.update_favorite(id1, 1)

        favorites = self.repo.get_favorites()

        self.assertEqual(len(favorites), 1)
        self.assertEqual(favorites[0].id, id1)

    def test_url_exists(self):
        """Should check if URL already exists."""
        url = "https://example.com/article"
        self.repo.add(text="Existing article", location=url)

        exists = self.repo.url_exists(url)
        self.assertIsNotNone(exists)

        not_exists = self.repo.url_exists("https://example.com/nonexistent")
        self.assertIsNone(not_exists)

    def test_update_review(self):
        """Should update review scheduling data."""
        highlight_id = self.repo.add(text="Test")
        next_date = date.today() + timedelta(days=7)

        self.repo.update_review(highlight_id, repetitions=3, interval_days=7, efactor=2.5, next_review=next_date)

        highlight = self.repo.get_by_id(highlight_id)
        self.assertEqual(highlight.repetitions, 3)
        self.assertEqual(highlight.interval_days, 7)
        self.assertEqual(highlight.efactor, 2.5)


class TestAnnotationRepository(unittest.TestCase):
    """Tests for AnnotationRepository."""

    @classmethod
    def setUpClass(cls):
        """Create a temporary database for testing."""
        cls.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        cls.temp_db.close()
        cls.conn = connect(Path(cls.temp_db.name))
        cls.repo = AnnotationRepository(cls.conn)
        cls.highlight_repo = HighlightRepository(cls.conn)

    @classmethod
    def tearDownClass(cls):
        """Clean up temporary database."""
        cls.conn.close()
        os.unlink(cls.temp_db.name)

    def setUp(self):
        """Clear data before each test."""
        self.conn.execute("DELETE FROM annotations")
        self.conn.execute("DELETE FROM highlights")
        self.conn.commit()

    def test_add_annotation(self):
        """Should add an annotation."""
        highlight_id = self.highlight_repo.add(text="Test highlight")
        annotation_id = self.repo.add(
            highlight_id=highlight_id,
            selected_text="Selected text",
            note="My note"
        )

        self.assertIsNotNone(annotation_id)
        self.assertGreater(annotation_id, 0)

    def test_get_by_highlight(self):
        """Should get annotations for a highlight."""
        highlight_id = self.highlight_repo.add(text="Test highlight")
        self.repo.add(highlight_id=highlight_id, note="Note 1")
        self.repo.add(highlight_id=highlight_id, note="Note 2")

        annotations = self.repo.get_by_highlight(highlight_id)

        self.assertEqual(len(annotations), 2)

    def test_update_note(self):
        """Should update annotation note."""
        highlight_id = self.highlight_repo.add(text="Test highlight")
        annotation_id = self.repo.add(highlight_id=highlight_id, note="Original")

        self.repo.update_note(annotation_id, "Updated note")

        annotations = self.repo.get_by_highlight(highlight_id)
        self.assertEqual(annotations[0].note, "Updated note")

    def test_delete_annotation(self):
        """Should delete an annotation."""
        highlight_id = self.highlight_repo.add(text="Test highlight")
        annotation_id = self.repo.add(highlight_id=highlight_id, note="To delete")

        self.repo.delete(annotation_id)

        annotations = self.repo.get_by_highlight(highlight_id)
        self.assertEqual(len(annotations), 0)

    def test_cascade_delete(self):
        """Deleting highlight should cascade delete annotations."""
        highlight_id = self.highlight_repo.add(text="Test highlight")
        self.repo.add(highlight_id=highlight_id, note="Note")
        self.highlight_repo.delete(highlight_id)

        annotations = self.repo.get_by_highlight(highlight_id)
        self.assertEqual(len(annotations), 0)


if __name__ == "__main__":
    unittest.main()
