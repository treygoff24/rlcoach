"""Field constants and coordinate system for Rocket League analysis.

This module defines the standard RLBot field coordinate system and provides
utilities for field-relative calculations used throughout the analysis pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple


class Vec3(NamedTuple):
    """3D vector with x, y, z components."""

    x: float
    y: float
    z: float

    def __add__(self, other: Vec3) -> Vec3:
        return Vec3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: Vec3) -> Vec3:
        return Vec3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, scalar: float) -> Vec3:
        return Vec3(self.x * scalar, self.y * scalar, self.z * scalar)


@dataclass(frozen=True)
class BoostPad:
    """Boost pad metadata for classification of pickups."""

    pad_id: int
    position: Vec3
    is_big: bool
    radius: float


class FieldConstants:
    """Standard RLBot field dimensions and coordinate system.

    Coordinate system:
    - X-axis: -4096 to +4096 (side walls)
    - Y-axis: -5120 to +5120 (goal lines)
    - Z-axis: 0 to 2044+ (floor to ceiling)
    - Origin (0,0,0) is center of field at ground level
    """

    # Field boundaries (RLBot standard)
    SIDE_WALL_X: float = 4096.0
    BACK_WALL_Y: float = 5120.0
    CEILING_Z: float = 2044.0

    # Goal dimensions
    GOAL_WIDTH: float = 892.755  # Half-width of goal opening
    GOAL_HEIGHT: float = 642.775
    GOAL_DEPTH: float = 880.0

    # Boost pad pickup radii (uu)
    SMALL_BOOST_RADIUS: float = 170.0
    BIG_BOOST_RADIUS: float = 250.0

    # Boost pads - Large (100%) including corners and back-wall pads
    BIG_BOOST_POSITIONS: tuple[Vec3, ...] = (
        Vec3(-3584.0, -4096.0, 73.0),
        Vec3(3584.0, -4096.0, 73.0),
        Vec3(-3584.0, 4096.0, 73.0),
        Vec3(3584.0, 4096.0, 73.0),
        Vec3(0.0, -4608.0, 73.0),
        Vec3(0.0, 4608.0, 73.0),
    )

    CORNER_BOOST_POSITIONS: tuple[Vec3, ...] = BIG_BOOST_POSITIONS[:4]

    # Small boost pads (12%) - full RLBot reference table
    SMALL_BOOST_POSITIONS: tuple[Vec3, ...] = (
        Vec3(0.0, -4240.0, 70.0),
        Vec3(-1792.0, -4184.0, 70.0),
        Vec3(1792.0, -4184.0, 70.0),
        Vec3(-940.0, -3308.0, 70.0),
        Vec3(940.0, -3308.0, 70.0),
        Vec3(0.0, -2816.0, 70.0),
        Vec3(-3584.0, -2484.0, 70.0),
        Vec3(3584.0, -2484.0, 70.0),
        Vec3(-1788.0, -2300.0, 70.0),
        Vec3(1788.0, -2300.0, 70.0),
        Vec3(-2048.0, -1036.0, 70.0),
        Vec3(0.0, -1024.0, 70.0),
        Vec3(2048.0, -1036.0, 70.0),
        Vec3(-1024.0, 0.0, 70.0),
        Vec3(1024.0, 0.0, 70.0),
        Vec3(-2048.0, 1036.0, 70.0),
        Vec3(0.0, 1024.0, 70.0),
        Vec3(2048.0, 1036.0, 70.0),
        Vec3(-1788.0, 2300.0, 70.0),
        Vec3(1788.0, 2300.0, 70.0),
        Vec3(-3584.0, 2484.0, 70.0),
        Vec3(3584.0, 2484.0, 70.0),
        Vec3(0.0, 2816.0, 70.0),
        Vec3(-940.0, 3310.0, 70.0),
        Vec3(940.0, 3308.0, 70.0),
        Vec3(-1792.0, 4184.0, 70.0),
        Vec3(1792.0, 4184.0, 70.0),
        Vec3(0.0, 4240.0, 70.0),
    )

    @classmethod
    def is_in_bounds(cls, pos: Vec3) -> bool:
        """Check if position is within field boundaries."""
        return (
            -cls.SIDE_WALL_X <= pos.x <= cls.SIDE_WALL_X
            and -cls.BACK_WALL_Y <= pos.y <= cls.BACK_WALL_Y
            and 0 <= pos.z <= cls.CEILING_Z
        )

    @classmethod
    def get_field_third(cls, pos: Vec3) -> str:
        """Get field third: 'defensive', 'neutral', 'offensive' based on Y position."""
        if pos.y < -cls.BACK_WALL_Y / 3:
            return "defensive"
        elif pos.y > cls.BACK_WALL_Y / 3:
            return "offensive"
        else:
            return "neutral"

    @classmethod
    def get_field_half(cls, pos: Vec3) -> str:
        """Get field half: 'blue' (negative Y) or 'orange' (positive Y)."""
        return "blue" if pos.y < 0 else "orange"

    @classmethod
    def distance_to_goal(cls, pos: Vec3, defending_team: int) -> float:
        """Calculate distance from position to goal line.

        Args:
            pos: Position vector
            defending_team: 0 for blue (defends negative Y), 1 for orange (defends positive Y)

        Returns:
            Distance to the goal line being defended
        """
        goal_y = -cls.BACK_WALL_Y if defending_team == 0 else cls.BACK_WALL_Y
        return abs(pos.y - goal_y)


# Combined boost pad table (6 big + 28 small)
BOOST_PAD_TABLE: tuple[BoostPad, ...] = tuple(
    [
        BoostPad(idx, pos, True, FieldConstants.BIG_BOOST_RADIUS)
        for idx, pos in enumerate(FieldConstants.BIG_BOOST_POSITIONS)
    ]
    + [
        BoostPad(
            idx + len(FieldConstants.BIG_BOOST_POSITIONS),
            pos,
            False,
            FieldConstants.SMALL_BOOST_RADIUS,
        )
        for idx, pos in enumerate(FieldConstants.SMALL_BOOST_POSITIONS)
    ]
)

FieldConstants.BOOST_PADS = BOOST_PAD_TABLE

# Export commonly used constants
FIELD = FieldConstants()


def find_big_pad_blue_corner() -> BoostPad:
    """Find a big boost pad on the blue (negative Y) side.

    Returns:
        A big boost pad on the blue corner
    """
    for pad in BOOST_PAD_TABLE:
        if pad.is_big and pad.position.y < 0:
            return pad
    raise ValueError("No blue corner big pad found")


def find_big_pad_orange_corner() -> BoostPad:
    """Find a big boost pad on the orange (positive Y) side.

    Returns:
        A big boost pad on the orange corner
    """
    for pad in BOOST_PAD_TABLE:
        if pad.is_big and pad.position.y > 0:
            return pad
    raise ValueError("No orange corner big pad found")


def find_small_pad_neutral() -> BoostPad:
    """Find a small boost pad near midfield.

    Returns:
        A small boost pad near the center
    """
    for pad in BOOST_PAD_TABLE:
        if not pad.is_big and abs(pad.position.y) < 1500:
            return pad
    raise ValueError("No neutral small pad found")


def find_small_pad_blue_side() -> BoostPad:
    """Find a small boost pad on blue side.

    Returns:
        A small boost pad on the blue (negative Y) side
    """
    for pad in BOOST_PAD_TABLE:
        if not pad.is_big and pad.position.y < -2000:
            return pad
    raise ValueError("No blue side small pad found")


def find_small_pad_orange_side() -> BoostPad:
    """Find a small boost pad on orange side.

    Returns:
        A small boost pad on the orange (positive Y) side
    """
    for pad in BOOST_PAD_TABLE:
        if not pad.is_big and pad.position.y > 2000:
            return pad
    raise ValueError("No orange side small pad found")
