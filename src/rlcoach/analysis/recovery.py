"""Recovery analysis module - detect and evaluate car recoveries after aerials/jumps."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from ..parser.types import Frame, PlayerFrame, Vec3


class RecoveryQuality(Enum):
    """Quality classification of a recovery."""

    EXCELLENT = "excellent"  # Smooth landing with immediate momentum retention
    GOOD = "good"  # Clean landing with minor speed loss
    AVERAGE = "average"  # Adequate landing, some control loss
    POOR = "poor"  # Awkward landing, significant momentum/control loss
    FAILED = "failed"  # Landed upside down or bounced significantly


@dataclass(frozen=True)
class RecoveryEvent:
    """A detected recovery event after aerial/jump."""

    timestamp: float
    player_id: str
    landing_position: Vec3
    landing_velocity: Vec3
    quality: RecoveryQuality
    time_airborne: float  # How long the car was in the air
    time_to_control: float  # Time to regain stable ground movement
    peak_height: float  # Maximum height reached during airborne phase
    speed_at_landing: float  # Speed when touching down
    speed_after_recovery: float  # Speed after regaining control
    # Ratio of post-recovery to pre-landing speed (can exceed 1.0 with boost/wavedash)
    momentum_retained: float
    # True if recovery included a wavedash
    was_wavedash: bool = False


@dataclass
class PlayerRecoveryState:
    """Track recovery state for a single player across frames."""

    is_airborne: bool = False
    airborne_start_time: float = 0.0
    peak_height: float = 0.0
    speed_at_takeoff: float = 0.0

    # Landing tracking
    landed_time: float | None = None
    landing_position: Vec3 | None = None
    landing_velocity: Vec3 | None = None
    speed_at_landing: float = 0.0

    # Control recovery tracking
    stable_frames: int = 0
    recovery_complete: bool = False
    wavedash_detected: bool = False


# Detection thresholds
GROUND_HEIGHT_THRESHOLD = 30.0  # Car is on ground if z < this
AIRBORNE_MIN_HEIGHT = 50.0  # Minimum height to count as meaningful airborne
# Velocity change threshold for "stable" (was 100, too strict for fast players)
STABLE_VELOCITY_THRESHOLD = 200.0
# Frames of stable movement = control regained (was 3, reduced for faster detection)
STABLE_FRAMES_REQUIRED = 2
WAVEDASH_WINDOW = 0.3  # Seconds after landing to detect wavedash
WAVEDASH_SPEED_BOOST = 1.15  # Speed increase ratio indicating wavedash
# Minimum airborne time to count as meaningful (was 0.2, reduced to catch more
# recoveries)
MIN_AIRBORNE_TIME = 0.15


def _calculate_speed(velocity: Vec3) -> float:
    """Calculate speed magnitude from velocity vector."""
    return math.sqrt(velocity.x**2 + velocity.y**2 + velocity.z**2)


def _calculate_horizontal_speed(velocity: Vec3) -> float:
    """Calculate horizontal speed (XY plane only)."""
    return math.sqrt(velocity.x**2 + velocity.y**2)


def _assess_recovery_quality(
    time_airborne: float,
    time_to_control: float,
    momentum_retained: float,
    peak_height: float,
    landing_velocity: Vec3,
) -> RecoveryQuality:
    """Assess recovery quality based on landing characteristics.

    Args:
        time_airborne: Duration of airborne phase
        time_to_control: Time to regain control after landing
        momentum_retained: Ratio of post-recovery to pre-landing speed
        peak_height: Maximum height during airborne phase
        landing_velocity: Velocity at moment of landing

    Returns:
        RecoveryQuality classification
    """
    # Failed recovery: landed with significant downward velocity and upside down
    # potential.
    if landing_velocity.z < -800.0:
        return RecoveryQuality.FAILED

    # Score based on multiple factors
    score = 0.0

    # Time to control (faster = better) - weight: 40%
    if time_to_control < 0.1:
        score += 0.4
    elif time_to_control < 0.2:
        score += 0.3
    elif time_to_control < 0.4:
        score += 0.2
    elif time_to_control < 0.6:
        score += 0.1

    # Momentum retention (higher = better) - weight: 40%
    if momentum_retained >= 1.0:
        score += 0.4  # Gained speed (wavedash/boost recovery)
    elif momentum_retained >= 0.85:
        score += 0.35
    elif momentum_retained >= 0.7:
        score += 0.25
    elif momentum_retained >= 0.5:
        score += 0.15

    # Landing velocity (less downward = better) - weight: 20%
    if landing_velocity.z > -200.0:
        score += 0.2
    elif landing_velocity.z > -400.0:
        score += 0.15
    elif landing_velocity.z > -600.0:
        score += 0.1

    # Classify based on score
    if score >= 0.75:
        return RecoveryQuality.EXCELLENT
    elif score >= 0.55:
        return RecoveryQuality.GOOD
    elif score >= 0.35:
        return RecoveryQuality.AVERAGE
    else:
        return RecoveryQuality.POOR


def detect_recoveries_for_player(
    frames: list[Frame],
    player_id: str,
) -> list[RecoveryEvent]:
    """Detect recovery events for a single player from frame data.

    Args:
        frames: Normalized frame data
        player_id: Player ID to analyze

    Returns:
        List of detected recovery events
    """
    events: list[RecoveryEvent] = []
    state = PlayerRecoveryState()

    prev_velocity: Vec3 | None = None

    for frame in frames:
        # Find player in this frame
        player: PlayerFrame | None = None
        for p in frame.players:
            if p.player_id == player_id:
                player = p
                break

        if player is None:
            continue

        timestamp = frame.timestamp
        pos = player.position
        vel = player.velocity
        speed = _calculate_speed(vel)
        _calculate_horizontal_speed(vel)

        is_on_ground = pos.z < GROUND_HEIGHT_THRESHOLD or player.is_on_ground

        # Track airborne state
        if not state.is_airborne and not is_on_ground and pos.z > AIRBORNE_MIN_HEIGHT:
            # Just became airborne
            state.is_airborne = True
            state.airborne_start_time = timestamp
            state.peak_height = pos.z
            state.speed_at_takeoff = speed
            state.recovery_complete = False
            state.wavedash_detected = False
            state.stable_frames = 0
            # If we were tracking a landing but player jumped again before recovery
            # completed, abandon the previous recovery tracking.
            if state.landed_time is not None:
                state.landed_time = None
                state.landing_position = None
                state.landing_velocity = None

        elif state.is_airborne:
            # Still airborne - track peak height
            state.peak_height = max(state.peak_height, pos.z)

            if is_on_ground:
                # Just landed
                state.is_airborne = False
                state.landed_time = timestamp
                state.landing_position = pos
                state.landing_velocity = vel
                state.speed_at_landing = speed

        # Track recovery after landing
        if state.landed_time is not None and not state.recovery_complete:
            time_since_landing = timestamp - state.landed_time

            # Check for wavedash (speed boost shortly after landing)
            if (
                not state.wavedash_detected
                and time_since_landing < WAVEDASH_WINDOW
                and speed > state.speed_at_landing * WAVEDASH_SPEED_BOOST
            ):
                state.wavedash_detected = True

            # Check for stable movement (velocity not changing dramatically)
            if prev_velocity is not None:
                vel_change = _calculate_speed(
                    Vec3(
                        vel.x - prev_velocity.x,
                        vel.y - prev_velocity.y,
                        vel.z - prev_velocity.z,
                    )
                )
                if vel_change < STABLE_VELOCITY_THRESHOLD and is_on_ground:
                    state.stable_frames += 1
                else:
                    state.stable_frames = 0

            # Recovery complete when stable for enough frames
            if (
                state.stable_frames >= STABLE_FRAMES_REQUIRED
                or time_since_landing > 1.0
            ):
                state.recovery_complete = True

                time_airborne = state.landed_time - state.airborne_start_time
                time_to_control = timestamp - state.landed_time

                # Only record meaningful recoveries
                if (
                    time_airborne >= MIN_AIRBORNE_TIME
                    and state.peak_height >= AIRBORNE_MIN_HEIGHT
                ):
                    momentum_retained = (
                        speed / state.speed_at_landing
                        if state.speed_at_landing > 10.0
                        else 1.0
                    )

                    quality = _assess_recovery_quality(
                        time_airborne=time_airborne,
                        time_to_control=time_to_control,
                        momentum_retained=momentum_retained,
                        peak_height=state.peak_height,
                        landing_velocity=state.landing_velocity or Vec3(0, 0, 0),
                    )

                    events.append(
                        RecoveryEvent(
                            timestamp=state.landed_time,
                            player_id=player_id,
                            landing_position=state.landing_position or pos,
                            landing_velocity=state.landing_velocity or Vec3(0, 0, 0),
                            quality=quality,
                            time_airborne=round(time_airborne, 3),
                            time_to_control=round(time_to_control, 3),
                            peak_height=round(state.peak_height, 2),
                            speed_at_landing=round(state.speed_at_landing, 2),
                            speed_after_recovery=round(speed, 2),
                            momentum_retained=round(momentum_retained, 3),
                            was_wavedash=state.wavedash_detected,
                        )
                    )

                # Reset for next recovery
                state.landed_time = None
                state.landing_position = None
                state.landing_velocity = None

        prev_velocity = vel

    return events


def analyze_recoveries(frames: list[Frame]) -> dict:
    """Analyze recoveries for all players in replay.

    Args:
        frames: Normalized frame data

    Returns:
        Dict with recovery analysis results
    """
    # Get all unique player IDs
    player_ids: set[str] = set()
    for frame in frames:
        for player in frame.players:
            player_ids.add(player.player_id)

    # Detect recoveries for each player
    per_player: dict[str, dict] = {}
    all_events: list[dict] = []

    for player_id in sorted(player_ids):
        events = detect_recoveries_for_player(frames, player_id)

        # Aggregate statistics
        if events:
            quality_counts = {q.value: 0 for q in RecoveryQuality}
            total_momentum = 0.0
            wavedash_count = 0

            for event in events:
                quality_counts[event.quality.value] += 1
                total_momentum += event.momentum_retained
                if event.was_wavedash:
                    wavedash_count += 1

                # Add to flat event list
                all_events.append(
                    {
                        "timestamp": event.timestamp,
                        "player_id": event.player_id,
                        "quality": event.quality.value,
                        "time_airborne": event.time_airborne,
                        "time_to_control": event.time_to_control,
                        "peak_height": event.peak_height,
                        "speed_at_landing": event.speed_at_landing,
                        "speed_after_recovery": event.speed_after_recovery,
                        "momentum_retained": event.momentum_retained,
                        "was_wavedash": event.was_wavedash,
                        "landing_position": {
                            "x": event.landing_position.x,
                            "y": event.landing_position.y,
                            "z": event.landing_position.z,
                        },
                    }
                )

            avg_momentum = total_momentum / len(events) if events else 0.0
            # Cap average_momentum_retained at 1.0 for summary statistics
            # Individual events can exceed 1.0 (boost/wavedash during recovery)
            # but the "average retained" metric should reflect momentum kept, not gained
            avg_momentum_capped = min(avg_momentum, 1.0)

            per_player[player_id] = {
                "total_recoveries": len(events),
                "quality_distribution": quality_counts,
                "excellent_count": quality_counts.get("excellent", 0),
                "poor_count": quality_counts.get("poor", 0)
                + quality_counts.get("failed", 0),
                "average_momentum_retained": round(avg_momentum_capped, 3),
                "wavedash_count": wavedash_count,
            }
        else:
            per_player[player_id] = {
                "total_recoveries": 0,
                "quality_distribution": {q.value: 0 for q in RecoveryQuality},
                "excellent_count": 0,
                "poor_count": 0,
                "average_momentum_retained": 0.0,
                "wavedash_count": 0,
            }

    # Sort events by timestamp
    all_events.sort(key=lambda e: e["timestamp"])

    # Calculate team aggregates
    total_recoveries = sum(p.get("total_recoveries", 0) for p in per_player.values())
    total_excellent = sum(p.get("excellent_count", 0) for p in per_player.values())
    total_wavedashes = sum(p.get("wavedash_count", 0) for p in per_player.values())

    return {
        "per_player": per_player,
        "events": all_events,
        "total_recoveries": total_recoveries,
        "total_excellent_recoveries": total_excellent,
        "total_wavedashes": total_wavedashes,
    }
