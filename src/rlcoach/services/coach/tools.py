# src/rlcoach/services/coach/tools.py
"""Data access tools for AI Coach."""

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session as DBSession

from ...db.models import CoachNote, PlayerGameStats, Replay, UserReplay
from .prompts import MAX_NOTE_LENGTH, sanitize_user_content


def get_data_tools():
    """Get the list of available tools for Claude."""
    from .prompts import get_tool_descriptions

    return get_tool_descriptions()


async def execute_tool(
    tool_name: str,
    tool_input: dict[str, Any],
    user_id: str,
    db: DBSession,
) -> str:
    """Execute a tool and return the result as a string.

    Args:
        tool_name: Name of the tool to execute
        tool_input: Tool input parameters
        user_id: Current user's ID
        db: Database session

    Returns:
        JSON string with tool results
    """
    handlers = {
        "get_recent_games": _get_recent_games,
        "get_stats_by_mode": _get_stats_by_mode,
        "get_game_details": _get_game_details,
        "get_rank_benchmarks": _get_rank_benchmarks,
        "save_coaching_note": _save_coaching_note,
    }

    handler = handlers.get(tool_name)
    if not handler:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})

    try:
        result = await handler(tool_input, user_id, db)
        return json.dumps(result, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


async def _get_recent_games(
    params: dict[str, Any],
    user_id: str,
    db: DBSession,
) -> dict:
    """Fetch recent games for the user."""
    limit = min(params.get("limit", 10), 50)
    playlist = params.get("playlist")

    # Get replay IDs owned by user through UserReplay join table
    user_replay_ids = (
        db.query(UserReplay.replay_id).filter(UserReplay.user_id == user_id).subquery()
    )

    query = db.query(Replay).filter(Replay.replay_id.in_(user_replay_ids))

    if playlist:
        query = query.filter(Replay.playlist == playlist)

    replays = query.order_by(Replay.played_at_utc.desc()).limit(limit).all()

    if not replays:
        return {
            "games": [],
            "message": "No recent games found. Upload some replays to get started!",
        }

    # Batch load all player stats in one query (avoid N+1)
    replay_ids = [r.replay_id for r in replays]
    stats_by_replay = _get_my_player_stats_batch(db, replay_ids)

    games = []
    for replay in replays:
        player_stats = stats_by_replay.get(replay.replay_id, {})

        games.append(
            {
                "id": replay.replay_id,
                "date": (
                    replay.played_at_utc.isoformat() if replay.played_at_utc else None
                ),
                "playlist": replay.playlist,
                "result": replay.result,
                "score": f"{replay.my_score or 0}-{replay.opponent_score or 0}",
                "map": replay.map,
                "stats": player_stats,
            }
        )

    return {
        "games": games,
        "total": len(games),
    }


async def _get_stats_by_mode(
    params: dict[str, Any],
    user_id: str,
    db: DBSession,
) -> dict:
    """Get aggregated stats by game mode."""
    mode = params.get("mode", "all")
    days = params.get("days", 30)

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Get replay IDs owned by user
    user_replay_ids = (
        db.query(UserReplay.replay_id).filter(UserReplay.user_id == user_id).subquery()
    )

    query = db.query(Replay).filter(
        Replay.replay_id.in_(user_replay_ids),
        Replay.played_at_utc >= cutoff,
    )

    if mode != "all":
        # Playlist values stored as uppercase enums (DUEL, DOUBLES, STANDARD)
        playlist_map = {
            "duel": "DUEL",
            "doubles": "DOUBLES",
            "standard": "STANDARD",
        }
        # Use map for known modes, fall back to uppercase for others (rumble, hoops)
        query = query.filter(Replay.playlist == playlist_map.get(mode, mode.upper()))

    replays = query.all()

    if not replays:
        return {
            "mode": mode,
            "period_days": days,
            "games": 0,
            "message": f"No games found in {mode} mode over the last {days} days.",
        }

    # Batch load all player stats in one query (avoid N+1)
    replay_ids = [r.replay_id for r in replays]
    stats_by_replay = _get_my_player_stats_batch(db, replay_ids)

    # Aggregate stats from PlayerGameStats
    stats = {
        "goals": 0,
        "assists": 0,
        "saves": 0,
        "shots": 0,
        "wins": 0,
        "losses": 0,
    }

    for replay in replays:
        player_stats = stats_by_replay.get(replay.replay_id, {})

        stats["goals"] += player_stats.get("goals", 0)
        stats["assists"] += player_stats.get("assists", 0)
        stats["saves"] += player_stats.get("saves", 0)
        stats["shots"] += player_stats.get("shots", 0)

        if replay.result == "WIN":
            stats["wins"] += 1
        elif replay.result == "LOSS":
            stats["losses"] += 1

    total_games = len(replays)
    win_rate = (stats["wins"] / total_games * 100) if total_games > 0 else 0

    return {
        "mode": mode,
        "period_days": days,
        "games": total_games,
        "win_rate": round(win_rate, 1),
        "per_game_averages": {
            "goals": round(stats["goals"] / total_games, 2) if total_games > 0 else 0,
            "assists": (
                round(stats["assists"] / total_games, 2) if total_games > 0 else 0
            ),
            "saves": round(stats["saves"] / total_games, 2) if total_games > 0 else 0,
            "shots": round(stats["shots"] / total_games, 2) if total_games > 0 else 0,
        },
        "totals": stats,
    }


async def _get_game_details(
    params: dict[str, Any],
    user_id: str,
    db: DBSession,
) -> dict:
    """Get detailed analysis of a specific game."""
    game_id = params.get("game_id")

    if not game_id:
        return {"error": "game_id is required"}

    # Check user owns this replay
    ownership = (
        db.query(UserReplay)
        .filter(
            UserReplay.replay_id == game_id,
            UserReplay.user_id == user_id,
        )
        .first()
    )

    if not ownership:
        return {"error": f"Game {game_id} not found"}

    replay = db.query(Replay).filter(Replay.replay_id == game_id).first()
    if not replay:
        return {"error": f"Game {game_id} not found"}

    player_stats = _get_my_player_stats(db, replay.replay_id)

    return {
        "id": replay.replay_id,
        "date": replay.played_at_utc.isoformat() if replay.played_at_utc else None,
        "playlist": replay.playlist,
        "result": replay.result,
        "score": f"{replay.my_score or 0}-{replay.opponent_score or 0}",
        "duration_seconds": replay.duration_seconds,
        "map": replay.map,
        "player_stats": player_stats,
    }


async def _get_rank_benchmarks(
    params: dict[str, Any],
    user_id: str,
    db: DBSession,
) -> dict:
    """Get benchmark stats for a rank from the rank_benchmarks module."""
    from ...rank_benchmarks import (
        RANK_DISPLAY_NAMES,
        get_benchmark_for_rank,
    )

    rank = params.get("rank", "Diamond I")
    mode = params.get("mode", "standard")

    rank_name_to_tier = {v: k for k, v in RANK_DISPLAY_NAMES.items()}
    rank_tier = rank_name_to_tier.get(rank)
    if rank_tier is None:
        rank_base = rank.split()[0] if " " in rank else rank
        for name, tier in rank_name_to_tier.items():
            if name.startswith(rank_base):
                rank_tier = tier
                break
    if rank_tier is None:
        rank_tier = 13  # Default to Diamond I

    benchmark = get_benchmark_for_rank(rank_tier)
    if not benchmark:
        benchmark = get_benchmark_for_rank(13)

    return {
        "rank": benchmark.rank_name,
        "rank_tier": benchmark.rank_tier,
        "mode": mode,
        "benchmarks": {
            "goals_per_game": benchmark.goals_per_game,
            "assists_per_game": benchmark.assists_per_game,
            "saves_per_game": benchmark.saves_per_game,
            "shots_per_game": benchmark.shots_per_game,
            "shooting_pct": benchmark.shooting_pct,
            "boost_per_minute": benchmark.boost_per_minute,
            "supersonic_pct": benchmark.supersonic_pct,
            "aerials_per_game": benchmark.aerials_per_game,
            "wavedashes_per_game": benchmark.wavedashes_per_game,
        },
        "source": "community aggregate data",
    }


async def _save_coaching_note(
    params: dict[str, Any],
    user_id: str,
    db: DBSession,
) -> dict:
    """Save a coaching note."""
    import uuid

    content = params.get("content")
    category = params.get("category", "observation")

    if not content:
        return {"error": "Note content is required"}

    # Validate category against allowed values
    allowed_categories = {"strength", "weakness", "goal", "observation"}
    if category not in allowed_categories:
        return {"error": f"Invalid category. Allowed: {allowed_categories}"}

    # Sanitize content to prevent prompt injection
    safe_content = sanitize_user_content(content, MAX_NOTE_LENGTH)
    if not safe_content:
        return {"error": "Note content is empty after sanitization"}

    # Check if content was redacted due to injection attempt
    if "redacted" in safe_content.lower():
        return {"error": "Note content contains disallowed patterns"}

    note = CoachNote(
        id=str(uuid.uuid4()),
        user_id=user_id,
        content=f"[{category.upper()}] {safe_content}",
        source="coach",
        category=category,
    )

    db.add(note)
    db.commit()

    return {
        "success": True,
        "note_id": note.id,
        "message": "Coaching note saved successfully.",
    }


def _get_my_player_stats_batch(db: DBSession, replay_ids: list[str]) -> dict[str, dict]:
    """Get player stats for the 'me' player in multiple replays (batch query).

    Args:
        db: Database session
        replay_ids: List of replay IDs to look up

    Returns:
        Dict mapping replay_id -> player stats dict
    """
    if not replay_ids:
        return {}

    # Batch query - single DB hit for all replays
    all_stats = (
        db.query(PlayerGameStats)
        .filter(
            PlayerGameStats.replay_id.in_(replay_ids),
            PlayerGameStats.is_me == True,  # noqa: E712
        )
        .all()
    )

    # Build lookup dict
    result = {}
    for stats in all_stats:
        result[stats.replay_id] = {
            "goals": stats.goals or 0,
            "assists": stats.assists or 0,
            "saves": stats.saves or 0,
            "shots": stats.shots or 0,
            "score": stats.score or 0,
            "bcpm": stats.bcpm,
            "avg_boost": stats.avg_boost,
            "avg_speed_kph": stats.avg_speed_kph,
            "time_supersonic_s": stats.time_supersonic_s,
            "demos_inflicted": stats.demos_inflicted or 0,
            "demos_taken": stats.demos_taken or 0,
        }

    return result


def _get_my_player_stats(db: DBSession, replay_id: str) -> dict:
    """Get player stats for the 'me' player in a replay.

    Args:
        db: Database session
        replay_id: Replay ID to look up

    Returns:
        Dict of player stats
    """
    # Use batch function for single lookup
    result = _get_my_player_stats_batch(db, [replay_id])
    return result.get(replay_id, {})
