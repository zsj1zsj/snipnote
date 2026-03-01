import unittest
from datetime import date, timedelta

from scheduler.sm2 import SM2Scheduler, ReviewResult


class TestSM2Scheduler(unittest.TestCase):
    """Tests for SM-2 spaced repetition algorithm."""

    def test_first_review_quality_5(self):
        """First successful review with quality 5 should set interval to 1 day."""
        result = SM2Scheduler.next_schedule(repetitions=0, interval_days=0, efactor=2.5, quality=5)

        self.assertEqual(result.repetitions, 1)
        self.assertEqual(result.interval_days, 1)
        self.assertEqual(result.next_review, date.today() + timedelta(days=1))

    def test_second_review_quality_5(self):
        """Second successful review with quality 5 should set interval to 6 days."""
        result = SM2Scheduler.next_schedule(repetitions=1, interval_days=1, efactor=2.5, quality=5)

        self.assertEqual(result.repetitions, 2)
        self.assertEqual(result.interval_days, 6)
        self.assertEqual(result.next_review, date.today() + timedelta(days=6))

    def test_third_review_quality_5(self):
        """Third+ successful review should multiply interval by efactor."""
        # interval = 6, efactor = 2.5 -> 6 * 2.5 = 15
        result = SM2Scheduler.next_schedule(repetitions=2, interval_days=6, efactor=2.5, quality=5)

        self.assertEqual(result.repetitions, 3)
        self.assertEqual(result.interval_days, 15)
        self.assertEqual(result.next_review, date.today() + timedelta(days=15))

    def test_failed_review_quality_2_resets(self):
        """Failed recall (quality < 3) should reset repetitions and interval."""
        result = SM2Scheduler.next_schedule(repetitions=5, interval_days=30, efactor=2.6, quality=2)

        self.assertEqual(result.repetitions, 0)
        self.assertEqual(result.interval_days, 1)
        self.assertEqual(result.next_review, date.today() + timedelta(days=1))

    def test_quality_3_minimum_interval(self):
        """Quality 3 is the minimum for successful recall."""
        result = SM2Scheduler.next_schedule(repetitions=0, interval_days=0, efactor=2.5, quality=3)

        self.assertEqual(result.repetitions, 1)
        self.assertEqual(result.interval_days, 1)

    def test_efactor_minimum_1_3(self):
        """E-factor should never go below 1.3."""
        # Quality 0 gives very low efactor calculation
        result = SM2Scheduler.next_schedule(repetitions=0, interval_days=0, efactor=1.3, quality=0)

        self.assertGreaterEqual(result.efactor, 1.3)

    def test_efactor_increases_with_higher_quality(self):
        """Higher quality should result in higher efactor."""
        result_3 = SM2Scheduler.next_schedule(repetitions=0, interval_days=0, efactor=2.5, quality=3)
        result_5 = SM2Scheduler.next_schedule(repetitions=0, interval_days=0, efactor=2.5, quality=5)

        self.assertGreater(result_5.efactor, result_3.efactor)

    def test_review_result_type(self):
        """Result should be a ReviewResult dataclass."""
        result = SM2Scheduler.next_schedule(repetitions=0, interval_days=0, efactor=2.5, quality=5)

        self.assertIsInstance(result, ReviewResult)
        self.assertIsInstance(result.next_review, date)


if __name__ == "__main__":
    unittest.main()
