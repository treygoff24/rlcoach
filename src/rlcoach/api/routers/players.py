# src/rlcoach/api/routers/players.py
"""Players API endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ...db.session import create_session
from ...db.models import Player, PlayerGameStats
from ...analysis.tendencies import compute_tendencies, TendencyProfile

router = APIRouter(tags=["players"])


class TagRequest(BaseModel):
    """Request body for tagging a player."""
    tagged: bool = True
    notes: str | None = None


@router.get("/players")
async def list_players(
    tagged: bool | None = None,
    min_games: int = Query(default=0),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    sort: str = Query(default="-games_with_me"),
) -> dict[str, Any]:
    """List players (excluding self).

    Args:
        tagged: Filter by tagged status
        min_games: Minimum games played with me
        limit: Maximum number of players to return
        offset: Number of players to skip
        sort: Sort field (prefix with - for descending)
    """
    session = create_session()
    try:
        query = session.query(Player).filter(Player.is_me == False)

        if tagged is not None:
            query = query.filter(Player.is_tagged_teammate == tagged)
        if min_games > 0:
            query = query.filter(Player.games_with_me >= min_games)

        # Get total count before pagination
        total = query.count()

        # Apply sorting
        if sort.startswith("-"):
            sort_field = sort[1:]
            descending = True
        else:
            sort_field = sort
            descending = False

        if hasattr(Player, sort_field):
            order_col = getattr(Player, sort_field)
            query = query.order_by(order_col.desc() if descending else order_col)

        # Apply pagination
        players = query.offset(offset).limit(limit).all()

        items = []
        for p in players:
            items.append({
                "player_id": p.player_id,
                "display_name": p.display_name,
                "platform": p.platform,
                "is_me": p.is_me,
                "is_tagged_teammate": p.is_tagged_teammate,
                "teammate_notes": p.teammate_notes,
                "games_with_me": p.games_with_me,
                "first_seen_utc": p.first_seen_utc.isoformat() if p.first_seen_utc else None,
                "last_seen_utc": p.last_seen_utc.isoformat() if p.last_seen_utc else None,
            })

        return {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    finally:
        session.close()


@router.get("/players/{player_id}")
async def get_player(player_id: str) -> dict[str, Any]:
    """Get player details by ID.

    Args:
        player_id: The player ID (e.g., steam:123456)
    """
    session = create_session()
    try:
        player = session.get(Player, player_id)
        if not player:
            raise HTTPException(status_code=404, detail="Player not found")

        result = {
            "player_id": player.player_id,
            "display_name": player.display_name,
            "platform": player.platform,
            "is_me": player.is_me,
            "is_tagged_teammate": player.is_tagged_teammate,
            "teammate_notes": player.teammate_notes,
            "games_with_me": player.games_with_me,
            "first_seen_utc": player.first_seen_utc.isoformat() if player.first_seen_utc else None,
            "last_seen_utc": player.last_seen_utc.isoformat() if player.last_seen_utc else None,
        }

        # Compute tendency profile if we have stats
        stats = (
            session.query(PlayerGameStats)
            .filter(PlayerGameStats.player_id == player_id)
            .all()
        )

        if stats:
            stat_dicts = []
            for s in stats:
                stat_dicts.append({
                    "goals": s.goals or 0,
                    "saves": s.saves or 0,
                    "shots": s.shots or 0,
                    "assists": s.assists or 0,
                    "challenge_wins": 0,  # Not all stats have this
                    "challenge_losses": 0,
                    "first_man_pct": s.first_man_pct or 33.0,
                    "second_man_pct": s.second_man_pct or 33.0,
                    "third_man_pct": s.third_man_pct or 33.0,
                    "bcpm": s.bcpm or 0,
                    "avg_boost": s.avg_boost or 0,
                    "aerial_count": 0,
                    "wavedash_count": 0,
                    "time_last_defender_s": s.time_last_defender_s or 0,
                    "behind_ball_pct": s.behind_ball_pct or 50.0,
                })

            profile = compute_tendencies(stat_dicts)
            if profile:
                result["tendency_profile"] = {
                    "aggression_score": round(profile.aggression_score, 1),
                    "challenge_rate": round(profile.challenge_rate, 1),
                    "first_man_tendency": round(profile.first_man_tendency, 1),
                    "boost_priority": round(profile.boost_priority, 1),
                    "mechanical_index": round(profile.mechanical_index, 1),
                    "defensive_index": round(profile.defensive_index, 1),
                }

        return result

    finally:
        session.close()


@router.post("/players/{player_id}/tag")
async def tag_player(player_id: str, request: TagRequest) -> dict[str, Any]:
    """Tag or untag a player as a teammate.

    Args:
        player_id: The player ID
        request: Tag request with notes
    """
    session = create_session()
    try:
        player = session.get(Player, player_id)
        if not player:
            raise HTTPException(status_code=404, detail="Player not found")

        player.is_tagged_teammate = request.tagged
        if request.notes is not None:
            player.teammate_notes = request.notes

        session.commit()

        return {
            "player_id": player.player_id,
            "display_name": player.display_name,
            "is_tagged_teammate": player.is_tagged_teammate,
            "teammate_notes": player.teammate_notes,
        }

    finally:
        session.close()
