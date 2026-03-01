#!/usr/bin/env python3
"""Backward compatibility wrapper for CLI.

This module provides backward compatibility for scripts that import from readlite.
"""
# Re-export from new modules
from pathlib import Path

from storage import connect, SCHEMA_SQL
from storage.repository import HighlightRepository, AnnotationRepository
from scheduler import SM2Scheduler

# Keep DEFAULT_DB at root level for backward compatibility
DEFAULT_DB = Path("data/readlite.db")

# Keep internal functions for backward compatibility
def _next_schedule(repetitions: int, interval_days: int, efactor: float, quality: int):
    """Backward compatible SM-2 schedule calculation."""
    result = SM2Scheduler.next_schedule(repetitions, interval_days, efactor, quality)
    return result.repetitions, result.interval_days, result.efactor


# CLI entry point
if __name__ == "__main__":
    from cli.main import main
    main()
