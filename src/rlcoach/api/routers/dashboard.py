# src/rlcoach/api/routers/dashboard.py
"""Dashboard API endpoints."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from ...db import UserReplay, get_session
from ...db.models import PlayerGameStats, Replay
from ..auth import AuthenticatedUser

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard")
async def get_dashboard(
    user: AuthenticatedUser,
    db: Annotated[DBSession, Depends(get_session)],
) -> dict[str, Any]:
    """Get dashboard summary data.

    Returns today's stats, recent games, and quick stats.
    Requires authentication.
    """
    today = date.today()

    # Select replay IDs belonging to this user
    user_replay_ids = select(UserReplay.replay_id).where(UserReplay.user_id == user.id)

    # Compute today's stats from user's replays (DailyStats is global, not per-user)
    today_replays = (
        db.query(Replay)
        .filter(
            Replay.replay_id.in_(user_replay_ids),
            Replay.play_date == today,
        )
        .all()
    )

    today_stats: dict[str, Any] = {}
    if today_replays:
        wins = sum(1 for r in today_replays if r.result == "WIN")
        losses = sum(1 for r in today_replays if r.result == "LOSS")
        draws = sum(1 for r in today_replays if r.result == "DRAW")
        games_played = len(today_replays)
        today_stats = {
            "games_played": games_played,
            "wins": wins,
            "losses": losses,
            "draws": draws,
            "win_rate": round(wins / games_played * 100, 1) if games_played else 0.0,
        }

    # Get recent games (last 10) scoped to this user
    recent_replays = (
        db.query(Replay)
        .filter(Replay.replay_id.in_(user_replay_ids))
        .order_by(Replay.played_at_utc.desc())
        .limit(10)
        .all()
    )

    recent_games = []
    for r in recent_replays:
        recent_games.append(
            {
                "replay_id": r.replay_id,
                "played_at_utc": (
                    r.played_at_utc.isoformat() if r.played_at_utc else None
                ),
                "playlist": r.playlist,
                "result": r.result,
                "my_score": r.my_score,
                "opponent_score": r.opponent_score,
                "map": r.map,
            }
        )

    # Quick stats (last 7 days average) for this user only
    quick_stats: dict[str, Any] = {
        "avg_goals": 0.0,
        "avg_saves": 0.0,
        "avg_assists": 0.0,
    }

    if recent_replays:
        replay_ids = [r.replay_id for r in recent_replays]
        my_stats = (
            db.query(PlayerGameStats)
            .filter(
                PlayerGameStats.replay_id.in_(replay_ids),
                PlayerGameStats.is_me,
            )
            .all()
        )

        if my_stats:
            quick_stats["avg_goals"] = sum(s.goals or 0 for s in my_stats) / len(
                my_stats
            )
            quick_stats["avg_saves"] = sum(s.saves or 0 for s in my_stats) / len(
                my_stats
            )
            quick_stats["avg_assists"] = sum(s.assists or 0 for s in my_stats) / len(
                my_stats
            )

    return {
        "today": today_stats,
        "recent_games": recent_games,
        "quick_stats": quick_stats,
    }
