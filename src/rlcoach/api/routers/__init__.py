# src/rlcoach/api/routers/__init__.py
"""API routers for RLCoach."""

from .analysis import router as analysis_router
from .coach import router as coach_router
from .dashboard import router as dashboard_router
from .games import router as games_router
from .players import router as players_router
from .replays import router as replays_router
from .users import router as users_router

__all__ = [
    "analysis_router",
    "coach_router",
    "dashboard_router",
    "games_router",
    "players_router",
    "replays_router",
    "users_router",
]
