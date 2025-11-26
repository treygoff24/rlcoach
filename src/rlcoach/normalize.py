"""Normalization layer for converting parser outputs to standardized timeline format.

This module transforms raw parser data into normalized structures with:
- Measured frame rates
- Standard RLBot coordinate system
- Unified player identity mapping
- Consistent timeline format
"""

from __future__ import annotations

import math
import statistics
from dataclasses import replace
from typing import Any

from .field_constants import FIELD, Vec3
from .parser.types import (
    Header,
    NetworkFrames,
    Frame,
    PlayerFrame,
    BallFrame,
    BoostPadEventFrame,
    Rotation,
    Quaternion,
)
from .utils.identity import (
    build_alias_lookup,
    build_player_identities,
    sanitize_display_name,
)

SUPERSONIC_ENTRY_UU_S = 2200.0
SUPERSONIC_EXIT_UU_S = 2100.0
SUPERSONIC_DERIVATIVE_ENTRY_UU_S = 2800.0
MIN_FRAME_DT = 1e-3

# Default frame rate when unable to measure from replay data
DEFAULT_FRAME_RATE = 30.0

# Seconds to keep after the last recorded goal to account for replays + kickoff
GOAL_POST_BUFFER_S = 7.0


def measure_frame_rate(frames: list[Any]) -> float:
    """Measure actual frame rate from frame timestamps.

    Args:
        frames: List of frame data with timestamp information

    Returns:
        Measured frame rate in Hz (defaults to DEFAULT_FRAME_RATE if unmeasurable)
    """
    if not frames or len(frames) < 2:
        return DEFAULT_FRAME_RATE

    # Extract timestamps - handle different frame formats
    timestamps = []
    for frame in frames:
        try:
            if hasattr(frame, 'timestamp'):
                timestamps.append(float(frame.timestamp))
            elif hasattr(frame, 'time'):
                timestamps.append(float(frame.time))
            elif isinstance(frame, dict) and 'timestamp' in frame:
                timestamps.append(float(frame['timestamp']))
            elif isinstance(frame, dict) and 'time' in frame:
                timestamps.append(float(frame['time']))
        except (ValueError, TypeError):
            continue  # Skip frames with invalid timestamps

    if len(timestamps) < 2:
        return DEFAULT_FRAME_RATE

    # Calculate time deltas between consecutive frames
    deltas = []
    for i in range(1, len(timestamps)):
        delta = timestamps[i] - timestamps[i-1]
        if delta > 0:  # Only positive deltas
            deltas.append(delta)

    if not deltas:
        return DEFAULT_FRAME_RATE

    # Use median delta to avoid outliers from frame drops
    median_delta = statistics.median(deltas)
    if median_delta <= 0:
        return DEFAULT_FRAME_RATE

    # Convert to Hz and clamp to reasonable range
    fps = 1.0 / median_delta
    return max(1.0, min(240.0, fps))


def to_field_coords(vec: Any) -> Vec3:
    """Transform vector to standard RLBot coordinate system.
    
    Args:
        vec: Input vector (Vec3, tuple, list, or dict)
        
    Returns:
        Vec3 in RLBot coordinate system (x=±4096, y=±5120, z≈2044)
    """
    # Handle different input formats
    if isinstance(vec, Vec3):
        return vec
    elif hasattr(vec, 'x') and hasattr(vec, 'y') and hasattr(vec, 'z'):
        x, y, z = vec.x, vec.y, vec.z
    elif isinstance(vec, (tuple, list)) and len(vec) >= 3:
        x, y, z = vec[0], vec[1], vec[2]
    elif isinstance(vec, dict):
        x = vec.get('x', 0.0)
        y = vec.get('y', 0.0)
        z = vec.get('z', 0.0)
    else:
        return Vec3(0.0, 0.0, 0.0)
    
    # Convert to float and ensure reasonable bounds
    try:
        x_norm = float(x)
        y_norm = float(y)  
        z_norm = float(z)
        
        # Clamp to field boundaries with some tolerance
        x_norm = max(-FIELD.SIDE_WALL_X * 1.1, min(FIELD.SIDE_WALL_X * 1.1, x_norm))
        y_norm = max(-FIELD.BACK_WALL_Y * 1.1, min(FIELD.BACK_WALL_Y * 1.1, y_norm))
        z_norm = max(-100.0, min(FIELD.CEILING_Z * 2.0, z_norm))
        
        return Vec3(x_norm, y_norm, z_norm)
    except (ValueError, TypeError):
        return Vec3(0.0, 0.0, 0.0)


def _parse_rotation(rot_data: Any) -> Rotation | Vec3:
    """Parse rotation data from parser output.

    Handles both new format (pitch/yaw/roll + optional quaternion) and legacy
    format (x/y/z where x=pitch, y=yaw, z=roll).

    Args:
        rot_data: Rotation data dict or object

    Returns:
        Rotation dataclass with euler angles and optional quaternion, or Vec3 for legacy
    """
    if rot_data is None:
        return Rotation(0.0, 0.0, 0.0)

    # Already a Rotation object
    if isinstance(rot_data, Rotation):
        return rot_data

    # Handle dict format
    if isinstance(rot_data, dict):
        # New format: has pitch/yaw/roll keys
        if 'pitch' in rot_data or 'yaw' in rot_data or 'roll' in rot_data:
            pitch = float(rot_data.get('pitch', 0.0))
            yaw = float(rot_data.get('yaw', 0.0))
            roll = float(rot_data.get('roll', 0.0))

            # Parse quaternion if present
            quat = None
            quat_data = rot_data.get('quaternion')
            if quat_data is not None and isinstance(quat_data, dict):
                quat = Quaternion(
                    x=float(quat_data.get('x', 0.0)),
                    y=float(quat_data.get('y', 0.0)),
                    z=float(quat_data.get('z', 0.0)),
                    w=float(quat_data.get('w', 1.0)),
                )

            return Rotation(pitch=pitch, yaw=yaw, roll=roll, quaternion=quat)

        # Legacy format: has x/y/z keys (x=pitch, y=yaw, z=roll)
        elif 'x' in rot_data or 'y' in rot_data or 'z' in rot_data:
            return Vec3(
                x=float(rot_data.get('x', 0.0)),
                y=float(rot_data.get('y', 0.0)),
                z=float(rot_data.get('z', 0.0)),
            )

    # For non-dict objects, check for x/y/z FIRST (legacy format), before pitch/yaw/roll
    # This is important because Mock objects have implicit attributes
    if hasattr(rot_data, 'x') and hasattr(rot_data, 'y') and hasattr(rot_data, 'z'):
        # Try to get x/y/z as numbers - this distinguishes real attributes from Mock implicit ones
        try:
            x_val = getattr(rot_data, 'x')
            y_val = getattr(rot_data, 'y')
            z_val = getattr(rot_data, 'z')
            # Verify they are actual numeric values
            if isinstance(x_val, (int, float)) and isinstance(y_val, (int, float)) and isinstance(z_val, (int, float)):
                return Vec3(x=float(x_val), y=float(y_val), z=float(z_val))
        except (TypeError, ValueError):
            pass

    # Handle object with pitch/yaw/roll attributes (new format)
    pitch_val = getattr(rot_data, 'pitch', None)
    yaw_val = getattr(rot_data, 'yaw', None)
    roll_val = getattr(rot_data, 'roll', None)

    # Check if any of pitch/yaw/roll are actual numbers (not Mock objects)
    has_real_pitch = isinstance(pitch_val, (int, float))
    has_real_yaw = isinstance(yaw_val, (int, float))
    has_real_roll = isinstance(roll_val, (int, float))

    if has_real_pitch or has_real_yaw or has_real_roll:
        pitch = float(pitch_val) if has_real_pitch else 0.0
        yaw = float(yaw_val) if has_real_yaw else 0.0
        roll = float(roll_val) if has_real_roll else 0.0

        quat = None
        quat_data = getattr(rot_data, 'quaternion', None)
        if quat_data is not None:
            if isinstance(quat_data, dict):
                quat = Quaternion(
                    x=float(quat_data.get('x', 0.0)),
                    y=float(quat_data.get('y', 0.0)),
                    z=float(quat_data.get('z', 0.0)),
                    w=float(quat_data.get('w', 1.0)),
                )
            elif hasattr(quat_data, 'x'):
                qx = getattr(quat_data, 'x', 0.0)
                qy = getattr(quat_data, 'y', 0.0)
                qz = getattr(quat_data, 'z', 0.0)
                qw = getattr(quat_data, 'w', 1.0)
                if all(isinstance(v, (int, float)) for v in [qx, qy, qz, qw]):
                    quat = Quaternion(x=float(qx), y=float(qy), z=float(qz), w=float(qw))

        return Rotation(pitch=pitch, yaw=yaw, roll=roll, quaternion=quat)

    return Rotation(0.0, 0.0, 0.0)


def normalize_players(header: Header | None, frames: list[Any]) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Create unified player identity mapping across header and frame data."""

    if header is None or not getattr(header, "players", None):
        return {}, {}

    identities = build_player_identities(header.players)
    alias_lookup = build_alias_lookup(identities)

    players_index: dict[str, dict[str, Any]] = {}
    for identity in identities:
        team_index = 0 if identity.team == "BLUE" else 1 if identity.team == "ORANGE" else 0
        players_index[identity.canonical_id] = {
            "name": identity.display_name,
            "team_index": team_index,
            "team_name": identity.team,
            "platform_ids": identity.platform_ids,
            "header_index": identity.header_index,
            "aliases": identity.aliases,
            "slug": identity.slug,
        }

    if frames:
        header_ids = [identity.canonical_id for identity in identities]
        sampled_ids: list[str] = []
        for frame in frames[:10]:
            try:
                players = []
                if hasattr(frame, "players"):
                    players = frame.players  # type: ignore[assignment]
                elif isinstance(frame, dict):
                    players = frame.get("players", [])
                for player in players:
                    raw_id = None
                    if hasattr(player, "player_id"):
                        raw_id = getattr(player, "player_id")
                    elif isinstance(player, dict):
                        raw_id = player.get("player_id")
                    if raw_id is None:
                        continue
                    raw_id_str = str(raw_id)
                    if raw_id_str and raw_id_str not in sampled_ids:
                        sampled_ids.append(raw_id_str)
            except (AttributeError, TypeError):
                continue

        for idx, raw_id in enumerate(sampled_ids):
            if raw_id in alias_lookup:
                continue
            if idx < len(header_ids):
                alias_lookup[raw_id] = header_ids[idx]

    return players_index, alias_lookup


def build_timeline(header: Header, frames: list[Any]) -> list[Frame]:
    """Build normalized timeline from header and network frame data.
    
    Args:
        header: Parsed header information
        frames: Network frame data (may be empty for header-only)
        
    Returns:
        List of normalized Frame objects
    """
    if not frames:
        # Header-only mode - create minimal timeline
        return [
            Frame(
                timestamp=0.0,
                ball=BallFrame(
                    position=Vec3(0.0, 0.0, 93.15),  # Ball spawn height
                    velocity=Vec3(0.0, 0.0, 0.0),
                    angular_velocity=Vec3(0.0, 0.0, 0.0)
                ),
                players=[],
                boost_pad_events=[],
            )
        ]
    
    # Get player mapping
    players_index, alias_lookup = normalize_players(header, frames)

    player_supersonic_state: dict[str, bool] = {}
    player_prev_position: dict[str, Vec3] = {}
    player_prev_timestamp: dict[str, float] = {}
    
    # Convert frames to normalized format
    normalized_frames = []
    
    for frame_data in frames:
        try:
            # Extract timestamp
            timestamp = 0.0
            if hasattr(frame_data, 'timestamp'):
                timestamp = float(frame_data.timestamp)
            elif hasattr(frame_data, 'time'):
                timestamp = float(frame_data.time)
            elif isinstance(frame_data, dict) and 'timestamp' in frame_data:
                timestamp = float(frame_data['timestamp'])
            elif isinstance(frame_data, dict) and 'time' in frame_data:
                timestamp = float(frame_data['time'])
            
            # Extract ball state
            ball_pos = Vec3(0.0, 0.0, 93.15)
            ball_vel = Vec3(0.0, 0.0, 0.0)
            ball_ang_vel = Vec3(0.0, 0.0, 0.0)
            
            if hasattr(frame_data, 'ball'):
                ball_pos = to_field_coords(frame_data.ball.position)
                ball_vel = to_field_coords(frame_data.ball.velocity)
                if hasattr(frame_data.ball, 'angular_velocity'):
                    ball_ang_vel = to_field_coords(frame_data.ball.angular_velocity)
            elif isinstance(frame_data, dict) and 'ball' in frame_data:
                ball = frame_data['ball']
                if isinstance(ball, dict):
                    ball_pos = to_field_coords(ball.get('position', {}))
                    ball_vel = to_field_coords(ball.get('velocity', {}))
                    ball_ang_vel = to_field_coords(ball.get('angular_velocity', {}))
            
            ball_frame = BallFrame(
                position=ball_pos,
                velocity=ball_vel,
                angular_velocity=ball_ang_vel
            )
            
            # Extract player states
            # Collect latest player state per player_id to avoid duplicates
            player_frames_map: dict[str, PlayerFrame] = {}
            players_data = []
            
            if hasattr(frame_data, 'players'):
                players_data = frame_data.players
            elif isinstance(frame_data, dict) and 'players' in frame_data:
                players_data = frame_data['players']
            
            for player_data in players_data:
                try:
                    # Extract player ID
                    player_id = "unknown"
                    if hasattr(player_data, 'player_id'):
                        player_id = str(player_data.player_id)
                    elif isinstance(player_data, dict) and 'player_id' in player_data:
                        player_id = str(player_data['player_id'])

                    canonical_id = alias_lookup.get(player_id, player_id)
                    if canonical_id != player_id:
                        alias_lookup.setdefault(player_id, canonical_id)
                    if canonical_id not in players_index and player_id in players_index:
                        canonical_id = player_id
                    
                    # Get team from player index or frame data  
                    team = 0
                    index_entry = players_index.get(canonical_id)
                    if index_entry and index_entry.get('team_index') is not None:
                        team = int(index_entry['team_index'])
                    
                    # If no team from index, try frame data
                    if team == 0:  # Only override if still default
                        if hasattr(player_data, 'team') and player_data.team is not None:
                            team = int(player_data.team)
                        elif isinstance(player_data, dict) and 'team' in player_data:
                            team = int(player_data['team'])
                    
                    # Extract position and other data
                    position = Vec3(0.0, 0.0, 17.0)  # Car height
                    velocity = Vec3(0.0, 0.0, 0.0)
                    rotation: Rotation | Vec3 = Rotation(0.0, 0.0, 0.0)
                    boost_amount = 33  # Starting boost

                    if hasattr(player_data, 'position'):
                        position = to_field_coords(player_data.position)
                    elif isinstance(player_data, dict) and 'position' in player_data:
                        position = to_field_coords(player_data['position'])

                    if hasattr(player_data, 'velocity'):
                        velocity = to_field_coords(player_data.velocity)
                    elif isinstance(player_data, dict) and 'velocity' in player_data:
                        velocity = to_field_coords(player_data['velocity'])

                    # Extract rotation - handle both new format (pitch/yaw/roll + quaternion)
                    # and legacy format (x/y/z)
                    if hasattr(player_data, 'rotation'):
                        rotation = _parse_rotation(player_data.rotation)
                    elif isinstance(player_data, dict) and 'rotation' in player_data:
                        rotation = _parse_rotation(player_data['rotation'])
                    
                    if hasattr(player_data, 'boost_amount'):
                        boost_amount = max(0, min(100, int(player_data.boost_amount)))
                    elif isinstance(player_data, dict):
                        # Accept both 'boost_amount' (Rust shape) and shorter 'boost'
                        if 'boost_amount' in player_data:
                            boost_amount = max(0, min(100, int(player_data['boost_amount'])))
                        elif 'boost' in player_data:
                            boost_amount = max(0, min(100, int(player_data['boost'])))
                    
                    # Extract boolean flags with proper handling
                    raw_supersonic_flag = False
                    is_on_ground = True
                    is_demolished = False
                    
                    if hasattr(player_data, 'is_supersonic'):
                        raw_supersonic_flag = bool(player_data.is_supersonic)
                    elif isinstance(player_data, dict) and 'is_supersonic' in player_data:
                        raw_supersonic_flag = bool(player_data['is_supersonic'])
                    
                    if hasattr(player_data, 'is_on_ground'):
                        is_on_ground = bool(player_data.is_on_ground)
                    elif isinstance(player_data, dict) and 'is_on_ground' in player_data:
                        is_on_ground = bool(player_data['is_on_ground'])
                    
                    if hasattr(player_data, 'is_demolished'):
                        is_demolished = bool(player_data.is_demolished)
                    elif isinstance(player_data, dict) and 'is_demolished' in player_data:
                        is_demolished = bool(player_data['is_demolished'])

                    linear_speed = math.sqrt(
                        velocity.x * velocity.x + velocity.y * velocity.y + velocity.z * velocity.z
                    )
                    horizontal_speed = math.hypot(velocity.x, velocity.y)
                    prev_pos = player_prev_position.get(canonical_id)
                    prev_time = player_prev_timestamp.get(canonical_id)
                    derivative_speed = 0.0
                    if prev_pos is not None and prev_time is not None:
                        dt = max(timestamp - prev_time, MIN_FRAME_DT)
                        dx = position.x - prev_pos.x
                        dy = position.y - prev_pos.y
                        dz = position.z - prev_pos.z
                        derivative_speed = math.sqrt(dx * dx + dy * dy + dz * dz) / dt

                    state = player_supersonic_state.get(canonical_id, False)
                    if raw_supersonic_flag:
                        state = True
                    elif linear_speed >= SUPERSONIC_ENTRY_UU_S or horizontal_speed >= SUPERSONIC_ENTRY_UU_S:
                        state = True
                    elif state and derivative_speed >= SUPERSONIC_DERIVATIVE_ENTRY_UU_S and horizontal_speed >= SUPERSONIC_EXIT_UU_S:
                        state = True
                    elif state and horizontal_speed >= SUPERSONIC_EXIT_UU_S:
                        state = True
                    else:
                        state = False

                    player_supersonic_state[canonical_id] = state
                    is_supersonic = raw_supersonic_flag or state
                    
                    player_frame = PlayerFrame(
                        player_id=canonical_id,
                        team=team,
                        position=position,
                        velocity=velocity,
                        rotation=rotation,
                        boost_amount=boost_amount,
                        is_supersonic=is_supersonic,
                        is_on_ground=is_on_ground,
                        is_demolished=is_demolished
                    )
                    
                    # Keep the latest state seen in this frame for each unique player ID
                    player_frames_map[canonical_id] = player_frame

                    if canonical_id not in players_index:
                        players_index[canonical_id] = {
                            "name": sanitize_display_name(getattr(player_data, "name", canonical_id)),
                            "team_index": team,
                            "team_name": "BLUE" if team == 0 else "ORANGE",
                            "platform_ids": {},
                            "header_index": -1,
                            "aliases": tuple(sorted({canonical_id, player_id})),
                            "slug": canonical_id,
                        }
                    alias_lookup.setdefault(player_id, canonical_id)

                    player_prev_position[canonical_id] = position
                    player_prev_timestamp[canonical_id] = timestamp

                except (ValueError, TypeError, AttributeError):
                    # Skip malformed player data
                    continue

            pad_events: list[BoostPadEventFrame] = []
            raw_pad_events: list[Any] = []
            if hasattr(frame_data, "boost_pad_events"):
                candidate = getattr(frame_data, "boost_pad_events")
                if isinstance(candidate, list):
                    raw_pad_events = candidate
                elif isinstance(candidate, tuple):
                    raw_pad_events = list(candidate)
                elif candidate is None:
                    raw_pad_events = []
            elif isinstance(frame_data, dict) and "boost_pad_events" in frame_data:
                raw_value = frame_data.get("boost_pad_events", [])
                if isinstance(raw_value, list):
                    raw_pad_events = raw_value

            for raw_event in raw_pad_events:
                if not isinstance(raw_event, dict):
                    continue
                pad_id_raw = raw_event.get("pad_id")
                if pad_id_raw is None:
                    continue
                try:
                    pad_id = int(pad_id_raw)
                except (TypeError, ValueError):
                    continue

                status = str(raw_event.get("status", "UNKNOWN")).upper()
                if status not in {"COLLECTED", "RESPAWNED"}:
                    status = "COLLECTED" if "COLLECT" in status else status
                is_big = bool(raw_event.get("is_big", False))

                player_id_value = raw_event.get("player_id")
                player_index_value = raw_event.get("player_index")
                canonical_player_id: str | None = None
                if isinstance(player_id_value, str) and player_id_value:
                    canonical_player_id = alias_lookup.get(player_id_value, player_id_value)
                    alias_lookup.setdefault(player_id_value, canonical_player_id)
                elif player_index_value is not None:
                    try:
                        idx_value = int(player_index_value)
                    except (TypeError, ValueError):
                        idx_value = None
                    if idx_value is not None:
                        candidate = f"player_{idx_value}"
                        canonical_player_id = alias_lookup.get(candidate, candidate)
                        alias_lookup.setdefault(candidate, canonical_player_id)
                player_team_value = raw_event.get("player_team")
                try:
                    player_team = int(player_team_value) if player_team_value is not None else None
                except (TypeError, ValueError):
                    player_team = None

                actor_id_value = raw_event.get("actor_id")
                try:
                    actor_id = int(actor_id_value) if actor_id_value is not None else None
                except (TypeError, ValueError):
                    actor_id = None

                instigator_value = raw_event.get("instigator_actor_id")
                try:
                    instigator_actor_id = int(instigator_value) if instigator_value is not None else None
                except (TypeError, ValueError):
                    instigator_actor_id = None

                raw_state_value = raw_event.get("raw_state")
                try:
                    raw_state = int(raw_state_value) if raw_state_value is not None else None
                except (TypeError, ValueError):
                    raw_state = None

                position_value = raw_event.get("position")
                position = to_field_coords(position_value) if position_value else None

                event_timestamp = raw_event.get("timestamp")
                try:
                    event_time = float(event_timestamp) if event_timestamp is not None else None
                except (TypeError, ValueError):
                    event_time = None

                object_name = raw_event.get("object_name")
                object_name_str = str(object_name) if isinstance(object_name, str) and object_name else None

                pad_events.append(
                    BoostPadEventFrame(
                        pad_id=pad_id,
                        status=status,
                        is_big=is_big,
                        player_id=canonical_player_id,
                        player_team=player_team,
                        player_index=int(player_index_value) if isinstance(player_index_value, (int, float)) else None,
                        actor_id=actor_id,
                        instigator_actor_id=instigator_actor_id,
                        raw_state=raw_state,
                        position=position,
                        timestamp=event_time,
                        object_name=object_name_str,
                    )
                )

            # Create normalized frame
            normalized_frame = Frame(
                timestamp=timestamp,
                ball=ball_frame,
                players=list(player_frames_map.values()),
                boost_pad_events=pad_events,
            )
            
            normalized_frames.append(normalized_frame)
        
        except (ValueError, TypeError, AttributeError):
            # Skip malformed frames
            continue
    
    # Sort by timestamp to ensure chronological order
    normalized_frames.sort(key=lambda f: f.timestamp)

    # Align timestamps to the in-game clock (kickoff = 0) and drop postgame junk
    normalized_frames = _align_match_clock(normalized_frames, header)

    # Return frames or minimal fallback
    return normalized_frames if normalized_frames else [
        Frame(
            timestamp=0.0,
            ball=BallFrame(
                position=Vec3(0.0, 0.0, 93.15),
                velocity=Vec3(0.0, 0.0, 0.0),
                angular_velocity=Vec3(0.0, 0.0, 0.0)
            ),
            players=[],
            boost_pad_events=[],
        )
    ]


def _align_match_clock(frames: list[Frame], header: Header | None) -> list[Frame]:
    """Shift frame timestamps so kickoff starts at 0 and prune post-game frames."""

    if not frames:
        return frames

    start_time = frames[0].timestamp
    end_time = frames[-1].timestamp
    frame_rate = measure_frame_rate(frames)

    # Collect candidate end times (absolute timestamps) from header metadata
    candidates: list[float] = []
    if header is not None:
        header_duration = float(getattr(header, "match_length", 0.0) or 0.0)
        if header_duration > 0:
            candidates.append(start_time + header_duration)

        goal_times: list[float] = []
        for goal in getattr(header, "goals", []) or []:
            if goal.frame is None:
                continue
            if frame_rate > 0:
                goal_times.append(start_time + (int(goal.frame) / frame_rate))
            else:
                idx = int(goal.frame)
                if idx < 0:
                    continue
                if idx >= len(frames):
                    idx = len(frames) - 1
                goal_times.append(frames[idx].timestamp)

        if goal_times:
            candidates.append(max(goal_times) + GOAL_POST_BUFFER_S)

    if candidates:
        end_time = min(end_time, max(candidates))

    if end_time <= start_time:
        end_time = frames[-1].timestamp

    adjusted: list[Frame] = []
    for frame in frames:
        t = frame.timestamp
        if t < start_time - 1e-3:
            continue
        if t > end_time + 1e-3:
            break
        shifted = t - start_time
        if abs(shifted) < 1e-6:
            shifted = 0.0
        normalized_events: list[BoostPadEventFrame] = []
        for event in getattr(frame, "boost_pad_events", []) or []:
            event_time = getattr(event, "timestamp", None)
            new_time: float | None
            if event_time is None:
                new_time = None
            else:
                try:
                    new_time = float(event_time) - start_time
                except (TypeError, ValueError):
                    new_time = None
            if new_time is not None and abs(new_time) < 1e-6:
                new_time = 0.0
            normalized_events.append(replace(event, timestamp=new_time))

        adjusted.append(
            replace(
                frame,
                timestamp=shifted,
                boost_pad_events=normalized_events,
            )
        )

    if not adjusted:
        adjusted.append(replace(frames[0], timestamp=0.0))

    return adjusted
