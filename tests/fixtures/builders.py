"""Test builder functions for creating synthetic frame and player data.

These functions provide a consistent API for building test fixtures
across all test files, reducing duplication and ensuring consistency.
"""

from __future__ import annotations

from rlcoach.field_constants import Vec3
from rlcoach.parser.types import BallFrame, Frame, PlayerFrame
from rlcoach.physics_constants import SUPERSONIC_SPEED_SQUARED


def create_test_player(
    player_id: str,
    team: int,
    position: Vec3 | None = None,
    velocity: Vec3 | None = None,
    rotation: Vec3 | None = None,
    boost: float = 50.0,
    is_on_ground: bool = True,
    is_demolished: bool = False,
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
    if rotation is None:
        rotation = Vec3(0.0, 0.0, 0.0)

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
        is_supersonic=is_supersonic,
        is_on_ground=is_on_ground,
        is_demolished=is_demolished,
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
    )


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
