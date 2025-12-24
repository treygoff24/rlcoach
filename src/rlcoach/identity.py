# src/rlcoach/identity.py
"""Player identity resolution for matching "me" in replays."""

from __future__ import annotations

from typing import Any

from .config import IdentityConfig


class PlayerIdentityResolver:
    """Resolves player identity in replays based on config.

    Resolution order:
    1. Platform ID match (exact)
    2. Display name match (case-insensitive)
    3. No match -> return None (don't guess)
    """

    def __init__(self, identity_config: IdentityConfig):
        self._platform_ids = set(identity_config.platform_ids)
        self._display_names = set(n.lower() for n in identity_config.display_names)

    def is_me(self, player_id: str, display_name: str) -> bool:
        """Check if a player matches the configured identity."""
        if player_id in self._platform_ids:
            return True
        if display_name.lower() in self._display_names:
            return True
        return False

    def find_me(self, players: list[dict[str, Any]]) -> dict[str, Any] | None:
        """Find the player matching configured identity.

        Args:
            players: List of player dicts with 'player_id' and 'display_name'

        Returns:
            The matching player dict, or None if not found
        """
        # First pass: check platform IDs
        for player in players:
            pid = player.get("player_id", "")
            if pid in self._platform_ids:
                return player

        # Second pass: check display names (case-insensitive)
        for player in players:
            name = player.get("display_name", "")
            if name.lower() in self._display_names:
                return player

        # No match found
        return None
