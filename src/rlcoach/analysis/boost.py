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
from typing import Any, Sequence
from ..events import BoostPickupEvent, PAD_NEUTRAL_TOLERANCE
from ..parser.types import Header, Frame
from ..field_constants import Vec3, FIELD


# Boost analysis thresholds (aligned with Ballchasing parity)
ZERO_BOOST_THRESHOLD = 3.0  # Consider < 3 as "zero boost"
FULL_BOOST_THRESHOLD = 99.0  # Consider >= 99 as "full boost"
OVERFILL_THRESHOLD = 80.0  # Overfill when collecting above this amount
OVERFILL_BASELINE = 85.0  # Baseline boost level for wasted big-pad capacity
SUPERSONIC_SPEED_THRESHOLD = 2300.0  # Speed at which boost provides minimal benefit
WASTE_DETECTION_MIN_BOOST = 10.0  # Minimum boost to consider for waste detection
BIG_GAIN_THRESHOLD = 70.0
SMALL_PAD_UNIT = 12.0
RESPAWN_GAIN = 33.0
PAD_EVENT_MATCH_WINDOW = 1.1
PAD_GAIN_MISMATCH_TOLERANCE = 24.0
FALLBACK_BIG_GAIN_THRESHOLD = 45.0
PAD_POSITION_TRUST_RADIUS_SQ = 600.0 * 600.0


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

    player_pickups = [p for p in pickups if p.player_id == player_id]
    delta_events = _collect_boost_delta_events(frames, player_id)

    if player_pickups:
        for pickup in player_pickups:
            gain = _resolve_pickup_gain(pickup)
            amount_collected += gain
            if pickup.stolen:
                amount_stolen += gain

            if pickup.pad_type == "BIG":
                big_pads += 1
                if pickup.stolen:
                    stolen_big_pads += 1
            else:
                small_pads += 1
                if pickup.stolen:
                    stolen_small_pads += 1

            overfill += _compute_overfill(
                pickup.pad_type,
                _to_float(pickup.boost_before),
                _to_float(pickup.boost_after),
                gain,
            )

    elif delta_events:
        used_pickups: set[int] = set()
        for event in delta_events:
            gain = event["gain"]
            if gain <= 0.5:
                continue

            match_result = _match_pickup_for_delta(
                event["timestamp"],
                player_pickups,
                used_pickups,
                window=PAD_EVENT_MATCH_WINDOW,
            )

            pickup_match: BoostPickupEvent | None = None
            match_before = None
            match_after = None
            event_pos = event.get("position")
            pos_y: float | None = event_pos.y if event_pos is not None else None

            if match_result is not None:
                match_idx, candidate = match_result
                raw_candidate_gain = _to_float(candidate.boost_gain)
                candidate_gain = raw_candidate_gain if raw_candidate_gain is not None else _resolve_pickup_gain(candidate)
                if abs(candidate_gain - gain) > PAD_GAIN_MISMATCH_TOLERANCE:
                    pickup_match = None
                else:
                    used_pickups.add(match_idx)
                    pickup_match = candidate
                    match_before = candidate.boost_before
                    match_after = candidate.boost_after

            if pickup_match is not None:
                pad_type = pickup_match.pad_type
                pad_meta = None
                try:
                    pad_idx = int(getattr(pickup_match, "pad_id", -1))
                    if 0 <= pad_idx < len(FIELD.BOOST_PADS):
                        pad_meta = FIELD.BOOST_PADS[pad_idx]
                except (TypeError, ValueError):
                    pad_meta = None
                if pad_meta is not None:
                    if pos_y is None:
                        pos_y = pad_meta.position.y
            else:
                if abs(gain - RESPAWN_GAIN) <= 1.5 and event["before"] <= 1.0:
                    continue
                inferred_pad, pad_dist_sq = _infer_pad_from_position(event_pos)
                pad_trusted = inferred_pad is not None and pad_dist_sq <= PAD_POSITION_TRUST_RADIUS_SQ
                if pad_trusted and inferred_pad is not None:
                    pad_is_big = inferred_pad.is_big
                    override_big = False
                    if not pad_is_big and gain >= FALLBACK_BIG_GAIN_THRESHOLD:
                        pad_is_big = True
                        override_big = True
                    pad_type = "BIG" if pad_is_big else "SMALL"
                    if pos_y is None:
                        if override_big:
                            pos_y = event_pos.y if event_pos is not None else None
                        else:
                            pos_y = inferred_pad.position.y
                else:
                    pad_type = "BIG" if gain >= FALLBACK_BIG_GAIN_THRESHOLD else "SMALL"
                    if pos_y is None and event_pos is not None:
                        pos_y = event_pos.y
                if pos_y is None:
                    pos_y = 0.0
                match_before = event["before"]
                match_after = event["after"]

            if pos_y is None:
                pos_y = 0.0
            stolen = _position_is_stolen(pos_y, player_team)

            amount_collected += gain
            if stolen:
                amount_stolen += gain

            if pad_type == "BIG":
                big_pads += 1
                if stolen:
                    stolen_big_pads += 1
            else:
                small_count = max(1, int(round(gain / SMALL_PAD_UNIT))) if gain >= 6.0 else 1
                small_pads += small_count
                if stolen:
                    stolen_small_pads += small_count

            before_val = _to_float(match_before)
            after_val = _to_float(match_after)
            if before_val is None:
                before_val = event["before"]
            if after_val is None:
                after_val = event["after"]
            overfill += _compute_overfill(
                pad_type,
                before_val,
                after_val,
                gain,
            )
    
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


def _resolve_pickup_gain(pickup: BoostPickupEvent) -> float:
    """Determine boost gain for a pickup event with fallbacks for partial data."""
    pad_capacity = 100.0 if pickup.pad_type == "BIG" else SMALL_PAD_UNIT
    gain = _to_float(pickup.boost_gain)
    if gain is None:
        gain = 0.0

    before = _to_float(pickup.boost_before)
    after = _to_float(pickup.boost_after)

    if gain >= 0.5:
        return float(gain)

    if before is not None and after is not None:
        diff = after - before
        if diff > 0.5:
            return float(diff)
        available = max(0.0, 100.0 - before)
        if available > 0.5:
            return float(min(pad_capacity, available))
        return 0.0

    if before is not None:
        available = max(0.0, 100.0 - before)
        if available > 0.5:
            return float(min(pad_capacity, available))
        return 0.0

    if after is not None:
        estimated_before = max(0.0, after - pad_capacity)
        diff = after - estimated_before
        if diff > 0.5:
            return float(diff)
        available = max(0.0, 100.0 - estimated_before)
        if available > 0.5:
            return float(min(pad_capacity, available))
        return 0.0

    return float(pad_capacity)


# Boost pickup helpers --------------------------------------------------------


def _compute_overfill(
    pad_type: str,
    boost_before: float | None,
    boost_after: float | None,
    gain: float,
) -> float:
    """Estimate wasted pad capacity (unused potential from the collected pad)."""
    pad_capacity = 100.0 if pad_type == "BIG" else SMALL_PAD_UNIT
    before = boost_before if boost_before is not None else 0.0
    after = boost_after if boost_after is not None else before + gain

    if pad_type != "BIG":
        if before >= OVERFILL_THRESHOLD:
            return max(0.0, pad_capacity - gain)
        return 0.0

    if before < OVERFILL_THRESHOLD:
        return 0.0

    baseline = max(before, OVERFILL_BASELINE)
    used = max(0.0, after - baseline)
    wasted = max(0.0, pad_capacity - used)
    return wasted

def _infer_pad_from_position(position: Vec3 | None) -> tuple[Any | None, float]:
    """Return the nearest boost pad metadata and squared distance for a position."""
    if position is None:
        return None, float("inf")

    best_pad = None
    best_dist_sq = float("inf")
    for pad in FIELD.BOOST_PADS:
        dx = position.x - pad.position.x
        dy = position.y - pad.position.y
        dz = position.z - pad.position.z
        dist_sq = dx * dx + dy * dy + dz * dz
        if dist_sq < best_dist_sq:
            best_dist_sq = dist_sq
            best_pad = pad
    return best_pad, best_dist_sq

def _collect_boost_delta_events(frames: list[Frame], player_id: str) -> list[dict[str, Any]]:
    """Collect positive boost deltas for a player across frames."""
    events: list[dict[str, Any]] = []
    prev_boost: float | None = None
    prev_timestamp: float | None = None

    for frame in frames:
        player_frame = _find_player_in_frame(frame, player_id)
        if player_frame is None:
            continue
        current_boost = float(player_frame.boost_amount)
        if prev_boost is not None and prev_timestamp is not None:
            gain = current_boost - prev_boost
            if gain > 0.5:
                events.append(
                    {
                        "timestamp": frame.timestamp,
                        "gain": gain,
                        "before": prev_boost,
                        "after": current_boost,
                        "position": player_frame.position,
                        "team": player_frame.team,
                    }
                )
        prev_boost = current_boost
        prev_timestamp = frame.timestamp
    return events


def _match_pickup_for_delta(
    timestamp: float,
    pickups: list[BoostPickupEvent],
    used: set[int],
    window: float = 0.15,
) -> tuple[int, BoostPickupEvent] | None:
    """Match a delta event to the nearest detected pickup."""
    best_idx: int | None = None
    best_diff = float("inf")
    for idx, pickup in enumerate(pickups):
        if idx in used:
            continue
        diff = abs(pickup.t - timestamp)
        if diff <= window and diff < best_diff:
            best_idx = idx
            best_diff = diff
    if best_idx is not None:
        return best_idx, pickups[best_idx]
    return None


def _position_is_stolen(y_value: float, player_team: int | None) -> bool:
    """Determine stolen classification based on position."""
    if player_team not in (0, 1):
        return False
    if abs(y_value) <= PAD_NEUTRAL_TOLERANCE:
        return False
    if player_team == 0:
        return y_value > PAD_NEUTRAL_TOLERANCE
    return y_value < -PAD_NEUTRAL_TOLERANCE


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

    # Calculate team rates
    minutes = max(match_duration / 60.0, 1.0)
    team_metrics["bpm"] = round(team_metrics["amount_collected"] / minutes, 2)
    team_metrics["bcpm"] = round((team_metrics["big_pads"] + team_metrics["small_pads"]) / minutes, 2)
    # Team avg_boost is the SUM of player averages (matching ballchasing semantics)
    team_metrics["avg_boost"] = round(team_metrics["avg_boost"], 2)
    
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


def _calculate_speed(velocity: Vec3) -> float:
    """Calculate speed magnitude from velocity vector."""
    if not velocity:
        return 0.0
    return math.sqrt(velocity.x**2 + velocity.y**2 + velocity.z**2)
