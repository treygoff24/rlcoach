"""Core data types for the parser layer."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PlayerInfo:
    """Information about a player in the replay."""

    name: str
    platform_id: str | None = None
    team: int | None = None  # 0 or 1
    score: int = 0


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

    # Match results
    team0_score: int = 0
    team1_score: int = 0
    match_length: float = 0.0  # seconds

    # Players
    players: list[PlayerInfo] = field(default_factory=list)

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
