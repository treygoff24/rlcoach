"""Movement and speed analysis for Rocket League replay data.

This module computes movement and speed metrics from frame data:
- Speed buckets: time in slow, boost speed, and supersonic ranges
- Ground vs air time analysis with height classifications
- Powerslide detection and duration tracking
- Aerial detection and time accounting
- Average speed calculations

All calculations use deterministic frame-by-frame analysis with
fixed thresholds for consistent results across runs.
"""

from __future__ import annotations

import math
from typing import Any
from ..parser.types import Header, Frame, PlayerFrame
from ..field_constants import Vec3


# Movement analysis constants (deterministic thresholds)
SLOW_SPEED_UU_S = 500.0  # Unreal Units per second - slow movement
BOOST_SPEED_UU_S = 1410.0  # Speed when boost provides significant benefit
SUPERSONIC_SPEED_UU_S = 2300.0  # Supersonic threshold

# Height thresholds for air/ground classification
GROUND_HEIGHT = 25.0  # Below this is considered ground
LOW_AIR_HEIGHT = 200.0  # Low air threshold
HIGH_AIR_HEIGHT = 500.0  # High air threshold

# Powerslide detection thresholds
MIN_POWERSLIDE_DURATION = 0.1  # Minimum seconds for powerslide detection
MIN_POWERSLIDE_ANGULAR_VELOCITY = 2.0  # Radians per second

# Aerial detection thresholds  
MIN_AERIAL_HEIGHT = 200.0  # Minimum height to consider aerial
MIN_AERIAL_DURATION = 0.5  # Minimum seconds airborne to count as aerial


def analyze_movement(
    frames: list[Frame],
    events: dict[str, list[Any]],
    player_id: str | None = None,
    team: str | None = None,
    header: Header | None = None,
) -> dict[str, Any]:
    """Analyze movement and speed metrics for a player or team.
    
    Args:
        frames: Normalized frame data for movement analysis
        events: Dictionary containing detected events (not used for movement)
        player_id: If provided, analyze specific player; otherwise team analysis
        team: Team filter ("BLUE" or "ORANGE"), required if player_id not provided
        header: Optional header for match context
        
    Returns:
        Dictionary matching schema movement definition:
        {
            "avg_speed_kph": float,
            "time_slow_s": float,
            "time_boost_speed_s": float,
            "time_supersonic_s": float,
            "time_ground_s": float,
            "time_low_air_s": float,
            "time_high_air_s": float,
            "powerslide_count": int,
            "powerslide_duration_s": float,
            "aerial_count": int,
            "aerial_time_s": float
        }
    """
    if not frames:
        return _empty_movement()
    
    if player_id:
        return _analyze_player_movement(frames, player_id)
    elif team:
        return _analyze_team_movement(frames, team)
    else:
        return _empty_movement()


def _analyze_player_movement(frames: list[Frame], player_id: str) -> dict[str, Any]:
    """Analyze movement metrics for a specific player."""
    
    # Initialize counters
    total_speed = 0.0
    frame_count = 0
    
    time_slow = 0.0
    time_boost_speed = 0.0
    time_supersonic = 0.0
    time_ground = 0.0
    time_low_air = 0.0
    time_high_air = 0.0
    
    powerslide_count = 0
    powerslide_duration = 0.0
    aerial_count = 0
    aerial_time = 0.0
    
    # Track state for event detection
    prev_player_frame = None
    prev_timestamp = None
    in_powerslide = False
    powerslide_start = 0.0
    in_aerial = False
    aerial_start = 0.0
    
    for frame in frames:
        player_frame = _find_player_in_frame(frame, player_id)
        if not player_frame:
            continue
        
        # Calculate speed and height
        speed = _calculate_speed(player_frame.velocity)
        height = player_frame.position.z
        total_speed += speed
        frame_count += 1
        
        # Calculate frame duration for this frame
        is_final_frame = (frame == frames[-1])
        
        if is_final_frame:
            # Final frame: estimate duration from previous interval or use default
            if len(frames) >= 2 and prev_timestamp is not None:
                # Use same duration as the previous interval
                prev_interval = frame.timestamp - prev_timestamp
                frame_dt = prev_interval
            else:
                frame_dt = 0.033  # Default for single frame
        else:
            # Non-final frame: use time to next frame
            current_index = frames.index(frame)
            next_frame = frames[current_index + 1]
            frame_dt = next_frame.timestamp - frame.timestamp
        
        # Speed bucket classification using current frame's state
        if speed <= SLOW_SPEED_UU_S:
            time_slow += frame_dt
        elif speed < BOOST_SPEED_UU_S:
            time_boost_speed += frame_dt
        elif speed >= SUPERSONIC_SPEED_UU_S or player_frame.is_supersonic:
            time_supersonic += frame_dt
        else:
            time_boost_speed += frame_dt
        
        # Height classification using current frame's state
        if height <= GROUND_HEIGHT or player_frame.is_on_ground:
            time_ground += frame_dt
        elif height <= HIGH_AIR_HEIGHT:  # 25 < height <= 500
            time_low_air += frame_dt
        else:  # height > 500
            time_high_air += frame_dt
        
        # Powerslide detection
        is_powersliding = _detect_powerslide(player_frame, prev_player_frame)
        if is_powersliding and not in_powerslide:
            # Starting powerslide
            in_powerslide = True
            powerslide_start = frame.timestamp
        elif not is_powersliding and in_powerslide:
            # Ending powerslide
            slide_duration = frame.timestamp - powerslide_start
            if slide_duration >= MIN_POWERSLIDE_DURATION:
                powerslide_count += 1
                powerslide_duration += slide_duration
            in_powerslide = False
        
        # Aerial detection
        is_aerial = height >= MIN_AERIAL_HEIGHT and not player_frame.is_on_ground
        if is_aerial and not in_aerial:
            # Starting aerial
            in_aerial = True
            aerial_start = frame.timestamp
        elif not is_aerial and in_aerial:
            # Ending aerial
            air_duration = frame.timestamp - aerial_start
            if air_duration >= MIN_AERIAL_DURATION:
                aerial_count += 1
                aerial_time += air_duration
            in_aerial = False
        
        prev_player_frame = player_frame
        prev_timestamp = frame.timestamp
    
    # All frame handling is done in the main loop now
    
    # Handle ongoing powerslide at end
    if in_powerslide and prev_timestamp:
        slide_duration = prev_timestamp - powerslide_start
        if slide_duration >= MIN_POWERSLIDE_DURATION:
            powerslide_count += 1
            powerslide_duration += slide_duration
    
    # Handle ongoing aerial at end
    if in_aerial and prev_timestamp:
        air_duration = prev_timestamp - aerial_start
        if air_duration >= MIN_AERIAL_DURATION:
            aerial_count += 1
            aerial_time += air_duration
    
    # Calculate average speed in kph
    avg_speed_kph = 0.0
    if frame_count > 0:
        avg_speed_uu_s = total_speed / frame_count
        avg_speed_kph = _uu_s_to_kph(avg_speed_uu_s)
    
    return {
        "avg_speed_kph": round(avg_speed_kph, 2),
        "time_slow_s": round(time_slow, 2),
        "time_boost_speed_s": round(time_boost_speed, 2),
        "time_supersonic_s": round(time_supersonic, 2),
        "time_ground_s": round(time_ground, 2),
        "time_low_air_s": round(time_low_air, 2),
        "time_high_air_s": round(time_high_air, 2),
        "powerslide_count": powerslide_count,
        "powerslide_duration_s": round(powerslide_duration, 2),
        "aerial_count": aerial_count,
        "aerial_time_s": round(aerial_time, 2)
    }


def _analyze_team_movement(frames: list[Frame], team: str) -> dict[str, Any]:
    """Analyze movement metrics for a team (aggregate all players)."""
    
    # Get all unique player IDs for the team
    team_players = set()
    team_id = 0 if team == "BLUE" else 1
    
    for frame in frames:
        for player in frame.players:
            if player.team == team_id:
                team_players.add(player.player_id)
    
    if not team_players:
        return _empty_movement()
    
    # Aggregate metrics from all team members
    team_metrics = _empty_movement()
    player_count = len(team_players)
    
    for player_id in team_players:
        player_metrics = _analyze_player_movement(frames, player_id)
        
        # Sum time-based metrics
        team_metrics["time_slow_s"] += player_metrics["time_slow_s"]
        team_metrics["time_boost_speed_s"] += player_metrics["time_boost_speed_s"]
        team_metrics["time_supersonic_s"] += player_metrics["time_supersonic_s"]
        team_metrics["time_ground_s"] += player_metrics["time_ground_s"]
        team_metrics["time_low_air_s"] += player_metrics["time_low_air_s"]
        team_metrics["time_high_air_s"] += player_metrics["time_high_air_s"]
        team_metrics["powerslide_duration_s"] += player_metrics["powerslide_duration_s"]
        team_metrics["aerial_time_s"] += player_metrics["aerial_time_s"]
        
        # Sum count metrics
        team_metrics["powerslide_count"] += player_metrics["powerslide_count"]
        team_metrics["aerial_count"] += player_metrics["aerial_count"]
        
        # Average speed calculation
        team_metrics["avg_speed_kph"] += player_metrics["avg_speed_kph"]
    
    # Calculate team average speed
    if player_count > 0:
        team_metrics["avg_speed_kph"] = round(team_metrics["avg_speed_kph"] / player_count, 2)
    
    return team_metrics


def _find_player_in_frame(frame: Frame, player_id: str) -> PlayerFrame | None:
    """Find player frame by ID, or None if not found."""
    for player in frame.players:
        if player.player_id == player_id:
            return player
    return None


def _calculate_speed(velocity: Vec3) -> float:
    """Calculate speed magnitude from velocity vector."""
    return math.sqrt(velocity.x ** 2 + velocity.y ** 2 + velocity.z ** 2)


def _detect_powerslide(current: PlayerFrame, previous: PlayerFrame | None) -> bool:
    """Detect if player is currently powersliding based on frame data."""
    if not previous or not current.is_on_ground:
        return False
    
    # Calculate angular velocity magnitude from rotation difference
    dt = 0.033  # Approximate frame time
    yaw_diff = abs(current.rotation.y - previous.rotation.y)
    angular_velocity = yaw_diff / dt
    
    # Powerslide detected if high angular velocity while on ground
    return angular_velocity >= MIN_POWERSLIDE_ANGULAR_VELOCITY


def _uu_s_to_kph(speed_uu_s: float) -> float:
    """Convert Unreal Units per second to kilometers per hour."""
    # 1 UU = ~1.9 cm, 3600 seconds per hour, 1000 m per km
    return speed_uu_s * 0.019 * 3.6


def _empty_movement() -> dict[str, Any]:
    """Return empty movement dict for degraded scenarios."""
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