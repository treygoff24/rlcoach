"""Positioning and rotation analysis for Rocket League replay data.

This module computes positioning and rotational metrics from frame data:
- Field occupancy: time spent in halves, thirds, and zones
- Ball relationship: behind/ahead percentages and distances
- Role detection: first/second/third man classification
- Rotation compliance scoring with flag detection
- Team positioning analysis and coordination metrics

All calculations use deterministic thresholds and frame-by-frame
analysis for consistent results.
"""

from __future__ import annotations

import math
from typing import Any
from ..parser.types import Header, Frame, PlayerFrame
from ..field_constants import Vec3, FieldConstants


# Role detection thresholds (distance-based)
FIRST_MAN_DISTANCE_THRESHOLD = 800.0  # Distance to ball for first man
TEAMMATE_DISTANCE_THRESHOLD = 1500.0  # Max distance to consider teammate proximity

# Rotation compliance thresholds
DOUBLE_COMMIT_DISTANCE = 500.0  # Both players within this distance of ball
OVERCOMMIT_BOOST_THRESHOLD = 20.0  # Low boost threshold for overcommit detection
ROTATION_VIOLATION_MIN_TIME = 1.0  # Minimum seconds for violation counting

# Ball relationship thresholds
BALL_AHEAD_THRESHOLD = 50.0  # Y-axis difference threshold


def analyze_positioning(
    frames: list[Frame],
    events: dict[str, list[Any]],
    player_id: str | None = None,
    team: str | None = None,
    header: Header | None = None,
) -> dict[str, Any]:
    """Analyze positioning and rotation metrics for a player or team.
    
    Args:
        frames: Normalized frame data for positioning analysis
        events: Dictionary containing detected events (not heavily used for positioning)
        player_id: If provided, analyze specific player; otherwise team analysis
        team: Team filter ("BLUE" or "ORANGE"), required if player_id not provided
        header: Optional header for match context
        
    Returns:
        Dictionary matching schema positioning definition:
        {
            "time_offensive_half_s": float,
            "time_defensive_half_s": float,
            "time_offensive_third_s": float,
            "time_middle_third_s": float,
            "time_defensive_third_s": float,
            "behind_ball_pct": float,
            "ahead_ball_pct": float,
            "avg_distance_to_ball_m": float,
            "avg_distance_to_teammate_m": float,
            "first_man_pct": float,
            "second_man_pct": float,
            "third_man_pct": float
        }
    """
    if not frames:
        return _empty_positioning()
    
    if player_id:
        return _analyze_player_positioning(frames, player_id)
    elif team:
        return _analyze_team_positioning(frames, team)
    else:
        return _empty_positioning()


def _analyze_player_positioning(frames: list[Frame], player_id: str) -> dict[str, Any]:
    """Analyze positioning metrics for a specific player."""

    # Initialize counters
    total_frames = 0
    total_distance_to_ball = 0.0
    total_distance_to_teammates = 0.0
    teammate_distance_count = 0

    # Field occupancy counters
    time_offensive_half = 0.0
    time_defensive_half = 0.0
    time_offensive_third = 0.0
    time_middle_third = 0.0
    time_defensive_third = 0.0

    # Ball relationship counters
    behind_ball_frames = 0
    ahead_ball_frames = 0

    # Role counters
    first_man_frames = 0
    second_man_frames = 0
    third_man_frames = 0

    # Determine player's team and team size from first valid frame
    player_team = None
    team_size = 0
    for frame in frames:
        player_frame = _find_player_in_frame(frame, player_id)
        if player_frame:
            player_team = player_frame.team
            # Count teammates (including this player)
            team_size = sum(1 for p in frame.players if p.team == player_team)
            break

    if player_team is None:
        return _empty_positioning()

    prev_timestamp: float | None = None

    for idx, frame in enumerate(frames):
        player_frame = _find_player_in_frame(frame, player_id)
        if not player_frame:
            continue

        total_frames += 1

        # Calculate frame duration for this frame without repeated list scans
        frame_dt = _frame_duration(frames, idx, prev_timestamp)
        
        # Field occupancy analysis
        player_pos = player_frame.position
        
        # Determine offensive/defensive based on team
        if player_team == 0:  # Blue team defends negative Y
            is_offensive_half = player_pos.y > 0
            is_defensive_half = player_pos.y <= 0
        else:  # Orange team defends positive Y
            is_offensive_half = player_pos.y < 0
            is_defensive_half = player_pos.y >= 0
        
        if is_offensive_half:
            time_offensive_half += frame_dt
        else:
            time_defensive_half += frame_dt
        
        # Field thirds analysis
        field_third = FieldConstants.get_field_third(player_pos)
        if player_team == 0:  # Blue team perspective
            if field_third == "defensive":
                time_defensive_third += frame_dt
            elif field_third == "offensive":
                time_offensive_third += frame_dt
            else:
                time_middle_third += frame_dt
        else:  # Orange team perspective (flip thirds)
            if field_third == "defensive":
                time_offensive_third += frame_dt
            elif field_third == "offensive":
                time_defensive_third += frame_dt
            else:
                time_middle_third += frame_dt
        
        # Ball relationship analysis
        ball_pos = frame.ball.position
        distance_to_ball = _calculate_distance(player_pos, ball_pos)
        total_distance_to_ball += distance_to_ball
        
        # Behind/ahead ball calculation (Y-axis based)
        if player_team == 0:  # Blue team
            if player_pos.y < ball_pos.y - BALL_AHEAD_THRESHOLD:
                behind_ball_frames += 1
            elif player_pos.y > ball_pos.y + BALL_AHEAD_THRESHOLD:
                ahead_ball_frames += 1
        else:  # Orange team
            if player_pos.y > ball_pos.y + BALL_AHEAD_THRESHOLD:
                behind_ball_frames += 1
            elif player_pos.y < ball_pos.y - BALL_AHEAD_THRESHOLD:
                ahead_ball_frames += 1
        
        # Role detection (relative to teammates)
        teammates = [p for p in frame.players if p.team == player_team and p.player_id != player_id]
        
        if teammates:
            # Calculate distance to teammates
            teammate_distances = []
            for teammate in teammates:
                teammate_dist = _calculate_distance(player_pos, teammate.position)
                teammate_distances.append(teammate_dist)
                total_distance_to_teammates += teammate_dist
                teammate_distance_count += 1
            
            # Determine role based on distance to ball relative to teammates
            teammate_ball_distances = [_calculate_distance(t.position, ball_pos) for t in teammates]
            player_ball_distance = distance_to_ball
            
            # Count how many teammates are closer to ball
            closer_teammates = sum(1 for dist in teammate_ball_distances if dist < player_ball_distance)
            
            if closer_teammates == 0:
                first_man_frames += 1
            elif closer_teammates == 1:
                second_man_frames += 1
            else:
                third_man_frames += 1
        else:
            # No teammates - player is always first man
            first_man_frames += 1

        prev_timestamp = frame.timestamp
    
    # Calculate percentages and averages
    if total_frames == 0:
        return _empty_positioning()
    
    behind_ball_pct = (behind_ball_frames / total_frames) * 100.0
    ahead_ball_pct = (ahead_ball_frames / total_frames) * 100.0
    avg_distance_to_ball_m = (total_distance_to_ball / total_frames) / 100.0  # Convert UU to meters
    
    avg_distance_to_teammate_m = 0.0
    if teammate_distance_count > 0:
        avg_distance_to_teammate_m = (total_distance_to_teammates / teammate_distance_count) / 100.0
    
    first_man_pct = (first_man_frames / total_frames) * 100.0
    second_man_pct = (second_man_frames / total_frames) * 100.0
    # Third man is only meaningful in 3v3 (team_size >= 3)
    third_man_pct = (third_man_frames / total_frames) * 100.0 if team_size >= 3 else None

    return {
        "time_offensive_half_s": round(time_offensive_half, 2),
        "time_defensive_half_s": round(time_defensive_half, 2),
        "time_offensive_third_s": round(time_offensive_third, 2),
        "time_middle_third_s": round(time_middle_third, 2),
        "time_defensive_third_s": round(time_defensive_third, 2),
        "behind_ball_pct": round(behind_ball_pct, 2),
        "ahead_ball_pct": round(ahead_ball_pct, 2),
        "avg_distance_to_ball_m": round(avg_distance_to_ball_m, 2),
        "avg_distance_to_teammate_m": round(avg_distance_to_teammate_m, 2),
        "first_man_pct": round(first_man_pct, 2),
        "second_man_pct": round(second_man_pct, 2),
        "third_man_pct": round(third_man_pct, 2) if third_man_pct is not None else None
    }


def _analyze_team_positioning(frames: list[Frame], team: str) -> dict[str, Any]:
    """Analyze positioning metrics for a team (aggregate all players)."""

    # Get all unique player IDs for the team and determine team size
    team_players = set()
    team_id = 0 if team == "BLUE" else 1

    for frame in frames:
        for player in frame.players:
            if player.team == team_id:
                team_players.add(player.player_id)

    team_size = len(team_players)
    if team_size == 0:
        return _empty_positioning(team_size=0)

    # Aggregate metrics from all team members
    # third_man_pct is only meaningful for 3v3 (team_size >= 3)
    team_metrics = {
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
        "third_man_pct": 0.0 if team_size >= 3 else None
    }

    for player_id in team_players:
        player_metrics = _analyze_player_positioning(frames, player_id)

        # Sum time-based metrics
        team_metrics["time_offensive_half_s"] += player_metrics["time_offensive_half_s"]
        team_metrics["time_defensive_half_s"] += player_metrics["time_defensive_half_s"]
        team_metrics["time_offensive_third_s"] += player_metrics["time_offensive_third_s"]
        team_metrics["time_middle_third_s"] += player_metrics["time_middle_third_s"]
        team_metrics["time_defensive_third_s"] += player_metrics["time_defensive_third_s"]

        # Average percentage and distance metrics
        team_metrics["behind_ball_pct"] += player_metrics["behind_ball_pct"]
        team_metrics["ahead_ball_pct"] += player_metrics["ahead_ball_pct"]
        team_metrics["avg_distance_to_ball_m"] += player_metrics["avg_distance_to_ball_m"]
        team_metrics["avg_distance_to_teammate_m"] += player_metrics["avg_distance_to_teammate_m"]
        team_metrics["first_man_pct"] += player_metrics["first_man_pct"]
        team_metrics["second_man_pct"] += player_metrics["second_man_pct"]
        # Only aggregate third_man_pct if it's meaningful (3v3)
        if team_size >= 3 and player_metrics["third_man_pct"] is not None:
            team_metrics["third_man_pct"] += player_metrics["third_man_pct"]

    # Calculate team averages for percentage metrics
    if team_size > 0:
        team_metrics["behind_ball_pct"] = round(team_metrics["behind_ball_pct"] / team_size, 2)
        team_metrics["ahead_ball_pct"] = round(team_metrics["ahead_ball_pct"] / team_size, 2)
        team_metrics["avg_distance_to_ball_m"] = round(team_metrics["avg_distance_to_ball_m"] / team_size, 2)
        team_metrics["avg_distance_to_teammate_m"] = round(team_metrics["avg_distance_to_teammate_m"] / team_size, 2)
        team_metrics["first_man_pct"] = round(team_metrics["first_man_pct"] / team_size, 2)
        team_metrics["second_man_pct"] = round(team_metrics["second_man_pct"] / team_size, 2)
        if team_size >= 3:
            team_metrics["third_man_pct"] = round(team_metrics["third_man_pct"] / team_size, 2)

    return team_metrics


def calculate_rotation_compliance(
    frames: list[Frame],
    player_id: str
) -> dict[str, Any]:
    """Calculate rotation compliance score and detect flags for a player.
    
    This is called separately for player-only analysis and included in
    the player analysis results.
    
    Returns:
        Dictionary with rotation compliance:
        {
            "score_0_to_100": float,
            "flags": list[str]
        }
    """
    if not frames:
        return {"score_0_to_100": 0.0, "flags": []}
    
    # Initialize violation counters
    double_commit_count = 0
    overcommit_count = 0
    out_of_position_time = 0.0
    total_frames = 0
    
    flags = []
    
    # Determine player's team
    player_team = None
    for frame in frames:
        player_frame = _find_player_in_frame(frame, player_id)
        if player_frame:
            player_team = player_frame.team
            break
    
    if player_team is None:
        return {"score_0_to_100": 0.0, "flags": []}
    
    for frame in frames:
        player_frame = _find_player_in_frame(frame, player_id)
        if not player_frame:
            continue
        
        total_frames += 1
        
        # Get teammates
        teammates = [p for p in frame.players if p.team == player_team and p.player_id != player_id]
        ball_pos = frame.ball.position
        player_pos = player_frame.position
        
        # Check for double commit (multiple teammates very close to ball)
        close_to_ball_count = 0
        distance_to_ball = _calculate_distance(player_pos, ball_pos)
        
        if distance_to_ball <= DOUBLE_COMMIT_DISTANCE:
            close_to_ball_count += 1
        
        for teammate in teammates:
            teammate_ball_dist = _calculate_distance(teammate.position, ball_pos)
            if teammate_ball_dist <= DOUBLE_COMMIT_DISTANCE:
                close_to_ball_count += 1
        
        if close_to_ball_count >= 2:
            double_commit_count += 1
        
        # Check for overcommit (last man going forward with low boost)
        if teammates:
            # Check if this player is furthest back
            teammate_y_positions = [t.position.y for t in teammates]
            
            if player_team == 0:  # Blue team
                is_last_man = player_pos.y <= min(teammate_y_positions)
                is_going_forward = player_pos.y > 0  # In offensive half
            else:  # Orange team
                is_last_man = player_pos.y >= max(teammate_y_positions)
                is_going_forward = player_pos.y < 0  # In offensive half
            
            if is_last_man and is_going_forward and player_frame.boost_amount < OVERCOMMIT_BOOST_THRESHOLD:
                overcommit_count += 1
    
    # Calculate base score (start with 100, deduct for violations)
    base_score = 100.0
    
    if total_frames > 0:
        double_commit_rate = double_commit_count / total_frames
        overcommit_rate = overcommit_count / total_frames
        
        # Deduct points based on violation rates
        base_score -= (double_commit_rate * 30.0)  # Up to 30 points for double commits
        base_score -= (overcommit_rate * 25.0)     # Up to 25 points for overcommits
    
    # Clamp score to 0-100 range
    final_score = max(0.0, min(100.0, base_score))
    
    # Generate flags based on violation thresholds
    if total_frames > 0:
        if double_commit_count / total_frames > 0.1:  # More than 10% of frames
            flags.append("double_commit")
        
        if overcommit_count / total_frames > 0.05:    # More than 5% of frames
            flags.append("last_man_overcommit")
        
        # Additional heuristic flags
        if final_score < 70:
            flags.append("poor_rotation")
        if final_score < 50:
            flags.append("critical_positioning")
    
    return {
        "score_0_to_100": round(final_score, 2),
        "flags": flags
    }


def _find_player_in_frame(frame: Frame, player_id: str) -> PlayerFrame | None:
    """Find player frame by ID, or None if not found."""
    for player in frame.players:
        if player.player_id == player_id:
            return player
    return None


def _calculate_distance(pos1: Vec3, pos2: Vec3) -> float:
    """Calculate 3D distance between two positions."""
    dx = pos1.x - pos2.x
    dy = pos1.y - pos2.y
    dz = pos1.z - pos2.z
    return math.sqrt(dx ** 2 + dy ** 2 + dz ** 2)


def _empty_positioning(team_size: int = 0) -> dict[str, Any]:
    """Return empty positioning dict for degraded scenarios.

    Args:
        team_size: Number of players on the team. If < 3, third_man_pct is None.
    """
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
        "third_man_pct": 0.0 if team_size >= 3 else None
    }


def _frame_duration(
    frames: list[Frame],
    index: int,
    prev_timestamp: float | None,
) -> float:
    """Compute the duration represented by a frame for positioning analysis."""

    if index < len(frames) - 1:
        next_dt = frames[index + 1].timestamp - frames[index].timestamp
        if next_dt > 0:
            return next_dt

    if prev_timestamp is not None:
        prev_dt = frames[index].timestamp - prev_timestamp
        if prev_dt > 0:
            return prev_dt

    return 0.033
