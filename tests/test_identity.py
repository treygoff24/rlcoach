# tests/test_identity.py
import pytest
from rlcoach.identity import PlayerIdentityResolver
from rlcoach.config import IdentityConfig


def test_resolve_by_platform_id():
    """Should match by platform ID first."""
    config = IdentityConfig(
        platform_ids=["steam:123456"],
        display_names=["OldName"]
    )
    resolver = PlayerIdentityResolver(config)

    players = [
        {"player_id": "steam:123456", "display_name": "NewName"},
        {"player_id": "steam:999999", "display_name": "Opponent"},
    ]

    result = resolver.find_me(players)

    assert result is not None
    assert result["player_id"] == "steam:123456"


def test_resolve_by_display_name_fallback():
    """Should fallback to display name (case-insensitive) if no platform ID match."""
    config = IdentityConfig(
        platform_ids=["steam:000000"],  # Not in replay
        display_names=["TestPlayer"]
    )
    resolver = PlayerIdentityResolver(config)

    players = [
        {"player_id": "epic:abc123", "display_name": "TESTPLAYER"},  # Different case
        {"player_id": "steam:999999", "display_name": "Opponent"},
    ]

    result = resolver.find_me(players)

    assert result is not None
    assert result["player_id"] == "epic:abc123"


def test_resolve_returns_none_if_not_found():
    """Should return None if player not found (don't guess)."""
    config = IdentityConfig(
        platform_ids=["steam:123456"],
        display_names=["MyName"]
    )
    resolver = PlayerIdentityResolver(config)

    players = [
        {"player_id": "steam:999999", "display_name": "SomeoneElse"},
        {"player_id": "epic:abc123", "display_name": "AnotherPlayer"},
    ]

    result = resolver.find_me(players)

    assert result is None


def test_is_me_check():
    """Should correctly identify if a player is me."""
    config = IdentityConfig(
        platform_ids=["steam:123456"],
        display_names=["MyName"]
    )
    resolver = PlayerIdentityResolver(config)

    assert resolver.is_me("steam:123456", "AnyName") is True
    assert resolver.is_me("epic:999", "myname") is True  # Case insensitive
    assert resolver.is_me("steam:999", "SomeoneElse") is False


def test_should_exclude_matching_name():
    """Should exclude matching display names."""
    config = IdentityConfig(
        display_names=["MainAccount"],
        excluded_names=["CasualAccount"]
    )
    resolver = PlayerIdentityResolver(config)

    assert resolver.should_exclude("CasualAccount") is True
    assert resolver.should_exclude("MainAccount") is False
    assert resolver.should_exclude("SomeoneElse") is False


def test_should_exclude_case_insensitive():
    """Should exclude names case-insensitively using casefold."""
    config = IdentityConfig(
        display_names=["Main"],
        excluded_names=["CasualAccount"]
    )
    resolver = PlayerIdentityResolver(config)

    assert resolver.should_exclude("casualaccount") is True
    assert resolver.should_exclude("CASUALACCOUNT") is True
    assert resolver.should_exclude("CasualAccount") is True


def test_should_exclude_with_whitespace():
    """Should handle whitespace in excluded names."""
    config = IdentityConfig(
        display_names=["Main"],
        excluded_names=["  CasualAccount  "]
    )
    resolver = PlayerIdentityResolver(config)

    assert resolver.should_exclude("CasualAccount") is True
    assert resolver.should_exclude("  CasualAccount  ") is True


def test_should_exclude_empty_list():
    """Empty excluded_names should exclude nothing."""
    config = IdentityConfig(
        display_names=["MainAccount"],
        excluded_names=[]
    )
    resolver = PlayerIdentityResolver(config)

    assert resolver.should_exclude("MainAccount") is False
    assert resolver.should_exclude("AnyName") is False
