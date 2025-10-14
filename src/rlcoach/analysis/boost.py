"""Boost economy analysis for Rocket League replay data.

This module computes boost usage and collection metrics:
- BPM (Boost Per Minute) and BCPM (Boost Collected Per Minute)
- Time spent at 0 and 100 boost
- Overfill and waste calculations
- Boost pad collection tracking
- Stolen boost analysis

All calculations use frame-by-frame analysis with event correlation
for comprehensive boost economy assessment.
"""

from __future__ import annotations

import math
from bisect import bisect_left
from typing import Any, Sequence
from ..events import BoostPickupEvent, CENTERLINE_TOLERANCE
from ..parser.types import Header, Frame
from ..field_constants import Vec3


# Boost analysis thresholds (aligned with Ballchasing parity)
ZERO_BOOST_THRESHOLD = 3.0  # Consider < 3 as "zero boost"
FULL_BOOST_THRESHOLD = 99.0  # Consider >= 99 as "full boost"
OVERFILL_THRESHOLD = 80.0  # Overfill when collecting above this amount
SUPERSONIC_SPEED_THRESHOLD = 2300.0  # Speed at which boost provides minimal benefit
WASTE_DETECTION_MIN_BOOST = 10.0  # Minimum boost to consider for waste detection


def analyze_boost(
    frames: list[Frame],
    events: dict[str, list[Any]],
    player_id: str | None = None,
    team: str | None = None,
    header: Header | None = None,
) -> dict[str, Any]:
    """Analyze boost economy metrics for a player or team.
    
    Args:
        frames: Normalized frame data for boost state tracking
        events: Dictionary containing detected events by type
        player_id: If provided, analyze specific player; otherwise team analysis
        team: Team filter ("BLUE" or "ORANGE"), required if player_id not provided
        header: Optional header for match context
        
    Returns:
        Dictionary matching schema boost definition:
        {
            "bpm": float,
            "bcpm": float,
            "avg_boost": float,
            "time_zero_boost_s": float,
            "time_hundred_boost_s": float,
            "amount_collected": float,
            "amount_stolen": float,
            "big_pads": int,
            "small_pads": int,
            "stolen_big_pads": int,
            "stolen_small_pads": int,
            "overfill": float,
            "waste": float
        }
    """
    # Extract boost pickup events
    boost_pickups = events.get('boost_pickups', [])

    # Calculate match duration from frames
    match_duration = frames[-1].timestamp - frames[0].timestamp if frames else 0.0
    frame_timestamps = [frame.timestamp for frame in frames]

    if player_id:
        return _analyze_player_boost(frames, frame_timestamps, boost_pickups, player_id, match_duration)
    elif team:
        return _analyze_team_boost(frames, frame_timestamps, boost_pickups, team, match_duration)
    else:
        return _empty_boost()


def _analyze_player_boost(
    frames: list[Frame],
    frame_timestamps: Sequence[float],
    pickups: list[BoostPickupEvent],
    player_id: str,
    match_duration: float,
) -> dict[str, Any]:
    """Analyze boost metrics for a specific player."""
    
    # Initialize counters
    time_zero_boost = 0.0
    time_hundred_boost = 0.0
    total_boost_sum = 0.0
    frame_count = 0
    waste = 0.0
    
    # Track previous frame for calculations
    prev_boost = None
    prev_speed = None
    prev_timestamp = None
    
    # Process frames for time-based metrics
    for frame in frames:
        player_frame = _find_player_in_frame(frame, player_id)
        if not player_frame:
            continue
            
        frame_count += 1
        boost_amount = player_frame.boost_amount
        total_boost_sum += boost_amount
        
        # Calculate time deltas based on previous boost state
        if prev_timestamp is not None:
            time_delta = frame.timestamp - prev_timestamp
            
            # Time at zero boost (use previous boost level)
            if prev_boost is not None and prev_boost <= ZERO_BOOST_THRESHOLD:
                time_zero_boost += time_delta
            
            # Time at full boost (use previous boost level)
            if prev_boost is not None and prev_boost >= FULL_BOOST_THRESHOLD:
                time_hundred_boost += time_delta
                
            # Waste detection - boost spent at supersonic or with minimal benefit
            if prev_boost is not None and prev_boost > boost_amount:
                boost_consumed = prev_boost - boost_amount
                player_speed = _calculate_speed(player_frame.velocity)
                
                # Waste if consuming boost while already supersonic
                if (player_speed > SUPERSONIC_SPEED_THRESHOLD and 
                    boost_consumed > WASTE_DETECTION_MIN_BOOST):
                    waste += boost_consumed * 0.7  # Heuristic factor
                    
                # Waste if consuming boost with minimal speed benefit
                elif (prev_speed and player_speed < prev_speed + 50.0 and
                      boost_consumed > WASTE_DETECTION_MIN_BOOST):
                    waste += boost_consumed * 0.3  # Partial waste
            
        prev_boost = boost_amount
        prev_speed = _calculate_speed(player_frame.velocity) if player_frame.velocity else 0.0
        prev_timestamp = frame.timestamp
    
    # Process pickup events for collection metrics
    amount_collected = 0.0
    amount_stolen = 0.0
    big_pads = 0
    small_pads = 0
    stolen_big_pads = 0
    stolen_small_pads = 0
    overfill = 0.0
    player_team = _infer_player_team(frames, player_id)
    
    for pickup in pickups:
        if pickup.player_id != player_id:
            continue

        pad_capacity = 100.0 if pickup.pad_type == "BIG" else 12.0
        pickup_gain, boost_before, boost_after = _resolve_pickup_amount(
            pickup,
            pad_capacity,
            frames,
            frame_timestamps,
            player_id,
        )

        effective_gain = min(pickup_gain, pad_capacity)
        amount_collected += effective_gain

        pickup_is_stolen = bool(pickup.stolen)
        if pickup_is_stolen and player_team is not None:
            y_candidates: list[float] = []
            if getattr(pickup, "location", None) is not None:
                loc_y = getattr(pickup.location, "y", None)
                if isinstance(loc_y, (int, float)):
                    y_candidates.append(float(loc_y))
            if pickup.frame is not None and 0 <= pickup.frame < len(frames):
                frame_player = _find_player_in_frame(frames[pickup.frame], player_id)
                if frame_player is not None:
                    y_candidates.append(frame_player.position.y)
            if y_candidates and all(not _is_on_opponent_half(y_val, player_team) for y_val in y_candidates):
                pickup_is_stolen = False

        if pickup_is_stolen:
            amount_stolen += effective_gain

        if pickup.pad_type == "BIG":
            big_pads += 1
            if pickup_is_stolen:
                stolen_big_pads += 1
        else:
            small_pads += 1
            if pickup_is_stolen:
                stolen_small_pads += 1

        if boost_before is not None and boost_before >= OVERFILL_THRESHOLD:
            overfill += max(0.0, pad_capacity - effective_gain)
    
    # Calculate rates (per minute)
    minutes = max(match_duration / 60.0, 1.0)  # Avoid division by zero
    bpm = amount_collected / minutes
    bcpm = (big_pads + small_pads) / minutes
    
    # Calculate average boost
    avg_boost = total_boost_sum / frame_count if frame_count > 0 else 0.0
    
    return {
        "bpm": round(bpm, 2),
        "bcpm": round(bcpm, 2),
        "avg_boost": round(avg_boost, 2),
        "time_zero_boost_s": round(time_zero_boost, 2),
        "time_hundred_boost_s": round(time_hundred_boost, 2),
        "amount_collected": round(amount_collected, 1),
        "amount_stolen": round(amount_stolen, 1),
        "big_pads": big_pads,
        "small_pads": small_pads,
        "stolen_big_pads": stolen_big_pads,
        "stolen_small_pads": stolen_small_pads,
        "overfill": round(overfill, 2),
        "waste": round(waste, 2)
    }


def _resolve_pickup_amount(
    pickup: BoostPickupEvent,
    pad_capacity: float,
    frames: list[Frame],
    frame_timestamps: Sequence[float],
    player_id: str,
) -> tuple[float, float | None, float | None]:
    """Resolve boost amount collected for a pickup event with fallbacks."""

    boost_before = _to_float(getattr(pickup, "boost_before", None))
    boost_after = _to_float(getattr(pickup, "boost_after", None))
    boost_gain = _to_float(getattr(pickup, "boost_gain", None))

    if boost_before is not None and boost_after is not None:
        gain = boost_after - boost_before
    elif boost_gain is not None:
        gain = boost_gain
        if boost_before is not None and boost_after is None:
            boost_after = boost_before + gain
        elif boost_after is not None and boost_before is None:
            boost_before = max(0.0, boost_after - gain)
    else:
        gain = 0.0

    if (boost_before is None or boost_after is None) and frames:
        frame = _find_frame_at_time(frames, frame_timestamps, pickup.t)
        if frame is not None:
            player_frame = _find_player_in_frame(frame, player_id)
            if player_frame is not None:
                boost_after = float(player_frame.boost_amount)
                if pickup.frame is not None and pickup.frame > 0:
                    prev_idx = max(0, min(len(frames) - 1, pickup.frame - 1))
                    prev_frame = frames[prev_idx]
                    prev_player_frame = _find_player_in_frame(prev_frame, player_id)
                    if prev_player_frame is not None:
                        boost_before = float(prev_player_frame.boost_amount)
                if boost_before is None:
                    boost_before = max(0.0, boost_after - pad_capacity)
                gain = boost_after - boost_before

    gain = max(0.0, gain)
    if gain == 0.0 and boost_gain is not None:
        gain = max(0.0, boost_gain)
    gain = min(gain, 100.0)
    return gain, boost_before, boost_after


def _to_float(value: Any) -> float | None:
    """Convert value to float if possible; otherwise None."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _infer_player_team(frames: list[Frame], player_id: str) -> int | None:
    """Infer player's team from frame data."""
    for frame in frames:
        player_frame = _find_player_in_frame(frame, player_id)
        if player_frame is not None:
            return player_frame.team
    return None


def _is_on_opponent_half(y_value: float, player_team: int) -> bool:
    """Check whether a Y coordinate lies on the opponent half for the given team."""
    if abs(y_value) <= CENTERLINE_TOLERANCE:
        return False
    if player_team == 0:
        return y_value > 0
    if player_team == 1:
        return y_value < 0
    return False


def _analyze_team_boost(
    frames: list[Frame],
    frame_timestamps: Sequence[float],
    pickups: list[BoostPickupEvent],
    team: str,
    match_duration: float,
) -> dict[str, Any]:
    """Analyze aggregated boost metrics for a team."""
    
    # Get all player IDs for this team from frames
    team_players = set()
    team_num = 0 if team == "BLUE" else 1
    
    for frame in frames:
        for player in frame.players:
            if player.team == team_num:
                team_players.add(player.player_id)
    
    if not team_players:
        return _empty_boost()
    
    # Aggregate metrics across all team players
    team_metrics = _empty_boost()
    player_count = len(team_players)
    
    for player_id in team_players:
        player_metrics = _analyze_player_boost(frames, frame_timestamps, pickups, player_id, match_duration)
        
        # Sum most metrics
        team_metrics["amount_collected"] += player_metrics["amount_collected"]
        team_metrics["amount_stolen"] += player_metrics["amount_stolen"]
        team_metrics["big_pads"] += player_metrics["big_pads"]
        team_metrics["small_pads"] += player_metrics["small_pads"]
        team_metrics["stolen_big_pads"] += player_metrics["stolen_big_pads"]
        team_metrics["stolen_small_pads"] += player_metrics["stolen_small_pads"]
        team_metrics["overfill"] += player_metrics["overfill"]
        team_metrics["waste"] += player_metrics["waste"]
        team_metrics["time_zero_boost_s"] += player_metrics["time_zero_boost_s"]
        team_metrics["time_hundred_boost_s"] += player_metrics["time_hundred_boost_s"]
        
        # Average these metrics
        team_metrics["avg_boost"] += player_metrics["avg_boost"]
    
    # Calculate team averages and rates
    minutes = max(match_duration / 60.0, 1.0)
    team_metrics["bpm"] = round(team_metrics["amount_collected"] / minutes, 2)
    team_metrics["bcpm"] = round((team_metrics["big_pads"] + team_metrics["small_pads"]) / minutes, 2)
    team_metrics["avg_boost"] = round(team_metrics["avg_boost"] / player_count, 2)
    
    # Round accumulated values
    for key in ["amount_collected", "amount_stolen", "overfill", "waste", 
                "time_zero_boost_s", "time_hundred_boost_s"]:
        team_metrics[key] = round(team_metrics[key], 2)
    
    return team_metrics


def _empty_boost() -> dict[str, Any]:
    """Return empty boost dict for degraded scenarios."""
    return {
        "bpm": 0.0,
        "bcpm": 0.0,
        "avg_boost": 0.0,
        "time_zero_boost_s": 0.0,
        "time_hundred_boost_s": 0.0,
        "amount_collected": 0.0,
        "amount_stolen": 0.0,
        "big_pads": 0,
        "small_pads": 0,
        "stolen_big_pads": 0,
        "stolen_small_pads": 0,
        "overfill": 0.0,
        "waste": 0.0
    }


def _find_player_in_frame(frame: Frame, player_id: str) -> Any | None:
    """Find specific player's data in a frame."""
    for player in frame.players:
        if player.player_id == player_id:
            return player
    return None


def _find_frame_at_time(
    frames: list[Frame],
    timestamps: Sequence[float],
    timestamp: float,
) -> Frame | None:
    """Find frame closest to given timestamp using binary search."""
    if not frames:
        return None

    idx = bisect_left(timestamps, timestamp)

    if idx <= 0:
        return frames[0]
    if idx >= len(frames):
        return frames[-1]

    prev_frame = frames[idx - 1]
    next_frame = frames[idx]

    if timestamp - prev_frame.timestamp <= next_frame.timestamp - timestamp:
        return prev_frame
    return next_frame


def _calculate_speed(velocity: Vec3) -> float:
    """Calculate speed magnitude from velocity vector."""
    if not velocity:
        return 0.0
    return math.sqrt(velocity.x**2 + velocity.y**2 + velocity.z**2)
