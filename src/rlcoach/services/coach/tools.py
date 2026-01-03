# src/rlcoach/services/coach/tools.py
"""Data access tools for AI Coach."""

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session as DBSession

from ...db.models import CoachNote, Replay


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

    query = db.query(Replay).filter(Replay.user_id == user_id)

    if playlist:
        query = query.filter(Replay.playlist == playlist)

    replays = query.order_by(Replay.created_at.desc()).limit(limit).all()

    if not replays:
        return {
            "games": [],
            "message": "No recent games found. Upload some replays to get started!",
        }

    games = []
    for replay in replays:
        # Get player stats from the replay
        analysis = replay.analysis or {}
        player_stats = _extract_player_stats(analysis, user_id)

        games.append({
            "id": replay.id,
            "date": replay.created_at.isoformat() if replay.created_at else None,
            "playlist": replay.playlist,
            "result": replay.result,  # "win", "loss", "draw"
            "score": f"{replay.team_score}-{replay.opponent_score}",
            "stats": player_stats,
        })

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

    query = db.query(Replay).filter(
        Replay.user_id == user_id,
        Replay.created_at >= cutoff,
    )

    if mode != "all":
        playlist_map = {
            "duel": "Ranked Duel",
            "doubles": "Ranked Doubles",
            "standard": "Ranked Standard",
        }
        query = query.filter(Replay.playlist == playlist_map.get(mode, mode))

    replays = query.all()

    if not replays:
        return {
            "mode": mode,
            "period_days": days,
            "games": 0,
            "message": f"No games found in {mode} mode over the last {days} days.",
        }

    # Aggregate stats
    stats = {
        "goals": 0,
        "assists": 0,
        "saves": 0,
        "shots": 0,
        "wins": 0,
        "losses": 0,
        "total_boost_used": 0,
        "total_supersonic_time": 0,
    }

    for replay in replays:
        analysis = replay.analysis or {}
        player_stats = _extract_player_stats(analysis, user_id)

        stats["goals"] += player_stats.get("goals", 0)
        stats["assists"] += player_stats.get("assists", 0)
        stats["saves"] += player_stats.get("saves", 0)
        stats["shots"] += player_stats.get("shots", 0)

        if replay.result == "win":
            stats["wins"] += 1
        elif replay.result == "loss":
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
            "assists": round(stats["assists"] / total_games, 2) if total_games > 0 else 0,
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

    replay = db.query(Replay).filter(
        Replay.id == game_id,
        Replay.user_id == user_id,
    ).first()

    if not replay:
        return {"error": f"Game {game_id} not found"}

    analysis = replay.analysis or {}

    return {
        "id": replay.id,
        "date": replay.created_at.isoformat() if replay.created_at else None,
        "playlist": replay.playlist,
        "result": replay.result,
        "score": f"{replay.team_score}-{replay.opponent_score}",
        "duration_seconds": replay.duration,
        "analysis": {
            "player_stats": _extract_player_stats(analysis, user_id),
            "mechanics": analysis.get("mechanics", {}),
            "boost": analysis.get("boost", {}),
            "positioning": analysis.get("positioning", {}),
            "insights": analysis.get("insights", []),
        },
    }


async def _get_rank_benchmarks(
    params: dict[str, Any],
    user_id: str,
    db: DBSession,
) -> dict:
    """Get benchmark stats for a rank.

    Note: In a real implementation, these would come from aggregated
    data across all users. For now, we return estimated benchmarks.
    """
    rank = params.get("rank", "Diamond II")
    mode = params.get("mode", "standard")

    # Estimated benchmarks by rank (would be real data in production)
    benchmarks = {
        "Bronze": {"goals": 0.3, "assists": 0.1, "saves": 0.2, "shots": 0.8, "win_rate": 50},
        "Silver": {"goals": 0.5, "assists": 0.2, "saves": 0.4, "shots": 1.2, "win_rate": 50},
        "Gold": {"goals": 0.7, "assists": 0.3, "saves": 0.6, "shots": 1.5, "win_rate": 50},
        "Platinum": {"goals": 0.9, "assists": 0.4, "saves": 0.8, "shots": 1.8, "win_rate": 50},
        "Diamond": {"goals": 1.1, "assists": 0.5, "saves": 1.0, "shots": 2.0, "win_rate": 50},
        "Champion": {"goals": 1.3, "assists": 0.6, "saves": 1.2, "shots": 2.2, "win_rate": 50},
        "Grand Champion": {"goals": 1.5, "assists": 0.8, "saves": 1.4, "shots": 2.5, "win_rate": 50},
        "SSL": {"goals": 1.8, "assists": 1.0, "saves": 1.6, "shots": 2.8, "win_rate": 50},
    }

    # Find closest rank match
    rank_base = rank.split()[0] if " " in rank else rank
    benchmark = benchmarks.get(rank_base, benchmarks["Diamond"])

    return {
        "rank": rank,
        "mode": mode,
        "benchmarks": {
            "goals_per_game": benchmark["goals"],
            "assists_per_game": benchmark["assists"],
            "saves_per_game": benchmark["saves"],
            "shots_per_game": benchmark["shots"],
            "win_rate": benchmark["win_rate"],
        },
        "note": "These are estimated benchmarks. Actual stats vary by playstyle.",
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

    note = CoachNote(
        id=str(uuid.uuid4()),
        user_id=user_id,
        content=f"[{category.upper()}] {content}",
        is_ai_generated=True,
    )

    db.add(note)
    db.commit()

    return {
        "success": True,
        "note_id": note.id,
        "message": "Coaching note saved successfully.",
    }


def _extract_player_stats(analysis: dict, user_id: str) -> dict:
    """Extract player-specific stats from replay analysis.

    Args:
        analysis: Full replay analysis dict
        user_id: User ID to find their stats

    Returns:
        Dict of player stats
    """
    # Try to find player stats in various analysis structures
    players = analysis.get("players", [])

    for player in players:
        if player.get("is_me") or player.get("user_id") == user_id:
            return {
                "goals": player.get("goals", 0),
                "assists": player.get("assists", 0),
                "saves": player.get("saves", 0),
                "shots": player.get("shots", 0),
                "score": player.get("score", 0),
                "boost_per_minute": player.get("boost_per_minute"),
                "supersonic_pct": player.get("supersonic_pct"),
            }

    # Fallback to fundamentals if available
    fundamentals = analysis.get("fundamentals", {})
    per_player = fundamentals.get("per_player", {})

    for player_id, stats in per_player.items():
        return {
            "goals": stats.get("goals", 0),
            "assists": stats.get("assists", 0),
            "saves": stats.get("saves", 0),
            "shots": stats.get("shots", 0),
        }

    return {}
