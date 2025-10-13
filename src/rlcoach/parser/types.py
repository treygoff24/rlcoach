"""Core data types for the parser layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import NamedTuple, Any


class Vec3(NamedTuple):
    """3D vector with x, y, z components."""
    x: float
    y: float
    z: float


@dataclass(frozen=True)
class PlayerInfo:
    """Information about a player in the replay."""

    name: str
    platform_id: str | None = None
    team: int | None = None  # 0 or 1
    score: int = 0
    platform_ids: dict[str, str] = field(default_factory=dict)
    camera_settings: dict[str, float | int] | None = None
    loadout: dict[str, int | str | float] = field(default_factory=dict)
    stats: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Header:
    """Header information extracted from replay files.

    This represents the minimal data that can be reliably extracted
    from replay headers without full network frame parsing.
    """

    # Match metadata
    playlist_id: str | None = None
    map_name: str | None = None
    team_size: int = 0
    engine_build: str | None = None
    match_guid: str | None = None
    overtime: bool | None = None
    mutators: dict[str, str | int | float | bool] = field(default_factory=dict)

    # Match results
    team0_score: int = 0
    team1_score: int = 0
    match_length: float = 0.0  # seconds

    # Players
    players: list[PlayerInfo] = field(default_factory=list)

    # Goals from header (not full event list; minimal info)
    goals: list["GoalHeader"] = field(default_factory=list)
    highlights: list["Highlight"] = field(default_factory=list)

    # Quality and warnings
    quality_warnings: list[str] = field(default_factory=list)

    def __post_init__(self):
        """Validate header data after initialization."""
        if self.team_size < 0:
            raise ValueError("team_size cannot be negative")

        if self.team0_score < 0 or self.team1_score < 0:
            raise ValueError("team scores cannot be negative")

        if self.match_length < 0:
            raise ValueError("match_length cannot be negative")


@dataclass(frozen=True)
class GoalHeader:
    """Goal info extracted from the header properties."""

    frame: int | None = None
    player_name: str | None = None
    player_team: int | None = None


@dataclass(frozen=True)
class Highlight:
    """Replay highlight tick mark information."""

    frame: int | None = None
    ball_name: str | None = None
    car_name: str | None = None


@dataclass(frozen=True)
class NetworkFrames:
    """Network frame data extracted from replay files.

    This is a stub implementation for future network frame parsing.
    The actual implementation will contain frame-by-frame data for
    ball and player positions, boost pickups, etc.
    """

    frame_count: int = 0
    sample_rate: float = 30.0  # Expected FPS
    frames: list = field(default_factory=list)  # Will be list[Frame] when implemented

    def __post_init__(self):
        """Validate network frame data."""
        if self.frame_count < 0:
            raise ValueError("frame_count cannot be negative")

        if self.sample_rate <= 0:
            raise ValueError("sample_rate must be positive")


@dataclass(frozen=True)
class PlayerFrame:
    """Player state at a specific frame."""
    
    player_id: str
    team: int
    position: Vec3
    velocity: Vec3
    rotation: Vec3  # pitch, yaw, roll in radians
    boost_amount: int  # 0-100
    is_supersonic: bool = False
    is_on_ground: bool = True
    is_demolished: bool = False


@dataclass(frozen=True)
class BallFrame:
    """Ball state at a specific frame."""
    
    position: Vec3
    velocity: Vec3
    angular_velocity: Vec3


@dataclass(frozen=True)
class Frame:
    """Normalized frame containing all game state at a specific time."""
    
    timestamp: float  # seconds from match start
    ball: BallFrame
    players: list[PlayerFrame] = field(default_factory=list)
    
    def get_player_by_id(self, player_id: str) -> PlayerFrame | None:
        """Get player frame by ID, or None if not found."""
        for player in self.players:
            if player.player_id == player_id:
                return player
        return None
    
    def get_players_by_team(self, team: int) -> list[PlayerFrame]:
        """Get all players on a specific team (0 or 1)."""
        return [p for p in self.players if p.team == team]
