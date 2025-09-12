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
    per_player_map = {}
    for player_id, team in players.items():
        player_analysis = _analyze_player(frames, events, player_id, team, header)
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


def _analyze_team(frames: list[Frame], events: dict[str, list[Any]], 
                  team: str, header: Header | None) -> dict[str, Any]:
    """Generate complete analysis for a team."""
    
    # Run individual analyzers
    fundamentals = analyze_fundamentals(frames, events, team=team, header=header)
    boost = analyze_boost(frames, events, team=team, header=header)
    movement = analyze_movement(frames, events, team=team, header=header)
    positioning = analyze_positioning(frames, events, team=team, header=header)
    
    # Placeholder for other analyzers (not in scope for this ticket)
    passing = analyze_passing(frames, events, team=team, header=header)
    challenges = analyze_challenges(frames, events, team=team, header=header)
    kickoffs = analyze_kickoffs(frames, events, team=team, header=header)
    
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
    movement = analyze_movement(frames, events, player_id=player_id, header=header)
    positioning = analyze_positioning(frames, events, player_id=player_id, header=header)
    
    # Calculate rotation compliance (player-only analysis)
    rotation_compliance = calculate_rotation_compliance(frames, player_id)
    
    # Placeholder for other analyzers (not in scope for this ticket)
    passing = analyze_passing(frames, events, player_id=player_id, header=header) 
    challenges = analyze_challenges(frames, events, player_id=player_id, header=header)
    kickoffs = analyze_kickoffs(frames, events, player_id=player_id, header=header)
    heatmaps = generate_heatmaps(frames, player_id, events)
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
        "rotation_compliance": rotation_compliance
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


def _placeholder_passing() -> dict[str, Any]:
    """Deprecated placeholder. Kept for import stability in older tests."""
    from .passing import _empty_passing

    return _empty_passing()


def _placeholder_challenges() -> dict[str, Any]:
    """Deprecated placeholder; use analyze_challenges instead."""
    return analyze_challenges([], {})


def _placeholder_kickoffs() -> dict[str, Any]:
    """Deprecated placeholder; use analyze_kickoffs instead."""
    return analyze_kickoffs([], {})


def _placeholder_heatmaps() -> dict[str, Any]:
    """Placeholder heatmaps for player analysis."""
    return {
        "position_occupancy_grid": None,
        "touch_density_grid": None,
        "boost_pickup_grid": None  # Changed from boost_usage_grid to match schema
    }




def _placeholder_insights() -> list[dict[str, Any]]:
    """Placeholder insights for player analysis."""
    return []
