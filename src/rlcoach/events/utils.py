"""Shared utility functions for event detection.

Math helpers, team name conversion, and field geometry utilities
used across multiple detector modules.
"""

from __future__ import annotations

import math

from ..field_constants import FIELD, Vec3
from ..parser.types import Frame, PlayerFrame


def distance_3d(pos1: Vec3, pos2: Vec3) -> float:
    """Calculate 3D Euclidean distance between two positions."""
    dx = pos1.x - pos2.x
    dy = pos1.y - pos2.y
    dz = pos1.z - pos2.z
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def vector_magnitude(vec: Vec3) -> float:
    """Calculate magnitude of a 3D vector."""
    return math.sqrt(vec.x * vec.x + vec.y * vec.y + vec.z * vec.z)


def relative_speed(player_velocity: Vec3, ball_velocity: Vec3) -> float:
    """Calculate magnitude of the relative velocity between player and ball."""
    dvx = player_velocity.x - ball_velocity.x
    dvy = player_velocity.y - ball_velocity.y
    dvz = player_velocity.z - ball_velocity.z
    return math.sqrt(dvx * dvx + dvy * dvy + dvz * dvz)


def team_name(idx: int | None) -> str:
    """Convert team index to team name string."""
    if idx == 0:
        return "BLUE"
    if idx == 1:
        return "ORANGE"
    return "UNKNOWN"


def is_toward_opponent_goal(team_idx: int, velocity: Vec3) -> bool:
    """Check if ball velocity is directed toward opponent's goal."""
    return velocity.y > 250.0 if team_idx == 0 else velocity.y < -250.0


def is_toward_own_goal(team_idx: int, velocity: Vec3) -> bool:
    """Check if ball velocity is directed toward own goal."""
    return velocity.y < -400.0 if team_idx == 0 else velocity.y > 400.0


def is_shot_on_target(team_idx: int, position: Vec3, velocity: Vec3) -> bool:
    """Check if current trajectory would enter opponent's goal."""
    if not is_toward_opponent_goal(team_idx, velocity):
        return False

    dy = velocity.y
    if abs(dy) < 1e-6:
        return False

    goal_y = FIELD.BACK_WALL_Y if team_idx == 0 else -FIELD.BACK_WALL_Y
    time_to_goal = (goal_y - position.y) / dy
    if time_to_goal <= 0 or time_to_goal > 3.5:
        return False

    est_x = position.x + velocity.x * time_to_goal
    est_z = position.z + velocity.z * time_to_goal
    if abs(est_x) > FIELD.GOAL_WIDTH or est_z > FIELD.GOAL_HEIGHT:
        return False

    return True


def is_in_defensive_third(team_idx: int, position: Vec3) -> bool:
    """Check if position is in the defensive third of the field."""
    if team_idx == 0:
        return position.y <= -FIELD.BACK_WALL_Y * 0.33
    return position.y >= FIELD.BACK_WALL_Y * 0.33


def nearest_player_ball_frame(
    frames: list[Frame], player_id: str, timestamp: float
) -> tuple[PlayerFrame | None, tuple[Vec3, Vec3] | None]:
    """Find the frame closest to timestamp and return player and ball state."""
    if not frames:
        return None, None
    closest: Frame | None = None
    best_delta = float("inf")
    for fr in frames:
        delta = abs(fr.timestamp - timestamp)
        if delta < best_delta:
            best_delta = delta
            closest = fr
    if closest is None:
        return None, None
    return closest.get_player_by_id(player_id), (closest.ball.position, closest.ball.velocity)
