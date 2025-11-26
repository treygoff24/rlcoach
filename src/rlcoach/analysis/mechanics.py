"""Mechanics detection module - infer jump/flip/dodge from physics state."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from ..field_constants import Vec3
from ..parser.types import Frame, PlayerFrame, Rotation

logger = logging.getLogger(__name__)


class MechanicType(Enum):
    """Types of mechanics that can be detected."""
    JUMP = "jump"
    DOUBLE_JUMP = "double_jump"
    FLIP = "flip"
    DODGE = "dodge"
    WAVEDASH = "wavedash"
    FLIP_CANCEL = "flip_cancel"
    AERIAL = "aerial"
    HALF_FLIP = "half_flip"
    SPEEDFLIP = "speedflip"


@dataclass(frozen=True)
class MechanicEvent:
    """A detected mechanic event."""
    timestamp: float
    player_id: str
    mechanic_type: MechanicType
    position: Vec3
    velocity: Vec3
    # Additional context
    direction: Optional[str] = None  # forward, backward, left, right, diagonal
    height: float = 0.0  # height above ground when mechanic started
    duration: Optional[float] = None  # how long the mechanic lasted (for flips)


@dataclass
class PlayerMechanicsState:
    """Track mechanics state for a single player across frames."""
    # Jump tracking
    is_airborne: bool = False
    airborne_start_time: Optional[float] = None
    has_jumped: bool = False  # First jump used
    has_double_jumped: bool = False  # Second jump used
    has_flipped: bool = False  # Flip used (consumes second jump)
    last_ground_time: float = 0.0

    # Physics tracking for derivative detection
    prev_z_velocity: float = 0.0
    prev_z_position: float = 17.0  # Car ground level
    prev_angular_x: float = 0.0  # pitch rate
    prev_angular_y: float = 0.0  # yaw rate
    prev_rotation_pitch: float = 0.0
    prev_rotation_yaw: float = 0.0
    prev_rotation_roll: float = 0.0

    # Flip tracking
    flip_start_time: Optional[float] = None
    flip_initial_rotation: Optional[tuple[float, float, float]] = None
    flip_direction: Optional[str] = None  # Direction of most recent flip
    flip_cancel_detected: bool = False  # Was flip cancelled?

    # Landing detection
    last_velocity_z: float = 0.0

    # Half-flip/speedflip tracking
    initial_yaw: float = 0.0  # Yaw at flip start for 180° detection
    prev_yaw: float = 0.0  # Previous yaw for rotation tracking


# Physics constants for detection thresholds
GROUND_HEIGHT_THRESHOLD = 25.0  # Car is on ground if z < this
JUMP_Z_VELOCITY_THRESHOLD = 292.0  # Minimum z velocity spike for jump (UU/s)
DOUBLE_JUMP_Z_VELOCITY_THRESHOLD = 292.0  # Same threshold for double jump
FLIP_ANGULAR_THRESHOLD = 5.0  # Radians/second rotation rate for flip detection
JUMP_COOLDOWN = 0.1  # Minimum time between jump detections (seconds)
AERIAL_HEIGHT_THRESHOLD = 200.0  # Height threshold for aerial classification
WAVEDASH_LANDING_WINDOW = 0.2  # Time window after flip to detect wavedash

# Half-flip and speedflip detection constants
FLIP_CANCEL_PITCH_REVERSAL_THRESHOLD = 3.0  # rad/s pitch rate reversal for flip cancel
FLIP_CANCEL_WINDOW = 0.25  # Time window after flip to detect cancel
HALF_FLIP_YAW_CHANGE_THRESHOLD = 2.5  # ~143 degrees in radians for half-flip
HALF_FLIP_DETECTION_WINDOW = 0.6  # Time window to complete half-flip
SPEEDFLIP_CANCEL_WINDOW = 0.20  # Speedflip cancel must be nearly immediate


def _get_rotation_values(rotation: Rotation | Vec3) -> tuple[float, float, float]:
    """Extract pitch, yaw, roll from rotation (handles both formats).

    Args:
        rotation: Rotation object (Rotation dataclass or legacy Vec3)

    Returns:
        Tuple of (pitch, yaw, roll) in radians

    Note:
        Returns (0.0, 0.0, 0.0) for unrecognized types with a warning.
    """
    if isinstance(rotation, Rotation):
        return (rotation.pitch, rotation.yaw, rotation.roll)
    elif isinstance(rotation, Vec3):
        # Legacy format: x=pitch, y=yaw, z=roll
        return (rotation.x, rotation.y, rotation.z)

    # Log warning for unexpected types
    logger.warning(
        "Unrecognized rotation type %s, defaulting to (0, 0, 0)",
        type(rotation).__name__
    )
    return (0.0, 0.0, 0.0)


def _get_flip_direction(
    velocity: Vec3,
    rotation_change: tuple[float, float, float],
    yaw: float
) -> str:
    """Determine flip direction based on velocity and rotation change."""
    pitch_rate, yaw_rate, roll_rate = rotation_change

    # Dominant rotation axis determines flip type
    if abs(pitch_rate) > abs(roll_rate) and abs(pitch_rate) > abs(yaw_rate):
        return "forward" if pitch_rate > 0 else "backward"
    elif abs(roll_rate) > abs(pitch_rate) and abs(roll_rate) > abs(yaw_rate):
        return "left" if roll_rate > 0 else "right"
    else:
        # Mixed or diagonal flip
        return "diagonal"


def _normalize_angle(angle: float) -> float:
    """Normalize angle to [-pi, pi] range."""
    while angle > math.pi:
        angle -= 2 * math.pi
    while angle < -math.pi:
        angle += 2 * math.pi
    return angle


def detect_mechanics_for_player(
    frames: list[Frame],
    player_id: str,
) -> list[MechanicEvent]:
    """Detect mechanics for a single player from frame data.

    Args:
        frames: Normalized frame data
        player_id: Player ID to analyze

    Returns:
        List of detected mechanic events
    """
    events: list[MechanicEvent] = []
    state = PlayerMechanicsState()

    prev_frame: Optional[Frame] = None
    prev_player: Optional[PlayerFrame] = None

    for frame in frames:
        # Find player in this frame
        player: Optional[PlayerFrame] = None
        for p in frame.players:
            if p.player_id == player_id:
                player = p
                break

        if player is None:
            prev_frame = frame
            continue

        timestamp = frame.timestamp
        pos = player.position
        vel = player.velocity
        rot = player.rotation

        pitch, yaw, roll = _get_rotation_values(rot)

        # Calculate derivatives if we have previous frame
        if prev_player is not None and prev_frame is not None:
            dt = max(timestamp - prev_frame.timestamp, 0.001)  # Prevent div by zero

            # Velocity change (acceleration)
            z_accel = (vel.z - state.prev_z_velocity) / dt

            # Rotation rate (angular velocity approximation)
            pitch_rate = (pitch - state.prev_rotation_pitch) / dt
            yaw_rate = (yaw - state.prev_rotation_yaw) / dt
            roll_rate = (roll - state.prev_rotation_roll) / dt

            # Detect ground state
            was_airborne = state.is_airborne
            is_on_ground = pos.z < GROUND_HEIGHT_THRESHOLD or player.is_on_ground

            if is_on_ground and was_airborne:
                # Just landed
                # Check for wavedash (landing within window after starting a flip)
                if (state.flip_start_time is not None and
                    timestamp - state.flip_start_time < WAVEDASH_LANDING_WINDOW):
                    events.append(MechanicEvent(
                        timestamp=timestamp,
                        player_id=player_id,
                        mechanic_type=MechanicType.WAVEDASH,
                        position=pos,
                        velocity=vel,
                        height=0.0,
                        duration=timestamp - state.flip_start_time,
                    ))

                # Reset airborne state
                state.is_airborne = False
                state.has_jumped = False
                state.has_double_jumped = False
                state.has_flipped = False
                state.airborne_start_time = None
                state.flip_start_time = None
                state.last_ground_time = timestamp

            elif not is_on_ground and not was_airborne:
                # Just became airborne
                state.is_airborne = True
                state.airborne_start_time = timestamp

            elif not is_on_ground:
                # Already airborne - detect mechanics

                # Jump detection: sudden z velocity increase
                z_vel_increase = vel.z - state.prev_z_velocity
                time_since_ground = timestamp - state.last_ground_time

                if (z_vel_increase > JUMP_Z_VELOCITY_THRESHOLD and
                    time_since_ground > JUMP_COOLDOWN):

                    # Check rotation rate to distinguish jump vs flip
                    total_rot_rate = math.sqrt(
                        pitch_rate * pitch_rate +
                        roll_rate * roll_rate
                    )

                    if total_rot_rate > FLIP_ANGULAR_THRESHOLD:
                        # This is a flip/dodge
                        if not state.has_flipped:
                            state.has_flipped = True
                            state.flip_start_time = timestamp
                            state.flip_cancel_detected = False
                            flip_dir = _get_flip_direction(
                                vel,
                                (pitch_rate, yaw_rate, roll_rate),
                                yaw
                            )
                            state.flip_direction = flip_dir
                            state.initial_yaw = yaw

                            mechanic_type = MechanicType.FLIP

                            events.append(MechanicEvent(
                                timestamp=timestamp,
                                player_id=player_id,
                                mechanic_type=mechanic_type,
                                position=pos,
                                velocity=vel,
                                direction=flip_dir,
                                height=pos.z,
                            ))
                    else:
                        # Pure vertical jump (jump or double jump)
                        if not state.has_jumped:
                            state.has_jumped = True
                            events.append(MechanicEvent(
                                timestamp=timestamp,
                                player_id=player_id,
                                mechanic_type=MechanicType.JUMP,
                                position=pos,
                                velocity=vel,
                                height=pos.z,
                            ))
                        elif not state.has_double_jumped and not state.has_flipped:
                            state.has_double_jumped = True
                            events.append(MechanicEvent(
                                timestamp=timestamp,
                                player_id=player_id,
                                mechanic_type=MechanicType.DOUBLE_JUMP,
                                position=pos,
                                velocity=vel,
                                height=pos.z,
                            ))

                # Aerial detection (high altitude)
                if (pos.z > AERIAL_HEIGHT_THRESHOLD and
                    state.has_jumped and
                    state.airborne_start_time is not None):
                    airborne_duration = timestamp - state.airborne_start_time
                    # Only mark as aerial after sustained flight
                    if airborne_duration > 0.5 and not any(
                        e.mechanic_type == MechanicType.AERIAL
                        and e.player_id == player_id
                        and timestamp - e.timestamp < 1.0
                        for e in events
                    ):
                        events.append(MechanicEvent(
                            timestamp=timestamp,
                            player_id=player_id,
                            mechanic_type=MechanicType.AERIAL,
                            position=pos,
                            velocity=vel,
                            height=pos.z,
                        ))

                # Flip cancel detection (pitch rate reversal after flip)
                if (state.has_flipped and
                    state.flip_start_time is not None and
                    not state.flip_cancel_detected):
                    flip_elapsed = timestamp - state.flip_start_time
                    if flip_elapsed < FLIP_CANCEL_WINDOW:
                        # Check for pitch rate reversal (flip cancel)
                        # In a flip, pitch rate should maintain direction
                        # Cancel shows as sudden reversal
                        prev_pitch_rate = state.prev_angular_x
                        pitch_rate_change = abs(pitch_rate - prev_pitch_rate)
                        if pitch_rate_change > FLIP_CANCEL_PITCH_REVERSAL_THRESHOLD:
                            state.flip_cancel_detected = True
                            events.append(MechanicEvent(
                                timestamp=timestamp,
                                player_id=player_id,
                                mechanic_type=MechanicType.FLIP_CANCEL,
                                position=pos,
                                velocity=vel,
                                direction=state.flip_direction,
                                height=pos.z,
                            ))

                # Half-flip and speedflip detection
                if (state.has_flipped and
                    state.flip_start_time is not None and
                    state.flip_cancel_detected):
                    flip_elapsed = timestamp - state.flip_start_time

                    # Check for half-flip (backward flip + cancel + 180° turn)
                    if (state.flip_direction == "backward" and
                        flip_elapsed < HALF_FLIP_DETECTION_WINDOW):
                        # Calculate yaw change from flip start
                        yaw_change = abs(_normalize_angle(yaw - state.initial_yaw))
                        if yaw_change > HALF_FLIP_YAW_CHANGE_THRESHOLD:
                            # This is a half-flip
                            if not any(
                                e.mechanic_type == MechanicType.HALF_FLIP
                                and e.player_id == player_id
                                and abs(timestamp - e.timestamp) < 0.3
                                for e in events
                            ):
                                events.append(MechanicEvent(
                                    timestamp=timestamp,
                                    player_id=player_id,
                                    mechanic_type=MechanicType.HALF_FLIP,
                                    position=pos,
                                    velocity=vel,
                                    direction="backward",
                                    height=pos.z,
                                    duration=flip_elapsed,
                                ))

                    # Check for speedflip (diagonal flip + cancel)
                    elif (state.flip_direction == "diagonal" and
                          flip_elapsed < SPEEDFLIP_CANCEL_WINDOW * 2):
                        # Speedflip = diagonal flip with immediate cancel
                        # Already detected cancel, now classify as speedflip
                        if not any(
                            e.mechanic_type == MechanicType.SPEEDFLIP
                            and e.player_id == player_id
                            and abs(timestamp - e.timestamp) < 0.3
                            for e in events
                        ):
                            events.append(MechanicEvent(
                                timestamp=timestamp,
                                player_id=player_id,
                                mechanic_type=MechanicType.SPEEDFLIP,
                                position=pos,
                                velocity=vel,
                                direction="diagonal",
                                height=pos.z,
                                duration=flip_elapsed,
                            ))

        # Update state for next frame
        state.prev_z_velocity = vel.z
        state.prev_z_position = pos.z
        state.prev_rotation_pitch = pitch
        state.prev_rotation_yaw = yaw
        state.prev_rotation_roll = roll
        state.last_velocity_z = vel.z
        state.prev_yaw = yaw

        # Store pitch rate for flip cancel detection
        if prev_player is not None and prev_frame is not None:
            state.prev_angular_x = pitch_rate

        prev_frame = frame
        prev_player = player

    return events


def analyze_mechanics(frames: list[Frame]) -> dict:
    """Analyze mechanics for all players in replay.

    Args:
        frames: Normalized frame data

    Returns:
        Dict with mechanics analysis results
    """
    # Get all unique player IDs
    player_ids: set[str] = set()
    for frame in frames:
        for player in frame.players:
            player_ids.add(player.player_id)

    # Detect mechanics for each player
    per_player: dict[str, dict] = {}
    all_events: list[dict] = []

    for player_id in sorted(player_ids):
        events = detect_mechanics_for_player(frames, player_id)

        # Aggregate counts by mechanic type
        counts: dict[str, int] = {}
        for event in events:
            mtype = event.mechanic_type.value
            counts[mtype] = counts.get(mtype, 0) + 1

            # Add to flat event list
            all_events.append({
                "timestamp": event.timestamp,
                "player_id": event.player_id,
                "mechanic_type": mtype,
                "position": {"x": event.position.x, "y": event.position.y, "z": event.position.z},
                "velocity": {"x": event.velocity.x, "y": event.velocity.y, "z": event.velocity.z},
                "direction": event.direction,
                "height": event.height,
                "duration": event.duration,
            })

        per_player[player_id] = {
            "jump_count": counts.get("jump", 0),
            "double_jump_count": counts.get("double_jump", 0),
            "flip_count": counts.get("flip", 0),
            "wavedash_count": counts.get("wavedash", 0),
            "aerial_count": counts.get("aerial", 0),
            "halfflip_count": counts.get("half_flip", 0),
            "speedflip_count": counts.get("speedflip", 0),
            "flip_cancel_count": counts.get("flip_cancel", 0),
            "total_mechanics": sum(counts.values()),
        }

    # Sort events by timestamp
    all_events.sort(key=lambda e: e["timestamp"])

    return {
        "per_player": per_player,
        "events": all_events,
        "total_jumps": sum(p.get("jump_count", 0) for p in per_player.values()),
        "total_flips": sum(p.get("flip_count", 0) for p in per_player.values()),
        "total_aerials": sum(p.get("aerial_count", 0) for p in per_player.values()),
        "total_wavedashes": sum(p.get("wavedash_count", 0) for p in per_player.values()),
        "total_halfflips": sum(p.get("halfflip_count", 0) for p in per_player.values()),
        "total_speedflips": sum(p.get("speedflip_count", 0) for p in per_player.values()),
    }
