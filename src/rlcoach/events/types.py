"""Event type definitions for Rocket League replay analysis.

This module contains all dataclasses and enums used to represent
game events detected from replay data.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from ..field_constants import Vec3


@dataclass(frozen=True)
class GoalEvent:
    """Goal event with scorer and shot metrics."""

    t: float  # Timestamp from match start
    frame: int | None = None
    scorer: str | None = None  # Player ID who scored
    team: str | None = None  # "BLUE" or "ORANGE"
    assist: str | None = None  # Player ID with assist
    shot_speed_kph: float = 0.0
    distance_m: float = 0.0
    on_target: bool = True
    tickmark_lead_seconds: float = 0.0


@dataclass(frozen=True)
class DemoEvent:
    """Demolition event with victim and attacker."""

    t: float
    victim: str
    attacker: str | None = None
    team_attacker: str | None = None  # "BLUE" or "ORANGE"
    team_victim: str | None = None
    location: Vec3 | None = None


@dataclass(frozen=True)
class KickoffEvent:
    """Kickoff event with player analysis."""

    phase: str  # "INITIAL" or "OT"
    t_start: float
    players: list[dict[str, Any]]  # Player kickoff analysis
    outcome: str = "NEUTRAL"  # Simplified outcome
    first_touch_player: str | None = None
    time_to_first_touch: float | None = None


@dataclass(frozen=True)
class BoostPickupEvent:
    """Boost pad pickup event."""

    t: float
    player_id: str
    pad_type: str  # "SMALL" or "BIG"
    stolen: bool = False  # True if on opponent half
    pad_id: int = -1  # Index in boost pad arrays
    location: Vec3 | None = None
    frame: int | None = None
    boost_before: float | None = None
    boost_after: float | None = None
    boost_gain: float = 0.0


@dataclass
class PadState:
    """Runtime tracking for boost pad availability."""

    available_at: float = 0.0
    last_pickup: float | None = None


@dataclass(frozen=True)
class PadEnvelope:
    """Spatial heuristics for matching a player to a boost pad."""

    radius: float
    max_distance: float
    height_tolerance: float


class TouchContext(Enum):
    """Context of a ball touch based on car state."""

    GROUND = "ground"  # Car on ground when touching ball
    AERIAL = "aerial"  # Car in air, ball also elevated
    WALL = "wall"  # Car on/near wall when hitting ball
    CEILING = "ceiling"  # Car on ceiling
    HALF_VOLLEY = "half_volley"  # Just left ground (jumping touch)
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class TouchEvent:
    """Player-ball contact event."""

    t: float
    player_id: str
    location: Vec3
    frame: int | None = None
    ball_speed_kph: float = 0.0
    outcome: str = "NEUTRAL"  # Simplified classification
    is_save: bool = False
    touch_context: TouchContext = TouchContext.UNKNOWN
    car_height: float = 0.0
    is_first_touch: bool = False


@dataclass(frozen=True)
class ChallengeEvent:
    """50/50 contest event between opposing players."""

    t: float
    first_player: str
    second_player: str
    first_team: str
    second_team: str
    outcome: str  # Perspective of first player: WIN/LOSS/NEUTRAL
    winner_team: str | None
    location: Vec3
    depth_m: float
    duration: float
    risk_first: float
    risk_second: float


@dataclass(frozen=True)
class TimelineEvent:
    """Timeline entry for chronological event aggregation."""

    t: float
    type: str  # Event type from schema enum
    frame: int | None = None
    player_id: str | None = None
    team: str | None = None
    data: dict[str, Any] | None = None
