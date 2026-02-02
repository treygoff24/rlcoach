# src/rlcoach/config.py
"""Configuration management for RLCoach."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import tomllib

from .metrics import VALID_PLAYLISTS, VALID_RANKS


class ConfigError(Exception):
    """Configuration error."""

    pass


# Valid platform prefixes
VALID_PLATFORMS = {"steam", "epic", "psn", "xbox", "switch"}
PLATFORM_ID_PATTERN = re.compile(r"^(steam|epic|psn|xbox|switch):[a-zA-Z0-9_-]+$")


@dataclass
class IdentityConfig:
    platform_ids: list[str] = field(default_factory=list)
    display_names: list[str] = field(default_factory=list)
    excluded_names: list[str] = field(default_factory=list)


@dataclass
class PathsConfig:
    watch_folder: Path
    data_dir: Path
    reports_dir: Path


@dataclass
class PreferencesConfig:
    primary_playlist: str = "DOUBLES"
    target_rank: str = "GC1"
    timezone: str | None = None


@dataclass
class TeammatesConfig:
    tagged: dict[str, str] = field(default_factory=dict)


@dataclass
class RLCoachConfig:
    identity: IdentityConfig
    paths: PathsConfig
    preferences: PreferencesConfig
    teammates: TeammatesConfig = field(default_factory=TeammatesConfig)

    @property
    def db_path(self) -> Path:
        return self.paths.data_dir / "rlcoach.db"

    def validate(self) -> None:
        """Validate configuration, raising ConfigError if invalid."""
        # Must have at least one identity method
        if not self.identity.platform_ids and not self.identity.display_names:
            raise ConfigError(
                "Configuration requires at least one platform_id or display_name "
                "in [identity]"
            )

        # Validate platform ID format
        for pid in self.identity.platform_ids:
            if not PLATFORM_ID_PATTERN.match(pid):
                raise ConfigError(
                    f"Invalid platform_id format '{pid}'. "
                    "Must be 'platform:id' where platform is one of: "
                    f"{', '.join(sorted(VALID_PLATFORMS))}"
                )

        # Validate target rank
        if self.preferences.target_rank not in VALID_RANKS:
            raise ConfigError(
                f"Invalid target_rank '{self.preferences.target_rank}'. "
                f"Must be one of: {', '.join(sorted(VALID_RANKS))}"
            )

        # Validate playlist
        if self.preferences.primary_playlist not in VALID_PLAYLISTS:
            raise ConfigError(
                f"Invalid primary_playlist '{self.preferences.primary_playlist}'. "
                f"Must be one of: {', '.join(sorted(VALID_PLAYLISTS))}"
            )

        # Validate timezone (IANA format)
        if self.preferences.timezone is not None:
            try:
                ZoneInfo(self.preferences.timezone)
            except ZoneInfoNotFoundError as e:
                raise ConfigError(
                    f"Invalid timezone '{self.preferences.timezone}'. "
                    "Must be a valid IANA timezone (e.g., 'America/Los_Angeles')"
                ) from e

        # Validate no overlap between display_names and excluded_names
        display_set = {n.casefold().strip() for n in self.identity.display_names}
        excluded_set = {n.casefold().strip() for n in self.identity.excluded_names}
        overlap = display_set & excluded_set
        if overlap:
            overlap_str = ", ".join(sorted(overlap))
            raise ConfigError(
                f"Name(s) cannot appear in both display_names and excluded_names: "
                f"{overlap_str}"
            )

    def get_timezone(self) -> ZoneInfo:
        """Get the configured timezone or system default."""
        if self.preferences.timezone:
            return ZoneInfo(self.preferences.timezone)
        # Use system timezone
        return datetime.now().astimezone().tzinfo  # type: ignore


def compute_play_date(utc_time: datetime, timezone_name: str | None) -> date:
    """Compute the local play date from a UTC timestamp.

    Args:
        utc_time: UTC timestamp of when the game was played
        timezone_name: IANA timezone name, or None for system timezone

    Returns:
        Local date in the configured timezone
    """
    if timezone_name:
        tz = ZoneInfo(timezone_name)
    else:
        # Use system timezone
        tz = datetime.now().astimezone().tzinfo

    local_time = utc_time.astimezone(tz)
    return local_time.date()


def load_config(config_path: Path) -> RLCoachConfig:
    """Load configuration from TOML file."""
    if not config_path.exists():
        raise ConfigError(f"Config file not found: {config_path}")

    with open(config_path, "rb") as f:
        data = tomllib.load(f)

    identity_data = data.get("identity", {})
    identity = IdentityConfig(
        platform_ids=identity_data.get("platform_ids", []),
        display_names=identity_data.get("display_names", []),
        excluded_names=identity_data.get("excluded_names", []),
    )

    paths_data = data.get("paths", {})
    paths = PathsConfig(
        watch_folder=Path(paths_data.get("watch_folder", "~/Replays")).expanduser(),
        data_dir=Path(paths_data.get("data_dir", "~/.rlcoach/data")).expanduser(),
        reports_dir=Path(
            paths_data.get("reports_dir", "~/.rlcoach/reports")
        ).expanduser(),
    )

    prefs_data = data.get("preferences", {})
    preferences = PreferencesConfig(
        primary_playlist=prefs_data.get("primary_playlist", "DOUBLES"),
        target_rank=prefs_data.get("target_rank", "GC1"),
        timezone=prefs_data.get("timezone"),
    )

    teammates_data = data.get("teammates", {})
    teammates = TeammatesConfig(
        tagged=teammates_data.get("tagged", {}),
    )

    return RLCoachConfig(
        identity=identity,
        paths=paths,
        preferences=preferences,
        teammates=teammates,
    )


def get_default_config_path() -> Path:
    """Get the default config file path."""
    return Path.home() / ".rlcoach" / "config.toml"
