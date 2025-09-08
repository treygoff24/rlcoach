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
    
    # Boost pads - Large corner boost (100%)
    CORNER_BOOST_POSITIONS: tuple[Vec3, ...] = (
        Vec3(-3584.0, -4240.0, 73.0),  # Blue left corner
        Vec3(3584.0, -4240.0, 73.0),   # Blue right corner  
        Vec3(-3584.0, 4240.0, 73.0),   # Orange left corner
        Vec3(3584.0, 4240.0, 73.0),    # Orange right corner
    )
    
    # Small boost pads (12%) - simplified set of key positions
    SMALL_BOOST_POSITIONS: tuple[Vec3, ...] = (
        # Mid-field small boosts
        Vec3(-1788.0, 0.0, 70.0),
        Vec3(1788.0, 0.0, 70.0),
        Vec3(0.0, -2816.0, 70.0),
        Vec3(0.0, 2816.0, 70.0),
        # Additional strategic positions
        Vec3(-940.0, -3308.0, 70.0),
        Vec3(940.0, -3308.0, 70.0),
        Vec3(-940.0, 3308.0, 70.0), 
        Vec3(940.0, 3308.0, 70.0),
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


# Export commonly used constants
FIELD = FieldConstants()