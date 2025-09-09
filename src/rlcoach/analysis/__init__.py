"""Analysis aggregator for combining per-player and per-team metrics.

This module orchestrates all individual analyzers and provides the main entry
point for generating complete analysis results that conform to the JSON schema.
"""

from __future__ import annotations

from typing import Any
from .fundamentals import analyze_fundamentals
from .boost import analyze_boost
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
    
    # Generate per-team analysis
    per_team = {
        "blue": _analyze_team(frames, events, "BLUE", header),
        "orange": _analyze_team(frames, events, "ORANGE", header)
    }
    
    # Generate per-player analysis
    per_player = []
    for player_id, team in players.items():
        player_analysis = _analyze_player(frames, events, player_id, team, header)
        per_player.append(player_analysis)
    
    # Add data quality warnings
    if not frames and events:
        warnings.append("header_only_mode_limited_metrics")
    
    return {
        "per_team": per_team,
        "per_player": per_player,
        "warnings": warnings
    }


def _analyze_team(frames: list[Frame], events: dict[str, list[Any]], 
                  team: str, header: Header | None) -> dict[str, Any]:
    """Generate complete analysis for a team."""
    
    # Run individual analyzers
    fundamentals = analyze_fundamentals(frames, events, team=team, header=header)
    boost = analyze_boost(frames, events, team=team, header=header)
    
    # Placeholder for other analyzers (not in scope for this ticket)
    movement = _placeholder_movement()
    positioning = _placeholder_positioning() 
    passing = _placeholder_passing()
    challenges = _placeholder_challenges()
    kickoffs = _placeholder_kickoffs()
    
    return {
        "fundamentals": fundamentals,
        "boost": boost,
        "movement": movement,
        "positioning": positioning,
        "passing": passing,
        "challenges": challenges,
        "kickoffs": kickoffs
    }


def _analyze_player(frames: list[Frame], events: dict[str, list[Any]],
                   player_id: str, team: str, header: Header | None) -> dict[str, Any]:
    """Generate complete analysis for a player."""
    
    # Run individual analyzers  
    fundamentals = analyze_fundamentals(frames, events, player_id=player_id, header=header)
    boost = analyze_boost(frames, events, player_id=player_id, header=header)
    
    # Placeholder for other analyzers (not in scope for this ticket)
    movement = _placeholder_movement()
    positioning = _placeholder_positioning()
    passing = _placeholder_passing() 
    challenges = _placeholder_challenges()
    kickoffs = _placeholder_kickoffs()
    heatmaps = _placeholder_heatmaps()
    rotation_compliance = _placeholder_rotation_compliance()
    insights = _placeholder_insights()
    
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
        "insights": insights
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


# Placeholder functions for analyzers not implemented in this ticket
def _placeholder_movement() -> dict[str, Any]:
    """Placeholder movement analysis."""
    return {
        "avg_speed_kph": 0.0,
        "time_slow_s": 0.0,
        "time_boost_speed_s": 0.0,
        "time_supersonic_s": 0.0,
        "time_ground_s": 0.0,
        "time_low_air_s": 0.0,
        "time_high_air_s": 0.0,
        "powerslide_count": 0,
        "powerslide_duration_s": 0.0,
        "aerial_count": 0,
        "aerial_time_s": 0.0
    }


def _placeholder_positioning() -> dict[str, Any]:
    """Placeholder positioning analysis."""
    return {
        "time_offensive_half_s": 0.0,
        "time_defensive_half_s": 0.0,
        "time_offensive_third_s": 0.0,
        "time_middle_third_s": 0.0,
        "time_defensive_third_s": 0.0,
        "behind_ball_pct": 0.0,
        "ahead_ball_pct": 0.0,
        "avg_distance_to_ball_m": 0.0,
        "avg_distance_to_teammate_m": 0.0,
        "first_man_pct": 0.0,
        "second_man_pct": 0.0,
        "third_man_pct": 0.0
    }


def _placeholder_passing() -> dict[str, Any]:
    """Placeholder passing analysis.""" 
    return {
        "passes_completed": 0,
        "passes_attempted": 0,
        "passes_received": 0,
        "turnovers": 0,
        "give_and_go_count": 0,
        "possession_time_s": 0.0
    }


def _placeholder_challenges() -> dict[str, Any]:
    """Placeholder challenges analysis."""
    return {
        "contests": 0,
        "wins": 0,
        "losses": 0,
        "neutral": 0,
        "first_to_ball_pct": 0.0,
        "challenge_depth_m": 0.0,
        "risk_index_avg": 0.0
    }


def _placeholder_kickoffs() -> dict[str, Any]:
    """Placeholder kickoffs analysis."""
    return {
        "count": 0,
        "wins": 0,
        "losses": 0,
        "neutral": 0,
        "avg_boost_used": 0.0,
        "first_touch_pct": 0.0,
        "approach_consistency": 0.0
    }


def _placeholder_heatmaps() -> dict[str, Any]:
    """Placeholder heatmaps for player analysis."""
    return {
        "position_occupancy_grid": None,
        "touch_density_grid": None,
        "boost_usage_grid": None
    }


def _placeholder_rotation_compliance() -> dict[str, Any]:
    """Placeholder rotation compliance for player analysis."""
    return {
        "average_score": 0.0,
        "time_out_of_position_s": 0.0,
        "double_commits": 0,
        "rotation_violations": 0
    }


def _placeholder_insights() -> list[dict[str, Any]]:
    """Placeholder insights for player analysis."""
    return []