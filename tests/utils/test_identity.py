"""Tests for player identity helpers."""

from rlcoach.parser.types import PlayerInfo
from rlcoach.utils.identity import (
    build_alias_lookup,
    build_player_identities,
    sanitize_display_name,
    slugify_display_name,
)


def test_sanitize_display_name_trims_and_normalizes():
    assert sanitize_display_name("  Skillz.   ") == "Skillz."
    assert sanitize_display_name(None) == "Unknown"
    assert sanitize_display_name("\t\n ") == "Unknown"


def test_slugify_display_name_ascii_and_lowercase():
    assert slugify_display_name("Player One") == "player-one"
    assert slugify_display_name("Ångström") == "angstrom"
    assert slugify_display_name(None) == "unknown"


def test_build_player_identities_platform_precedence():
    players = [
        PlayerInfo(name="Alpha", platform_ids={"steam": "123"}, team=0),
        PlayerInfo(name="Bravo", platform_ids={"epic": "456"}, team=1),
    ]
    identities = build_player_identities(players)
    assert [p.canonical_id for p in identities] == ["steam:123", "epic:456"]
    assert identities[0].display_name == "Alpha"
    assert identities[1].team == "ORANGE"


def test_build_player_identities_slug_fallback_and_uniqueness():
    players = [
        PlayerInfo(name="Repeat", team=0),
        PlayerInfo(name="Repeat", team=1),
    ]
    identities = build_player_identities(players)
    assert identities[0].canonical_id == "slug:repeat"
    assert identities[1].canonical_id == "slug:repeat-2"


def test_build_alias_lookup_includes_header_and_frame_aliases():
    players = [
        PlayerInfo(name="Alpha", platform_ids={"steam": "123"}, team=0),
    ]
    identities = build_player_identities(players)
    aliases = build_alias_lookup(identities)
    canonical = identities[0].canonical_id
    assert aliases[canonical] == canonical
    assert aliases["player_0"] == canonical
    assert aliases["steam:123"] == canonical
