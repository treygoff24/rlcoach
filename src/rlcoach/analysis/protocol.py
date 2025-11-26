"""Protocol definition for analysis modules.

This module defines the standard interface that all analysis modules
should implement for consistency and interoperability.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from ..parser.types import Frame, Header


@runtime_checkable
class Analyzer(Protocol):
    """Protocol for analysis modules.

    All analysis modules should implement this interface to ensure
    consistent behavior and enable composition of analyzers.

    The analyze method receives normalized frames and optional context,
    returning a dictionary of analysis results suitable for JSON serialization.
    """

    def analyze(
        self,
        frames: list[Frame],
        events: dict[str, list[Any]] | None = None,
        header: Header | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Perform analysis on frame data.

        Args:
            frames: List of normalized Frame objects
            events: Optional dict of detected events (goals, touches, etc.)
            header: Optional Header with match metadata
            **kwargs: Additional analyzer-specific parameters

        Returns:
            Dict with analysis results. Should be JSON-serializable.
            Common keys include:
            - per_player: dict mapping player_id to player-specific metrics
            - per_team: dict with team-level aggregations
            - events: list of detected events/moments
        """
        ...


class AnalyzerConfig:
    """Base configuration for analysis modules.

    Subclass this to create analyzer-specific configuration.
    """

    def __init__(self, **kwargs: Any) -> None:
        """Initialize config with keyword arguments.

        Unknown kwargs are stored for flexibility.
        """
        for key, value in kwargs.items():
            setattr(self, key, value)

    def to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary."""
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}


def get_player_ids(frames: list[Frame]) -> set[str]:
    """Extract all unique player IDs from frames.

    Args:
        frames: List of Frame objects

    Returns:
        Set of unique player IDs
    """
    player_ids: set[str] = set()
    for frame in frames:
        for player in frame.players:
            player_ids.add(player.player_id)
    return player_ids


def get_player_teams(frames: list[Frame]) -> dict[str, int]:
    """Build a mapping of player IDs to team numbers.

    Args:
        frames: List of Frame objects

    Returns:
        Dict mapping player_id to team (0 or 1)
    """
    player_teams: dict[str, int] = {}
    for frame in frames:
        for player in frame.players:
            if player.player_id not in player_teams:
                player_teams[player.player_id] = player.team
    return player_teams
