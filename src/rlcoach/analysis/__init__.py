"""Analysis aggregator for combining per-player and per-team metrics.

This module orchestrates all individual analyzers and provides the main entry
point for generating complete analysis results that conform to the JSON schema.
"""

from __future__ import annotations

from typing import Any
from .fundamentals import analyze_fundamentals
from .boost import analyze_boost
from .movement import analyze_movement
from .positioning import analyze_positioning, calculate_rotation_compliance
from .passing import analyze_passing
from .challenges import analyze_challenges
from .kickoffs import analyze_kickoffs
from .heatmaps import generate_heatmaps
from .insights import generate_player_insights, generate_team_insights
from .mechanics import analyze_mechanics
from .recovery import analyze_recoveries
from .xg import analyze_shots_xg
from .defense import analyze_defense
from .ball_prediction import analyze_ball_prediction
from ..parser.types import Header, Frame


def aggregate_analysis(
    frames: list[Frame],
    events: dict[str, list[Any]],
    header: Header | None = None
) -> dict[str, Any]:
    """Aggregate all analysis results for a replay.

    Args:
        frames: Normalized frame data
        events: Dictionary containing all detected events by type
        header: Optional header for match context

    Returns:
        Dictionary with per_team and per_player analysis matching schema:
        {
            "per_team": {
                "blue": { "fundamentals": {...}, "boost": {...}, ... },
                "orange": { "fundamentals": {...}, "boost": {...}, ... }
            },
            "per_player": [
                {
                    "player_id": "...",
                    "fundamentals": {...},
                    "boost": {...},
                    ...
                }
            ],
            "warnings": [...]
        }
    """
    warnings = []

    # Check data quality
    if not frames:
        warnings.append("no_frame_data_available")
    if not events:
        warnings.append("no_events_detected")

    # Get unique players and their teams from frames
    players = _extract_players_from_frames(frames)

    # Cache expensive analysis results that analyze all players/teams in one pass
    # This avoids redundant re-analysis when iterating per-player or per-team
    touches = events.get("touches", [])
    cached_mechanics = analyze_mechanics(frames)
    cached_recoveries = analyze_recoveries(frames)
    cached_defense = analyze_defense(frames)
    cached_ball_prediction = analyze_ball_prediction(frames)
    cached_xg = analyze_shots_xg(frames, touches)

    # Generate per-team analysis using cached results
    per_team = {
        "blue": _analyze_team(frames, events, "BLUE", header, cached_defense, cached_mechanics),
        "orange": _analyze_team(frames, events, "ORANGE", header, cached_defense, cached_mechanics)
    }

    # Generate per-player analysis using cached results
    per_player = []
    per_player_map = {}
    for player_id, team in players.items():
        player_analysis = _analyze_player(
            frames, events, player_id, team, header,
            cached_mechanics, cached_recoveries, cached_defense,
            cached_ball_prediction, cached_xg
        )
        per_player.append(player_analysis)
        per_player_map[player_id] = player_analysis

    # Generate team-level coaching insights
    coaching_insights = generate_team_insights(per_team, per_player_map)

    # Add data quality warnings
    if not frames and events:
        warnings.append("header_only_mode_limited_metrics")

    return {
        "per_team": per_team,
        "per_player": per_player,
        "coaching_insights": coaching_insights,
        "warnings": warnings
    }


def _analyze_team(
    frames: list[Frame],
    events: dict[str, list[Any]],
    team: str,
    header: Header | None,
    cached_defense: dict[str, Any] | None = None,
    cached_mechanics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate complete analysis for a team."""

    # Run individual analyzers
    fundamentals = analyze_fundamentals(frames, events, team=team, header=header)
    boost = analyze_boost(frames, events, team=team, header=header)
    movement = analyze_movement(frames, events, team=team, header=header)
    positioning = analyze_positioning(frames, events, team=team, header=header)

    # Additional analyzers
    passing = analyze_passing(frames, events, team=team, header=header)
    challenges = analyze_challenges(frames, events, team=team, header=header)
    kickoffs = analyze_kickoffs(frames, events, team=team, header=header)

    # Use cached defense results if available, otherwise compute
    if cached_defense is None:
        cached_defense = analyze_defense(frames)
    team_key = "blue" if team == "BLUE" else "orange"
    defense_team = cached_defense.get("per_team", {}).get(team_key, {})

    # Aggregate team-level mechanics from cached per-player data
    if cached_mechanics is None:
        cached_mechanics = analyze_mechanics(frames)
    team_mechanics = _aggregate_team_mechanics(frames, team, cached_mechanics)

    return {
        "fundamentals": fundamentals,
        "boost": boost,
        "movement": movement,
        "positioning": positioning,
        "passing": passing,
        "challenges": challenges,
        "kickoffs": kickoffs,
        "defense": defense_team,
        "mechanics": team_mechanics,
    }


def _aggregate_team_mechanics(
    frames: list[Frame],
    team: str,
    cached_mechanics: dict[str, Any],
) -> dict[str, Any]:
    """Aggregate mechanics counts for a team from per-player data."""
    # Build team player mapping
    team_idx = 0 if team == "BLUE" else 1
    team_player_ids: set[str] = set()
    for frame in frames:
        for player in frame.players:
            if player.team == team_idx:
                team_player_ids.add(player.player_id)

    # Aggregate mechanics counts
    total_wavedashes = 0
    total_halfflips = 0
    total_speedflips = 0
    total_aerials = 0
    total_flips = 0
    total_flip_cancels = 0

    per_player = cached_mechanics.get("per_player", {})
    for player_id in team_player_ids:
        player_mech = per_player.get(player_id, {})
        total_wavedashes += player_mech.get("wavedash_count", 0)
        total_halfflips += player_mech.get("halfflip_count", 0)
        total_speedflips += player_mech.get("speedflip_count", 0)
        total_aerials += player_mech.get("aerial_count", 0)
        total_flips += player_mech.get("flip_count", 0)
        total_flip_cancels += player_mech.get("flip_cancel_count", 0)

    return {
        "total_wavedashes": total_wavedashes,
        "total_halfflips": total_halfflips,
        "total_speedflips": total_speedflips,
        "total_aerials": total_aerials,
        "total_flips": total_flips,
        "total_flip_cancels": total_flip_cancels,
    }


def _analyze_player(
    frames: list[Frame],
    events: dict[str, list[Any]],
    player_id: str,
    team: str,
    header: Header | None,
    cached_mechanics: dict[str, Any] | None = None,
    cached_recoveries: dict[str, Any] | None = None,
    cached_defense: dict[str, Any] | None = None,
    cached_ball_prediction: dict[str, Any] | None = None,
    cached_xg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate complete analysis for a player."""

    # Run individual analyzers
    fundamentals = analyze_fundamentals(frames, events, player_id=player_id, header=header)
    boost = analyze_boost(frames, events, player_id=player_id, header=header)
    movement = analyze_movement(frames, events, player_id=player_id, header=header)
    positioning = analyze_positioning(frames, events, player_id=player_id, header=header)

    # Calculate rotation compliance (player-only analysis)
    rotation_compliance = calculate_rotation_compliance(frames, player_id)

    # Additional analyzers
    passing = analyze_passing(frames, events, player_id=player_id, header=header)
    challenges = analyze_challenges(frames, events, player_id=player_id, header=header)
    kickoffs = analyze_kickoffs(frames, events, player_id=player_id, header=header)
    heatmaps = generate_heatmaps(frames, player_id, events)

    # Use cached results if available, otherwise compute
    # Extract player-specific data from aggregated results
    if cached_mechanics is None:
        cached_mechanics = analyze_mechanics(frames)
    mechanics_player = cached_mechanics.get("per_player", {}).get(player_id, {
        "jump_count": 0,
        "double_jump_count": 0,
        "flip_count": 0,
        "wavedash_count": 0,
        "aerial_count": 0,
        "halfflip_count": 0,
        "speedflip_count": 0,
        "flip_cancel_count": 0,
        "total_mechanics": 0,
    })

    if cached_recoveries is None:
        cached_recoveries = analyze_recoveries(frames)
    recovery_player = cached_recoveries.get("per_player", {}).get(player_id, {
        "total_recoveries": 0,
        "quality_distribution": {},
        "excellent_count": 0,
        "poor_count": 0,
        "average_momentum_retained": 0.0,
        "wavedash_count": 0,
    })

    if cached_xg is None:
        touches = events.get("touches", [])
        cached_xg = analyze_shots_xg(frames, touches)
    xg_player = cached_xg.get("per_player", {}).get(player_id, {
        "total_shots": 0,
        "total_xg": 0.0,
    })

    if cached_defense is None:
        cached_defense = analyze_defense(frames)
    defense_player = cached_defense.get("per_player", {}).get(player_id, {
        "time_as_last_defender": 0.0,
        "time_out_of_position": 0.0,
        "time_shadowing": 0.0,
        "average_shadow_angle": None,
    })

    if cached_ball_prediction is None:
        cached_ball_prediction = analyze_ball_prediction(frames)
    ball_prediction_player = cached_ball_prediction.get("per_player", {}).get(player_id, {
        "total_reads": 0,
        "quality_distribution": {},
        "excellent_reads": 0,
        "poor_reads": 0,
        "average_prediction_error": 0.0,
        "proactive_rate": 0.0,
    })

    # Generate insights based on complete analysis data
    complete_analysis = {
        "player_id": player_id,
        "fundamentals": fundamentals,
        "boost": boost,
        "movement": movement,
        "positioning": positioning,
        "passing": passing,
        "challenges": challenges,
        "kickoffs": kickoffs,
        "rotation_compliance": rotation_compliance,
        "mechanics": mechanics_player,
        "recovery": recovery_player,
        "xg": xg_player,
        "defense": defense_player,
        "ball_prediction": ball_prediction_player,
    }
    insights = generate_player_insights(complete_analysis)

    return {
        "player_id": player_id,
        "fundamentals": fundamentals,
        "boost": boost,
        "movement": movement,
        "positioning": positioning,
        "passing": passing,
        "challenges": challenges,
        "kickoffs": kickoffs,
        "heatmaps": heatmaps,
        "rotation_compliance": rotation_compliance,
        "insights": insights,
        "mechanics": mechanics_player,
        "recovery": recovery_player,
        "xg": xg_player,
        "defense": defense_player,
        "ball_prediction": ball_prediction_player,
    }


def _extract_players_from_frames(frames: list[Frame]) -> dict[str, str]:
    """Extract unique players and their teams from frames.
    
    Returns:
        Dictionary mapping player_id -> team_name ("BLUE" or "ORANGE")
    """
    players = {}
    
    for frame in frames:
        for player in frame.players:
            if player.player_id not in players:
                team_name = "BLUE" if player.team == 0 else "ORANGE"
                players[player.player_id] = team_name
    
    return players
