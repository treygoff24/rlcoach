# src/rlcoach/api/routers/__init__.py
"""API routers for RLCoach."""

from .analysis import router as analysis_router
from .dashboard import router as dashboard_router
from .games import router as games_router
from .players import router as players_router

__all__ = ["games_router", "dashboard_router", "analysis_router", "players_router"]
