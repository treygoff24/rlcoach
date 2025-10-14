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
from .parser.types import Header, NetworkFrames, Frame, PlayerFrame, BallFrame
from .utils.identity import (
    build_alias_lookup,
    build_player_identities,
    sanitize_display_name,
)

SUPERSONIC_ENTRY_UU_S = 2200.0
SUPERSONIC_EXIT_UU_S = 2100.0
SUPERSONIC_DERIVATIVE_ENTRY_UU_S = 2800.0
MIN_FRAME_DT = 1e-3


# Seconds to keep after the last recorded goal to account for replays + kickoff
GOAL_POST_BUFFER_S = 7.0


def measure_frame_rate(frames: list[Any]) -> float:
    """Measure actual frame rate from frame timestamps.
    
    Args:
        frames: List of frame data with timestamp information
        
    Returns:
        Measured frame rate in Hz (defaults to 30.0 if unmeasurable)
    """
    if not frames or len(frames) < 2:
        return 30.0
    
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
        return 30.0
    
    # Calculate time deltas between consecutive frames
    deltas = []
    for i in range(1, len(timestamps)):
        delta = timestamps[i] - timestamps[i-1]
        if delta > 0:  # Only positive deltas
            deltas.append(delta)
    
    if not deltas:
        return 30.0
    
    # Use median delta to avoid outliers from frame drops
    median_delta = statistics.median(deltas)
    if median_delta <= 0:
        return 30.0
    
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
                players=[]
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
                    rotation = Vec3(0.0, 0.0, 0.0)
                    boost_amount = 33  # Starting boost
                    
                    if hasattr(player_data, 'position'):
                        position = to_field_coords(player_data.position)
                    elif isinstance(player_data, dict) and 'position' in player_data:
                        position = to_field_coords(player_data['position'])
                    
                    if hasattr(player_data, 'velocity'):
                        velocity = to_field_coords(player_data.velocity)
                    elif isinstance(player_data, dict) and 'velocity' in player_data:
                        velocity = to_field_coords(player_data['velocity'])
                    
                    if hasattr(player_data, 'rotation'):
                        rotation = to_field_coords(player_data.rotation)
                    elif isinstance(player_data, dict) and 'rotation' in player_data:
                        rotation = to_field_coords(player_data['rotation'])
                    
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

            # Create normalized frame
            normalized_frame = Frame(
                timestamp=timestamp,
                ball=ball_frame,
                players=list(player_frames_map.values())
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
            players=[]
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
        adjusted.append(replace(frame, timestamp=shifted))

    if not adjusted:
        adjusted.append(replace(frames[0], timestamp=0.0))

    return adjusted
