"""Ball prediction awareness analysis.

Provides analysis of:
- Ball trajectory prediction (simplified physics)
- Player read quality (how well players anticipate ball movement)
- Proactive vs reactive positioning
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from ..field_constants import FIELD, Vec3
from ..parser.types import Frame, PlayerFrame


class ReadQuality(Enum):
    """Quality of a player's ball read."""

    EXCELLENT = "excellent"  # Player was already moving toward predicted position
    GOOD = "good"  # Player adjusted quickly to ball trajectory
    AVERAGE = "average"  # Normal reaction time
    POOR = "poor"  # Slow to react or wrong direction
    WHIFF = "whiff"  # Complete miss/misread


@dataclass(frozen=True)
class BallPrediction:
    """Predicted ball state after time delta."""

    position: Vec3
    velocity: Vec3
    time_delta: float
    bounced: bool  # Whether prediction includes a bounce


@dataclass(frozen=True)
class ReadEvent:
    """A player's read on the ball at a specific moment."""

    timestamp: float
    player_id: str
    predicted_intercept: Vec3  # Where player would meet ball at current trajectory
    actual_ball_position: Vec3  # Where ball actually went
    prediction_error: float  # Distance between predicted and actual
    read_quality: ReadQuality
    was_proactive: bool  # Player moving toward ball before obvious


# Physics constants (simplified)
GRAVITY = -650.0  # UU/s^2
BALL_RADIUS = 93.15
AIR_RESISTANCE = 0.03  # Simplified drag coefficient
BOUNCE_COEFFICIENT = 0.6  # Energy retained on bounce
WALL_BOUNCE_COEFFICIENT = 0.7

# Analysis thresholds
EXCELLENT_READ_ERROR = 150.0  # Within this distance = excellent
GOOD_READ_ERROR = 300.0
AVERAGE_READ_ERROR = 600.0
POOR_READ_ERROR = 1200.0

PROACTIVE_THRESHOLD = 0.3  # Seconds before ball arrives = proactive


def _predict_ball_position(
    position: Vec3,
    velocity: Vec3,
    time_delta: float,
    include_bounces: bool = True,
) -> BallPrediction:
    """Predict ball position after time_delta seconds.

    Uses simplified physics (gravity, basic bounces, no spin).

    Args:
        position: Current ball position
        velocity: Current ball velocity
        time_delta: Time to predict ahead (seconds)
        include_bounces: Whether to simulate bounces

    Returns:
        BallPrediction with predicted state
    """
    # Start with current state
    x = position.x
    y = position.y
    z = position.z
    vx = velocity.x
    vy = velocity.y
    vz = velocity.z

    # Adaptive step size: use finer steps for short predictions, coarser for long
    # - Short predictions (< 0.5s): 60fps (dt=0.016)
    # - Medium predictions (0.5-2s): 30fps (dt=0.033)
    # - Long predictions (> 2s): 15fps (dt=0.066)
    if time_delta < 0.5:
        dt = 0.016  # ~60fps for high precision
    elif time_delta < 2.0:
        dt = 0.033  # ~30fps for medium predictions
    else:
        dt = 0.066  # ~15fps for long predictions (limits max iterations)

    # Cap maximum iterations to prevent runaway loops
    max_iterations = int(time_delta / dt) + 100

    t = 0.0
    bounced = False
    iterations = 0

    while t < time_delta and iterations < max_iterations:
        iterations += 1
        remaining = time_delta - t
        step = min(dt, remaining)

        # Apply gravity
        vz += GRAVITY * step

        # Apply air resistance (simplified)
        speed = math.sqrt(vx * vx + vy * vy + vz * vz)
        if speed > 10.0:
            drag = 1.0 - AIR_RESISTANCE * step
            vx *= drag
            vy *= drag
            vz *= drag

        # Update position
        x += vx * step
        y += vy * step
        z += vz * step

        if include_bounces:
            # Ground bounce
            if z < BALL_RADIUS:
                z = BALL_RADIUS
                vz = -vz * BOUNCE_COEFFICIENT
                bounced = True

            # Ceiling bounce
            if z > FIELD.CEILING_Z - BALL_RADIUS:
                z = FIELD.CEILING_Z - BALL_RADIUS
                vz = -vz * BOUNCE_COEFFICIENT
                bounced = True

            # Side wall bounces
            if x > FIELD.SIDE_WALL_X - BALL_RADIUS:
                x = FIELD.SIDE_WALL_X - BALL_RADIUS
                vx = -vx * WALL_BOUNCE_COEFFICIENT
                bounced = True
            elif x < -FIELD.SIDE_WALL_X + BALL_RADIUS:
                x = -FIELD.SIDE_WALL_X + BALL_RADIUS
                vx = -vx * WALL_BOUNCE_COEFFICIENT
                bounced = True

            # Back wall bounces (outside goal)
            goal_width = FIELD.GOAL_WIDTH
            if y > FIELD.BACK_WALL_Y - BALL_RADIUS:
                if abs(x) > goal_width or z > FIELD.GOAL_HEIGHT:
                    y = FIELD.BACK_WALL_Y - BALL_RADIUS
                    vy = -vy * WALL_BOUNCE_COEFFICIENT
                    bounced = True
            elif y < -FIELD.BACK_WALL_Y + BALL_RADIUS:
                if abs(x) > goal_width or z > FIELD.GOAL_HEIGHT:
                    y = -FIELD.BACK_WALL_Y + BALL_RADIUS
                    vy = -vy * WALL_BOUNCE_COEFFICIENT
                    bounced = True

        t += step

    return BallPrediction(
        position=Vec3(x, y, z),
        velocity=Vec3(vx, vy, vz),
        time_delta=time_delta,
        bounced=bounced,
    )


def _calculate_intercept_point(
    player_pos: Vec3,
    player_vel: Vec3,
    ball_pos: Vec3,
    ball_vel: Vec3,
    max_time: float = 3.0,
) -> tuple[Vec3, float]:
    """Calculate where player could intercept the ball.

    Args:
        player_pos: Player position
        player_vel: Player velocity
        ball_pos: Ball position
        ball_vel: Ball velocity
        max_time: Maximum time to look ahead

    Returns:
        Tuple of (intercept position, time to intercept)
    """
    # Estimate player max speed (with boost)
    player_speed = math.sqrt(player_vel.x**2 + player_vel.y**2 + player_vel.z**2)
    max_player_speed = max(player_speed + 500.0, 1400.0)  # Account for boost

    best_intercept = ball_pos
    best_time = max_time

    # Sample future ball positions
    for t in [0.2, 0.4, 0.6, 0.8, 1.0, 1.5, 2.0, 2.5, 3.0]:
        if t > max_time:
            break

        pred = _predict_ball_position(ball_pos, ball_vel, t)

        # Distance player needs to travel
        dx = pred.position.x - player_pos.x
        dy = pred.position.y - player_pos.y
        dz = pred.position.z - player_pos.z
        distance = math.sqrt(dx * dx + dy * dy + dz * dz)

        # Time for player to reach
        player_time = distance / max_player_speed

        # Can player reach in time?
        if player_time <= t and t < best_time:
            best_time = t
            best_intercept = pred.position

    return best_intercept, best_time


def _assess_read_quality(
    player: PlayerFrame,
    ball_pos: Vec3,
    predicted_pos: Vec3,
    actual_future_pos: Vec3,
) -> tuple[ReadQuality, float, bool]:
    """Assess how well a player read the ball.

    Args:
        player: Player frame
        ball_pos: Current ball position
        predicted_pos: Where player was moving toward
        actual_future_pos: Where ball actually went

    Returns:
        Tuple of (quality, prediction error, was proactive)
    """
    # Calculate prediction error
    dx = predicted_pos.x - actual_future_pos.x
    dy = predicted_pos.y - actual_future_pos.y
    dz = predicted_pos.z - actual_future_pos.z
    error = math.sqrt(dx * dx + dy * dy + dz * dz)

    # Check if velocity is toward predicted position
    player_to_pred = Vec3(
        predicted_pos.x - player.position.x,
        predicted_pos.y - player.position.y,
        predicted_pos.z - player.position.z,
    )

    # Dot product of velocity and direction to prediction
    ptp_mag = math.sqrt(player_to_pred.x**2 + player_to_pred.y**2 + player_to_pred.z**2)
    vel_mag = math.sqrt(
        player.velocity.x**2 + player.velocity.y**2 + player.velocity.z**2
    )

    proactive = False
    if vel_mag > 100.0 and ptp_mag > 100.0:
        vel_dot = (
            player.velocity.x * player_to_pred.x
            + player.velocity.y * player_to_pred.y
            + player.velocity.z * player_to_pred.z
        ) / (vel_mag * ptp_mag)

        # Moving toward prediction = proactive
        if vel_dot > 0.7:
            proactive = True

    # Quality based on error
    if error < EXCELLENT_READ_ERROR:
        quality = ReadQuality.EXCELLENT
    elif error < GOOD_READ_ERROR:
        quality = ReadQuality.GOOD
    elif error < AVERAGE_READ_ERROR:
        quality = ReadQuality.AVERAGE
    elif error < POOR_READ_ERROR:
        quality = ReadQuality.POOR
    else:
        quality = ReadQuality.WHIFF

    return quality, error, proactive


def analyze_player_reads(
    frames: list[Frame],
    player_id: str,
    sample_interval: float = 0.5,
) -> list[ReadEvent]:
    """Analyze ball reads for a single player.

    Args:
        frames: Normalized frame data
        player_id: Player to analyze
        sample_interval: How often to sample reads (seconds)

    Returns:
        List of ReadEvent objects
    """
    events: list[ReadEvent] = []

    if len(frames) < 10:
        return events

    last_sample_time = -sample_interval
    lookahead_time = 0.5  # Predict 0.5 seconds ahead

    for i, frame in enumerate(frames):
        # Sample at intervals
        if frame.timestamp - last_sample_time < sample_interval:
            continue

        # Find player in frame
        player: PlayerFrame | None = None
        for p in frame.players:
            if p.player_id == player_id:
                player = p
                break

        if player is None:
            continue

        # Find future frame for validation
        future_frame: Frame | None = None
        for j in range(i + 1, len(frames)):
            if frames[j].timestamp >= frame.timestamp + lookahead_time:
                future_frame = frames[j]
                break

        if future_frame is None:
            continue

        # Predict where ball will be
        _predict_ball_position(
            frame.ball.position,
            frame.ball.velocity,
            lookahead_time,
        )

        # Calculate where player was trying to go
        intercept_pos, intercept_time = _calculate_intercept_point(
            player.position,
            player.velocity,
            frame.ball.position,
            frame.ball.velocity,
        )

        # Assess read quality
        quality, error, proactive = _assess_read_quality(
            player,
            frame.ball.position,
            intercept_pos,
            future_frame.ball.position,
        )

        events.append(
            ReadEvent(
                timestamp=frame.timestamp,
                player_id=player_id,
                predicted_intercept=intercept_pos,
                actual_ball_position=future_frame.ball.position,
                prediction_error=round(error, 2),
                read_quality=quality,
                was_proactive=proactive,
            )
        )

        last_sample_time = frame.timestamp

    return events


def analyze_ball_prediction(frames: list[Frame]) -> dict:
    """Comprehensive ball prediction analysis for the replay.

    Args:
        frames: Normalized frame data

    Returns:
        Dict with ball prediction analysis results
    """
    # Get all unique player IDs
    player_ids: set[str] = set()
    for frame in frames:
        for player in frame.players:
            player_ids.add(player.player_id)

    per_player: dict[str, dict] = {}
    all_reads: list[dict] = []

    for player_id in sorted(player_ids):
        reads = analyze_player_reads(frames, player_id)

        if reads:
            quality_counts = {q.value: 0 for q in ReadQuality}
            total_error = 0.0
            proactive_count = 0

            for read in reads:
                quality_counts[read.read_quality.value] += 1
                total_error += read.prediction_error
                if read.was_proactive:
                    proactive_count += 1

                all_reads.append(
                    {
                        "timestamp": read.timestamp,
                        "player_id": read.player_id,
                        "read_quality": read.read_quality.value,
                        "prediction_error": read.prediction_error,
                        "was_proactive": read.was_proactive,
                    }
                )

            avg_error = total_error / len(reads) if reads else 0.0
            proactive_rate = proactive_count / len(reads) if reads else 0.0

            per_player[player_id] = {
                "total_reads": len(reads),
                "quality_distribution": quality_counts,
                "excellent_reads": quality_counts.get("excellent", 0),
                "poor_reads": quality_counts.get("poor", 0)
                + quality_counts.get("whiff", 0),
                "average_prediction_error": round(avg_error, 2),
                "proactive_rate": round(proactive_rate, 3),
            }
        else:
            per_player[player_id] = {
                "total_reads": 0,
                "quality_distribution": {q.value: 0 for q in ReadQuality},
                "excellent_reads": 0,
                "poor_reads": 0,
                "average_prediction_error": 0.0,
                "proactive_rate": 0.0,
            }

    # Sort reads by timestamp
    all_reads.sort(key=lambda r: r["timestamp"])

    # Aggregate stats
    total_excellent = sum(p.get("excellent_reads", 0) for p in per_player.values())
    total_poor = sum(p.get("poor_reads", 0) for p in per_player.values())
    avg_proactive = (
        sum(p.get("proactive_rate", 0.0) for p in per_player.values()) / len(per_player)
        if per_player
        else 0.0
    )

    return {
        "per_player": per_player,
        "reads": all_reads[:200],  # Limit output size
        "total_excellent_reads": total_excellent,
        "total_poor_reads": total_poor,
        "average_proactive_rate": round(avg_proactive, 3),
    }
