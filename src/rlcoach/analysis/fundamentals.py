"""Fundamentals analysis for Rocket League replay data.

This module computes core performance metrics from game events:
- Goals, assists, shots, saves
- Demolitions inflicted and taken  
- Score calculation
- Shooting percentage

All calculations use deterministic event-based counting with graceful
degradation for incomplete data.
"""

from __future__ import annotations

from typing import Any
from ..events import GoalEvent, DemoEvent, TouchEvent
from ..parser.types import Header, Frame


def analyze_fundamentals(
    frames: list[Frame],
    events: dict[str, list[Any]],
    player_id: str | None = None,
    team: str | None = None,
    header: Header | None = None,
) -> dict[str, Any]:
    """Analyze fundamental performance metrics for a player or team.
    
    Args:
        frames: Normalized frame data (used for validation only)
        events: Dictionary containing detected events by type
        player_id: If provided, analyze specific player; otherwise team analysis
        team: Team filter ("BLUE" or "ORANGE"), required if player_id not provided
        header: Optional header for additional context
        
    Returns:
        Dictionary matching schema fundamentals definition:
        {
            "goals": int,
            "assists": int, 
            "shots": int,
            "saves": int,
            "demos_inflicted": int,
            "demos_taken": int,
            "score": int,
            "shooting_percentage": float
        }
    """
    if not events:
        return _empty_fundamentals()
    
    # Extract event lists with safe defaults
    goals = events.get('goals', [])
    demos = events.get('demos', [])
    touches = events.get('touches', [])
    
    # Count goals
    goals_count = 0
    assists_count = 0
    
    for goal in goals:
        if _matches_filter(goal.scorer, goal.team, player_id, team):
            goals_count += 1
        
        # Count assists - goal.assist is the assisting player ID
        if goal.assist and _matches_filter(goal.assist, goal.team, player_id, team):
            assists_count += 1
    
    # Count demos inflicted and taken
    demos_inflicted = 0
    demos_taken = 0
    
    for demo in demos:
        # Demos inflicted - player was the attacker
        if demo.attacker and _matches_filter(demo.attacker, demo.team_attacker, player_id, team):
            demos_inflicted += 1
        
        # Demos taken - player was the victim
        if _matches_filter(demo.victim, demo.team_victim, player_id, team):
            demos_taken += 1
    
    # Count shots and saves from touch events
    shots_count = 0
    saves_count = 0
    
    for touch in touches:
        if not _matches_filter(touch.player_id, _infer_team_from_events(touch.player_id, goals, demos), player_id, team):
            continue
            
        if touch.outcome == "SHOT":
            shots_count += 1
        elif touch.outcome == "SAVE":
            saves_count += 1
    
    # Calculate shooting percentage
    shooting_percentage = 0.0
    if shots_count > 0:
        shooting_percentage = (goals_count / shots_count) * 100.0
    
    # Calculate score using community standard formula
    score = (
        100 * goals_count +
        50 * assists_count + 
        20 * shots_count +
        75 * saves_count +
        25 * demos_inflicted
    )
    
    return {
        "goals": goals_count,
        "assists": assists_count,
        "shots": shots_count, 
        "saves": saves_count,
        "demos_inflicted": demos_inflicted,
        "demos_taken": demos_taken,
        "score": score,
        "shooting_percentage": round(shooting_percentage, 2)
    }


def _empty_fundamentals() -> dict[str, Any]:
    """Return empty fundamentals dict for degraded scenarios."""
    return {
        "goals": 0,
        "assists": 0,
        "shots": 0,
        "saves": 0, 
        "demos_inflicted": 0,
        "demos_taken": 0,
        "score": 0,
        "shooting_percentage": 0.0
    }


def _matches_filter(event_player_id: str | None, event_team: str | None, 
                   filter_player_id: str | None, filter_team: str | None) -> bool:
    """Check if event matches player/team filter criteria."""
    if filter_player_id:
        # Player-specific analysis
        return event_player_id == filter_player_id
    elif filter_team:
        # Team analysis
        return event_team == filter_team
    else:
        # No filter - should not happen in normal usage
        return True


def _infer_team_from_events(player_id: str, goals: list[GoalEvent], demos: list[DemoEvent]) -> str | None:
    """Infer player's team from their involvement in events.
    
    This is a fallback for touch events which don't include team info.
    """
    # Check goals where this player was scorer
    for goal in goals:
        if goal.scorer == player_id:
            return goal.team
    
    # Check demos where this player was victim or attacker
    for demo in demos:
        if demo.victim == player_id:
            return demo.team_victim
        elif demo.attacker == player_id:
            return demo.team_attacker
    
    return None