# src/rlcoach/api/routers/dashboard.py
"""Dashboard API endpoints."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException

from ...db.session import create_session
from ...db.models import Replay, DailyStats, PlayerGameStats

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard")
async def get_dashboard() -> dict[str, Any]:
    """Get dashboard summary data.

    Returns today's stats, recent games, and quick stats.
    """
    today = date.today()

    session = create_session()
    try:
        # Get today's stats
        daily = session.query(DailyStats).filter_by(
            play_date=today,
            playlist="DOUBLES",
        ).first()

        today_stats = {}
        if daily:
            today_stats = {
                "games_played": daily.games_played,
                "wins": daily.wins,
                "losses": daily.losses,
                "draws": daily.draws,
                "win_rate": daily.win_rate,
            }

        # Get recent games (last 10)
        recent_replays = (
            session.query(Replay)
            .order_by(Replay.played_at_utc.desc())
            .limit(10)
            .all()
        )

        recent_games = []
        for r in recent_replays:
            recent_games.append({
                "replay_id": r.replay_id,
                "played_at_utc": r.played_at_utc.isoformat() if r.played_at_utc else None,
                "playlist": r.playlist,
                "result": r.result,
                "my_score": r.my_score,
                "opponent_score": r.opponent_score,
                "map": r.map,
            })

        # Quick stats (last 7 days average)
        quick_stats = {
            "avg_goals": 0.0,
            "avg_saves": 0.0,
            "avg_assists": 0.0,
        }

        # Get average stats from recent games
        if recent_replays:
            replay_ids = [r.replay_id for r in recent_replays]
            my_stats = (
                session.query(PlayerGameStats)
                .filter(
                    PlayerGameStats.replay_id.in_(replay_ids),
                    PlayerGameStats.is_me == True,
                )
                .all()
            )

            if my_stats:
                quick_stats["avg_goals"] = sum(s.goals or 0 for s in my_stats) / len(my_stats)
                quick_stats["avg_saves"] = sum(s.saves or 0 for s in my_stats) / len(my_stats)
                quick_stats["avg_assists"] = sum(s.assists or 0 for s in my_stats) / len(my_stats)

        return {
            "today": today_stats,
            "recent_games": recent_games,
            "quick_stats": quick_stats,
        }

    finally:
        session.close()
