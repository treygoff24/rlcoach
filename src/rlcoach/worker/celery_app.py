"""Celery application configuration."""

import os

from celery import Celery

# Redis URL from environment
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "rlcoach",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["rlcoach.worker.tasks"],
)

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Task execution settings
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_time_limit=60,  # Hard limit: 60 seconds
    task_soft_time_limit=30,  # Soft limit: 30 seconds
    # Worker settings
    worker_prefetch_multiplier=1,  # Fair scheduling
    worker_max_tasks_per_child=100,  # Restart after 100 tasks
    worker_concurrency=4,  # Match CPU cores for parsing
    # Result backend settings
    result_expires=3600,  # Results expire after 1 hour
    # Task routing
    task_routes={
        "rlcoach.worker.tasks.process_replay": {"queue": "replay_processing"},
        "rlcoach.worker.tasks.migrate_to_cold_storage": {"queue": "cold_storage"},
    },
    # Rate limiting
    task_annotations={
        "rlcoach.worker.tasks.process_replay": {
            "rate_limit": "100/h",  # Max 100 per hour per worker
        },
    },
    # Celery Beat schedule (periodic tasks)
    beat_schedule={
        "process-scheduled-deletions-daily": {
            "task": "rlcoach.worker.tasks.process_scheduled_deletions",
            "schedule": 86400.0,  # Every 24 hours (in seconds)
            "options": {"queue": "maintenance"},
        },
    },
)
