"""
rlcoach worker module for background replay processing.

This module provides Celery tasks for:
- Replay file parsing and analysis
- Database updates with parsed results
- Cold storage migration
"""

from rlcoach.worker.celery_app import celery_app

__all__ = ["celery_app"]
