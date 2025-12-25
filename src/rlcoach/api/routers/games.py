# src/rlcoach/api/routers/games.py
"""Games and replays API endpoints."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from ...db.models import PlayerGameStats, Replay
from ...db.session import create_session

router = APIRouter(tags=["games"])


@router.get("/games")
async def list_games(
    playlist: str | None = None,
    result: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    sort: str = Query(default="-played_at_utc"),
) -> dict[str, Any]:
    """List games with filtering and pagination.

    Args:
        playlist: Filter by playlist (e.g., DOUBLES, STANDARD)
        result: Filter by result (WIN, LOSS, DRAW)
        date_from: Filter games from this date
        date_to: Filter games up to this date
        limit: Maximum number of games to return
        offset: Number of games to skip
        sort: Sort field (prefix with - for descending)
    """
    session = create_session()
    try:
        query = session.query(Replay)

        # Apply filters
        if playlist:
            query = query.filter(Replay.playlist == playlist)
        if result:
            query = query.filter(Replay.result == result)
        if date_from:
            query = query.filter(Replay.play_date >= date_from)
        if date_to:
            query = query.filter(Replay.play_date <= date_to)

        # Get total count before pagination
        total = query.count()

        # Apply sorting
        if sort.startswith("-"):
            sort_field = sort[1:]
            descending = True
        else:
            sort_field = sort
            descending = False

        if hasattr(Replay, sort_field):
            order_col = getattr(Replay, sort_field)
            query = query.order_by(order_col.desc() if descending else order_col)

        # Apply pagination
        replays = query.offset(offset).limit(limit).all()

        items = []
        for r in replays:
            items.append(
                {
                    "replay_id": r.replay_id,
                    "played_at_utc": (
                        r.played_at_utc.isoformat() if r.played_at_utc else None
                    ),
                    "play_date": r.play_date.isoformat() if r.play_date else None,
                    "playlist": r.playlist,
                    "result": r.result,
                    "my_score": r.my_score,
                    "opponent_score": r.opponent_score,
                    "map": r.map,
                    "duration_seconds": r.duration_seconds,
                    "overtime": r.overtime,
                }
            )

        return {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    finally:
        session.close()


@router.get("/replays/{replay_id}")
async def get_replay(replay_id: str) -> dict[str, Any]:
    """Get replay details by ID.

    Args:
        replay_id: The replay ID
    """
    session = create_session()
    try:
        replay = session.get(Replay, replay_id)
        if not replay:
            raise HTTPException(status_code=404, detail="Replay not found")

        # Get player stats
        stats = (
            session.query(PlayerGameStats)
            .filter(PlayerGameStats.replay_id == replay_id)
            .all()
        )

        player_stats = []
        for s in stats:
            player_stats.append(
                {
                    "player_id": s.player_id,
                    "team": s.team,
                    "is_me": s.is_me,
                    "goals": s.goals,
                    "assists": s.assists,
                    "saves": s.saves,
                    "shots": s.shots,
                    "bcpm": s.bcpm,
                    "avg_boost": s.avg_boost,
                }
            )

        return {
            "replay_id": replay.replay_id,
            "played_at_utc": (
                replay.played_at_utc.isoformat() if replay.played_at_utc else None
            ),
            "play_date": replay.play_date.isoformat() if replay.play_date else None,
            "playlist": replay.playlist,
            "result": replay.result,
            "my_score": replay.my_score,
            "opponent_score": replay.opponent_score,
            "map": replay.map,
            "duration_seconds": replay.duration_seconds,
            "overtime": replay.overtime,
            "my_team": replay.my_team,
            "player_stats": player_stats,
        }

    finally:
        session.close()


@router.get("/replays/{replay_id}/full")
async def get_replay_full(replay_id: str) -> dict[str, Any]:
    """Get complete replay data including all stats.

    Args:
        replay_id: The replay ID
    """
    session = create_session()
    try:
        replay = session.get(Replay, replay_id)
        if not replay:
            raise HTTPException(status_code=404, detail="Replay not found")

        # Get all player stats
        stats = (
            session.query(PlayerGameStats)
            .filter(PlayerGameStats.replay_id == replay_id)
            .all()
        )

        player_stats = []
        for s in stats:
            stat_dict = {
                "player_id": s.player_id,
                "team": s.team,
                "is_me": s.is_me,
                # Fundamentals
                "goals": s.goals,
                "assists": s.assists,
                "saves": s.saves,
                "shots": s.shots,
                "shooting_pct": s.shooting_pct,
                "score": s.score,
                "demos_inflicted": s.demos_inflicted,
                "demos_taken": s.demos_taken,
                # Boost
                "bcpm": s.bcpm,
                "avg_boost": s.avg_boost,
                "time_zero_boost_s": s.time_zero_boost_s,
                "time_full_boost_s": s.time_full_boost_s,
                "boost_collected": s.boost_collected,
                "boost_stolen": s.boost_stolen,
                # Movement
                "avg_speed_kph": s.avg_speed_kph,
                "time_supersonic_s": s.time_supersonic_s,
                # Positioning
                "behind_ball_pct": s.behind_ball_pct,
                "first_man_pct": s.first_man_pct,
                "second_man_pct": s.second_man_pct,
                "third_man_pct": s.third_man_pct,
            }
            player_stats.append(stat_dict)

        replay_data = {
            "replay_id": replay.replay_id,
            "source_file": replay.source_file,
            "file_hash": replay.file_hash,
            "played_at_utc": (
                replay.played_at_utc.isoformat() if replay.played_at_utc else None
            ),
            "play_date": replay.play_date.isoformat() if replay.play_date else None,
            "playlist": replay.playlist,
            "team_size": replay.team_size,
            "result": replay.result,
            "my_score": replay.my_score,
            "opponent_score": replay.opponent_score,
            "map": replay.map,
            "duration_seconds": replay.duration_seconds,
            "overtime": replay.overtime,
            "my_team": replay.my_team,
            "my_player_id": replay.my_player_id,
        }

        return {
            "replay": replay_data,
            "player_stats": player_stats,
        }

    finally:
        session.close()
