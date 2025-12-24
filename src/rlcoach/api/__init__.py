# src/rlcoach/api/__init__.py
"""FastAPI REST API for RLCoach."""

from .app import create_app

__all__ = ["create_app"]
