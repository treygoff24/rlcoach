"""Test builder functions for creating synthetic frame and player data.

These functions provide a consistent API for building test fixtures
across all test files, reducing duplication and ensuring consistency.
"""

from __future__ import annotations

from rlcoach.field_constants import Vec3
from rlcoach.parser.types import (
    BallFrame,
    Frame,
    ParserComponentEvent,
    PlayerFrame,
    Quaternion,
    Rotation,
)
from rlcoach.physics_constants import SUPERSONIC_SPEED_SQUARED


def create_test_player(
    player_id: str,
    team: int,
    position: Vec3 | None = None,
    velocity: Vec3 | None = None,
    angular_velocity: Vec3 | None = None,
    rotation: Rotation | Vec3 | None = None,
    quaternion: Quaternion | None = None,
    boost: float = 50.0,
    boost_active: bool | None = None,
    boost_active_raw: int | None = None,
    boost_amount_raw: int | None = None,
    boost_grant_count: int | None = None,
    throttle: float | None = None,
    steer: float | None = None,
    handbrake: bool | None = None,
    throttle_raw: int | None = None,
    steer_raw: int | None = None,
    is_on_ground: bool = True,
    is_demolished: bool = False,
    is_jumping: bool | None = None,
    is_dodging: bool | None = None,
    is_double_jumping: bool | None = None,
    jump_active_raw: int | None = None,
    dodge_active_raw: int | None = None,
    double_jump_active_raw: int | None = None,
    sleeping: bool = False,
) -> PlayerFrame:
    """Create a test PlayerFrame with sensible defaults.

    Args:
        player_id: Unique player identifier
        team: Team number (0=blue, 1=orange)
        position: Position vector (defaults to field center at ground level)
        velocity: Velocity vector (defaults to stationary)
        rotation: Rotation as Vec3 (pitch, yaw, roll) (defaults to level)
        boost: Boost amount 0-100 (defaults to 50)
        is_on_ground: Whether player is on ground (defaults to True)
        is_demolished: Whether player is demolished (defaults to False)

    Returns:
        PlayerFrame with specified or default values
    """
    if position is None:
        position = Vec3(0.0, 0.0, 17.0)
    if velocity is None:
        velocity = Vec3(0.0, 0.0, 0.0)
    if angular_velocity is None:
        angular_velocity = Vec3(0.0, 0.0, 0.0)
    if rotation is None:
        rotation = Vec3(0.0, 0.0, 0.0)
    elif isinstance(rotation, Vec3) and quaternion is not None:
        rotation = Rotation(
            pitch=rotation.x,
            yaw=rotation.y,
            roll=rotation.z,
            quaternion=quaternion,
        )

    # Calculate is_supersonic from velocity
    speed_sq = velocity.x**2 + velocity.y**2 + velocity.z**2
    is_supersonic = speed_sq > SUPERSONIC_SPEED_SQUARED

    return PlayerFrame(
        player_id=player_id,
        team=team,
        position=position,
        velocity=velocity,
        rotation=rotation,
        boost_amount=boost,
        angular_velocity=angular_velocity,
        sleeping=sleeping,
        throttle=throttle,
        steer=steer,
        handbrake=handbrake,
        throttle_raw=throttle_raw,
        steer_raw=steer_raw,
        boost_active=boost_active,
        boost_active_raw=boost_active_raw,
        boost_amount_raw=boost_amount_raw,
        boost_grant_count=boost_grant_count,
        is_supersonic=is_supersonic,
        is_on_ground=is_on_ground,
        is_demolished=is_demolished,
        is_jumping=is_jumping,
        is_dodging=is_dodging,
        is_double_jumping=is_double_jumping,
        jump_active_raw=jump_active_raw,
        dodge_active_raw=dodge_active_raw,
        double_jump_active_raw=double_jump_active_raw,
    )


def create_test_ball(
    position: Vec3 | None = None,
    velocity: Vec3 | None = None,
    angular_velocity: Vec3 | None = None,
) -> BallFrame:
    """Create a test BallFrame with sensible defaults.

    Args:
        position: Ball position (defaults to center at ball height)
        velocity: Ball velocity (defaults to stationary)
        angular_velocity: Ball spin (defaults to none)

    Returns:
        BallFrame with specified or default values
    """
    if position is None:
        position = Vec3(0.0, 0.0, 93.15)
    if velocity is None:
        velocity = Vec3(0.0, 0.0, 0.0)
    if angular_velocity is None:
        angular_velocity = Vec3(0.0, 0.0, 0.0)

    return BallFrame(
        position=position,
        velocity=velocity,
        angular_velocity=angular_velocity,
    )


def create_test_frame(
    timestamp: float,
    players: list[PlayerFrame],
    ball: BallFrame | None = None,
    component_events: list[ParserComponentEvent] | None = None,
) -> Frame:
    """Create a test Frame with player and ball data.

    Args:
        timestamp: Frame timestamp in seconds
        players: List of PlayerFrame objects
        ball: BallFrame (defaults to centered stationary ball)

    Returns:
        Frame with specified data
    """
    if ball is None:
        ball = create_test_ball()

    return Frame(
        timestamp=timestamp,
        ball=ball,
        players=players,
        component_events=component_events or [],
    )


def create_component_event(
    timestamp: float,
    kind: str,
    component: str,
    player_id: str,
    vector: Vec3 | None = None,
    raw_value: int | None = None,
    active: bool | None = None,
) -> ParserComponentEvent:
    """Create a parser-authored component event for synthetic tests."""
    return ParserComponentEvent(
        timestamp=timestamp,
        kind=kind,
        component=component,
        player_id=player_id,
        vector=vector,
        raw_value=raw_value,
        active=active,
    )


def with_flip_at(
    frames: list[Frame],
    timestamp: float,
    player_id: str,
    direction: Vec3 | None = None,
) -> list[Frame]:
    """Return frames with a dodge torque event attached at the closest timestamp."""
    if not frames:
        return frames
    if direction is None:
        direction = Vec3(1.0, 0.0, 0.0)

    closest = min(
        range(len(frames)), key=lambda idx: abs(frames[idx].timestamp - timestamp)
    )
    updated = list(frames)
    frame = updated[closest]
    event = create_component_event(
        timestamp=frame.timestamp,
        kind="dodge_torque",
        component="dodge",
        player_id=player_id,
        vector=direction,
    )
    updated[closest] = Frame(
        timestamp=frame.timestamp,
        ball=frame.ball,
        players=frame.players,
        boost_pad_events=frame.boost_pad_events,
        component_events=[*frame.component_events, event],
        parser_touch_events=frame.parser_touch_events,
        parser_demo_events=frame.parser_demo_events,
        parser_stat_events=frame.parser_stat_events,
        parser_tickmarks=frame.parser_tickmarks,
        parser_kickoff_markers=frame.parser_kickoff_markers,
    )
    return updated


def create_simple_replay_frames(
    duration_seconds: float = 60.0,
    frame_rate: float = 30.0,
    players: list[tuple[str, int]] | None = None,
) -> list[Frame]:
    """Create a sequence of simple test frames for a replay.

    Args:
        duration_seconds: Total duration of replay in seconds
        frame_rate: Frames per second
        players: List of (player_id, team) tuples (defaults to 2 players)

    Returns:
        List of Frame objects spanning the duration
    """
    if players is None:
        players = [("player1", 0), ("player2", 1)]

    frames = []
    num_frames = int(duration_seconds * frame_rate)
    dt = 1.0 / frame_rate

    for i in range(num_frames):
        timestamp = i * dt
        player_frames = [create_test_player(pid, team) for pid, team in players]
        frames.append(create_test_frame(timestamp, player_frames))

    return frames
