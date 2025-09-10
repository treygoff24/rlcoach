"""Normalization layer for converting parser outputs to standardized timeline format.

This module transforms raw parser data into normalized structures with:
- Measured frame rates
- Standard RLBot coordinate system
- Unified player identity mapping
- Consistent timeline format
"""

from __future__ import annotations

import statistics
from typing import Any

from .field_constants import FIELD, Vec3
from .parser.types import Header, NetworkFrames, Frame, PlayerFrame, BallFrame


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


def normalize_players(header: Header, frames: list[Any]) -> dict[str, dict[str, Any]]:
    """Create unified player identity mapping across header and frame data.
    
    Args:
        header: Parsed header with player info
        frames: Network frame data (may be empty)
        
    Returns:
        Dict mapping player_id -> {name, team, platform_id, etc.}
    """
    players_index = {}
    
    # Start with header player information
    for i, player_info in enumerate(header.players):
        player_id = f"player_{i}"
        if player_info.platform_id:
            player_id = player_info.platform_id
        
        players_index[player_id] = {
            'name': player_info.name,
            'team': player_info.team,
            'platform_id': player_info.platform_id,
            'score': player_info.score,
            'header_index': i
        }
    
    # Augment with frame data if available
    if frames:
        # Extract unique player IDs from frames
        frame_player_ids = set()
        for frame in frames[:10]:  # Sample first few frames
            try:
                if hasattr(frame, 'players') and hasattr(frame.players, '__iter__'):
                    for player in frame.players:
                        if hasattr(player, 'player_id'):
                            frame_player_ids.add(player.player_id)
            except (TypeError, AttributeError):
                continue  # Skip malformed frames
        
        # Match frame players to header players by position/index
        frame_ids = sorted(frame_player_ids)
        header_ids = list(players_index.keys())
        
        for i, frame_id in enumerate(frame_ids):
            if i < len(header_ids):
                header_id = header_ids[i]
                if frame_id != header_id:
                    # Create alias mapping
                    players_index[frame_id] = players_index[header_id].copy()
                    players_index[frame_id]['alias_for'] = header_id
    
    return players_index


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
    players_index = normalize_players(header, frames)
    
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
            player_frames = []
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
                    
                    # Get team from player index or frame data  
                    team = 0
                    if player_id in players_index:
                        index_team = players_index[player_id].get('team')
                        if index_team is not None:
                            team = int(index_team)
                    
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
                    is_supersonic = False
                    is_on_ground = True
                    is_demolished = False
                    
                    if hasattr(player_data, 'is_supersonic'):
                        is_supersonic = bool(player_data.is_supersonic)
                    elif isinstance(player_data, dict) and 'is_supersonic' in player_data:
                        is_supersonic = bool(player_data['is_supersonic'])
                    
                    if hasattr(player_data, 'is_on_ground'):
                        is_on_ground = bool(player_data.is_on_ground)
                    elif isinstance(player_data, dict) and 'is_on_ground' in player_data:
                        is_on_ground = bool(player_data['is_on_ground'])
                    
                    if hasattr(player_data, 'is_demolished'):
                        is_demolished = bool(player_data.is_demolished)
                    elif isinstance(player_data, dict) and 'is_demolished' in player_data:
                        is_demolished = bool(player_data['is_demolished'])
                    
                    player_frame = PlayerFrame(
                        player_id=player_id,
                        team=team,
                        position=position,
                        velocity=velocity,
                        rotation=rotation,
                        boost_amount=boost_amount,
                        is_supersonic=is_supersonic,
                        is_on_ground=is_on_ground,
                        is_demolished=is_demolished
                    )
                    
                    player_frames.append(player_frame)
                
                except (ValueError, TypeError, AttributeError):
                    # Skip malformed player data
                    continue
            
            # Create normalized frame
            normalized_frame = Frame(
                timestamp=timestamp,
                ball=ball_frame,
                players=player_frames
            )
            
            normalized_frames.append(normalized_frame)
        
        except (ValueError, TypeError, AttributeError):
            # Skip malformed frames
            continue
    
    # Sort by timestamp to ensure chronological order
    normalized_frames.sort(key=lambda f: f.timestamp)
    
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
