import unittest
from datetime import date

from core import Highlight, Annotation, ReviewSchedule


class TestHighlight(unittest.TestCase):
    """Tests for Highlight domain model."""

    def test_default_values(self):
        """Highlight should have correct default values."""
        h = Highlight()

        self.assertIsNone(h.id)
        self.assertEqual(h.text, "")
        self.assertEqual(h.source, "")
        self.assertEqual(h.author, "")
        self.assertEqual(h.location, "")
        self.assertEqual(h.tags, "")
        self.assertEqual(h.created_at, "")
        self.assertIsNone(h.last_reviewed)
        self.assertEqual(h.next_review, "")
        self.assertEqual(h.favorite, 0)
        self.assertEqual(h.is_read, 0)
        self.assertEqual(h.repetitions, 0)
        self.assertEqual(h.interval_days, 0)
        self.assertEqual(h.efactor, 2.5)

    def test_with_values(self):
        """Highlight should accept custom values."""
        h = Highlight(
            id=1,
            text="Test text",
            source="Test Book",
            author="Test Author",
            location="Chapter 1",
            tags="python,test",
            created_at="2024-01-01T00:00:00",
            last_reviewed="2024-01-02T00:00:00",
            next_review="2024-01-03",
            favorite=1,
            is_read=1,
            repetitions=3,
            interval_days=7,
            efactor=2.6
        )

        self.assertEqual(h.id, 1)
        self.assertEqual(h.text, "Test text")
        self.assertEqual(h.source, "Test Book")
        self.assertEqual(h.author, "Test Author")
        self.assertEqual(h.location, "Chapter 1")
        self.assertEqual(h.tags, "python,test")
        self.assertEqual(h.favorite, 1)
        self.assertEqual(h.is_read, 1)
        self.assertEqual(h.repetitions, 3)
        self.assertEqual(h.interval_days, 7)
        self.assertEqual(h.efactor, 2.6)


class TestAnnotation(unittest.TestCase):
    """Tests for Annotation domain model."""

    def test_default_values(self):
        """Annotation should have correct default values."""
        a = Annotation()

        self.assertIsNone(a.id)
        self.assertEqual(a.highlight_id, 0)
        self.assertEqual(a.selected_text, "")
        self.assertEqual(a.note, "")
        self.assertEqual(a.created_at, "")

    def test_with_values(self):
        """Annotation should accept custom values."""
        a = Annotation(
            id=1,
            highlight_id=5,
            selected_text="Important text",
            note="My thoughts",
            created_at="2024-01-01T00:00:00"
        )

        self.assertEqual(a.id, 1)
        self.assertEqual(a.highlight_id, 5)
        self.assertEqual(a.selected_text, "Important text")
        self.assertEqual(a.note, "My thoughts")


class TestReviewSchedule(unittest.TestCase):
    """Tests for ReviewSchedule domain model."""

    def test_default_values(self):
        """ReviewSchedule should have correct default values."""
        rs = ReviewSchedule()

        self.assertEqual(rs.repetitions, 0)
        self.assertEqual(rs.interval_days, 0)
        self.assertEqual(rs.efactor, 2.5)
        self.assertEqual(rs.next_review, date.today())

    def test_with_values(self):
        """ReviewSchedule should accept custom values."""
        next_date = date(2024, 1, 15)
        rs = ReviewSchedule(
            repetitions=3,
            interval_days=7,
            efactor=2.6,
            next_review=next_date
        )

        self.assertEqual(rs.repetitions, 3)
        self.assertEqual(rs.interval_days, 7)
        self.assertEqual(rs.efactor, 2.6)
        self.assertEqual(rs.next_review, next_date)


if __name__ == "__main__":
    unittest.main()
