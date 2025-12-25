"""Player identity helpers for deterministic cross-source comparisons."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

from ..parser.types import PlayerInfo

_WHITESPACE_RE = re.compile(r"\s+")
_SLUG_RE = re.compile(r"[^a-z0-9]+")

_TEAM_NAMES = {
    0: "BLUE",
    1: "ORANGE",
}

_PLATFORM_PRIORITY = (
    "steam",
    "epic",
    "psn",
    "ps4",
    "ps5",
    "xbox",
    "xboxone",
    "xboxseries",
    "switch",
    "nintendo",
)


@dataclass(frozen=True)
class PlayerIdentity:
    """Resolved identity metadata for a replay participant."""

    canonical_id: str
    display_name: str
    team: str
    platform_ids: dict[str, str]
    slug: str
    header_index: int
    aliases: tuple[str, ...]


def sanitize_display_name(raw_name: str | None) -> str:
    """Trim whitespace and strip control characters from a display name."""
    if raw_name is None:
        return "Unknown"

    normalized = unicodedata.normalize("NFKC", str(raw_name))
    cleaned = _WHITESPACE_RE.sub(" ", normalized).strip()
    if not cleaned:
        return "Unknown"
    return cleaned


def slugify_display_name(raw_name: str | None) -> str:
    """Create a lowercase slug suitable for fallback identifiers."""
    cleaned = sanitize_display_name(raw_name).lower()
    cleaned_ascii = (
        unicodedata.normalize("NFKD", cleaned).encode("ascii", "ignore").decode("ascii")
    )
    slug = _SLUG_RE.sub("-", cleaned_ascii).strip("-")
    if not slug:
        return "player"
    return slug


def build_player_identities(players: Iterable[PlayerInfo]) -> list[PlayerIdentity]:
    """Resolve player identities with platform precedence and sanitized fallbacks."""
    identities: list[PlayerIdentity] = []
    used_ids: set[str] = set()

    for index, player in enumerate(players):
        platform_ids = _collect_platform_ids(player)
        display_name = sanitize_display_name(player.name)
        slug = slugify_display_name(player.name)
        candidate_id = _select_preferred_identifier(platform_ids, slug)
        canonical_id = _make_unique(candidate_id, used_ids)
        team = _resolve_team(player.team)
        aliases = _collect_aliases(canonical_id, slug, index, player, platform_ids)
        identities.append(
            PlayerIdentity(
                canonical_id=canonical_id,
                display_name=display_name,
                team=team,
                platform_ids=platform_ids,
                slug=slug,
                header_index=index,
                aliases=aliases,
            )
        )

    return identities


def build_alias_lookup(identities: Iterable[PlayerIdentity]) -> dict[str, str]:
    """Produce alias → canonical_id mapping for quick resolution."""
    alias_map: dict[str, str] = {}
    for identity in identities:
        for alias in identity.aliases:
            alias_map.setdefault(alias, identity.canonical_id)
    return alias_map


def _collect_platform_ids(player: PlayerInfo) -> dict[str, str]:
    """Gather and normalize platform identifiers from player metadata."""
    platform_ids: dict[str, str] = {}

    for key, value in (player.platform_ids or {}).items():
        if not value:
            continue
        norm_key = str(key).lower()
        norm_value = str(value).strip()
        if not norm_value:
            continue
        platform_ids[norm_key] = norm_value

    parsed = _parse_platform_id(player.platform_id)
    if parsed is not None:
        platform, value = parsed
        platform_ids.setdefault(platform, value)

    return platform_ids


def _parse_platform_id(value: str | None) -> tuple[str, str] | None:
    if not value:
        return None

    token = str(value).strip()
    if not token:
        return None

    for delimiter in (":", "|"):
        if delimiter in token:
            platform, platform_id = token.split(delimiter, 1)
            platform = platform.strip().lower()
            platform_id = platform_id.strip()
            if platform and platform_id:
                return platform, platform_id
            return None

    return None


def _select_preferred_identifier(platform_ids: dict[str, str], slug: str) -> str:
    for platform in _PLATFORM_PRIORITY:
        value = platform_ids.get(platform)
        if value:
            return f"{platform}:{value}"

    if platform_ids:
        platform, value = next(iter(sorted(platform_ids.items())))
        return f"{platform}:{value}"

    return f"slug:{slug}"


def _make_unique(candidate: str, used_ids: set[str]) -> str:
    if candidate not in used_ids:
        used_ids.add(candidate)
        return candidate

    suffix = 2
    while True:
        alternate = f"{candidate}-{suffix}"
        if alternate not in used_ids:
            used_ids.add(alternate)
            return alternate
        suffix += 1


def _resolve_team(team_value: int | None) -> str:
    if isinstance(team_value, int) and team_value in _TEAM_NAMES:
        return _TEAM_NAMES[team_value]
    return _TEAM_NAMES[0]


def _collect_aliases(
    canonical_id: str,
    slug: str,
    index: int,
    player: PlayerInfo,
    platform_ids: dict[str, str],
) -> tuple[str, ...]:
    aliases = {
        canonical_id,
        slug,
        f"slug:{slug}",
        f"player_{index}",
    }

    if player.platform_id:
        aliases.add(str(player.platform_id).strip())

    for platform, value in platform_ids.items():
        aliases.add(value)
        aliases.add(f"{platform}:{value}")

    return tuple(sorted(alias for alias in aliases if alias))


__all__ = [
    "PlayerIdentity",
    "build_alias_lookup",
    "build_player_identities",
    "sanitize_display_name",
    "slugify_display_name",
]
