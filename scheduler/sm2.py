"""SM-2 Spaced Repetition Algorithm Implementation.

This module provides an interface for different scheduling algorithms.
The SM-2 algorithm is the default implementation.
"""
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Protocol


class Scheduler(Protocol):
    """Protocol for review schedulers."""

    def next_schedule(self, repetitions: int, interval_days: int, efactor: float, quality: int) -> "ReviewResult":
        """Calculate next review schedule based on quality score."""
        ...


@dataclass
class ReviewResult:
    """Result of a review scheduling calculation."""
    repetitions: int
    interval_days: int
    efactor: float
    next_review: date


class SM2Scheduler:
    """SM-2 (SuperMemo 2) spaced repetition algorithm.

    The SM-2 algorithm calculates review intervals based on the quality
    of recall (0-5 scale).
    """

    @staticmethod
    def next_schedule(repetitions: int, interval_days: int, efactor: float, quality: int) -> ReviewResult:
        """Calculate the next schedule based on recall quality.

        Args:
            repetitions: Number of times the item has been reviewed
            interval_days: Current interval in days
            efactor: Easiness factor (default 2.5)
            quality: Quality of recall (0-5)
                0 - Complete blackout
                1 - Incorrect response, but upon seeing correct answer, remembered
                2 - Incorrect response, but correct answer seemed easy to recall
                3 - Correct response with serious difficulty
                4 - Correct response after hesitation
                5 - Perfect response

        Returns:
            ReviewResult with updated scheduling parameters
        """
        if quality < 3:
            # Failed recall - reset
            new_repetitions = 0
            new_interval_days = 1
        else:
            # Successful recall
            if repetitions == 0:
                new_interval_days = 1
            elif repetitions == 1:
                new_interval_days = 6
            else:
                new_interval_days = max(1, round(interval_days * efactor))
            new_repetitions = repetitions + 1

        # Update easiness factor
        new_efactor = efactor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
        new_efactor = max(1.3, new_efactor)

        return ReviewResult(
            repetitions=new_repetitions,
            interval_days=new_interval_days,
            efactor=new_efactor,
            next_review=date.today() + timedelta(days=new_interval_days),
        )


# Default scheduler instance
default_scheduler = SM2Scheduler()
