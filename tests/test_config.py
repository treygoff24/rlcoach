# tests/test_config.py
import pytest
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from rlcoach.config import (
    RLCoachConfig, load_config, ConfigError,
    IdentityConfig, PathsConfig, PreferencesConfig,
    compute_play_date,
)


def test_load_config_from_valid_toml(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text('''
[identity]
platform_ids = ["steam:76561198012345678"]
display_names = ["TestPlayer"]

[paths]
watch_folder = "~/Replays"
data_dir = "~/.rlcoach/data"
reports_dir = "~/.rlcoach/reports"

[preferences]
primary_playlist = "DOUBLES"
target_rank = "GC1"
timezone = "America/Los_Angeles"
''')

    config = load_config(config_file)

    assert config.identity.platform_ids == ["steam:76561198012345678"]
    assert config.preferences.timezone == "America/Los_Angeles"


def test_compute_play_date_with_timezone():
    """play_date should be computed from UTC time + configured timezone."""
    # 2024-12-24 02:00 UTC = 2024-12-23 18:00 PST (still Dec 23 in LA)
    utc_time = datetime(2024, 12, 24, 2, 0, 0, tzinfo=timezone.utc)

    play_date = compute_play_date(utc_time, "America/Los_Angeles")

    assert play_date.isoformat() == "2024-12-23"


def test_compute_play_date_with_system_timezone():
    """Should use system timezone when not configured."""
    utc_time = datetime(2024, 12, 24, 12, 0, 0, tzinfo=timezone.utc)

    # None means use system timezone
    play_date = compute_play_date(utc_time, None)

    # Just verify it returns a date (can't assert specific value without knowing system tz)
    assert play_date is not None


def test_validate_timezone_invalid():
    """Invalid IANA timezone should fail validation."""
    config = RLCoachConfig(
        identity=IdentityConfig(platform_ids=["steam:123"]),
        paths=PathsConfig(
            watch_folder=Path("~/Replays"),
            data_dir=Path("~/.rlcoach/data"),
            reports_dir=Path("~/.rlcoach/reports"),
        ),
        preferences=PreferencesConfig(timezone="Invalid/Timezone"),
    )

    with pytest.raises(ConfigError, match="timezone"):
        config.validate()


def test_validate_platform_id_format():
    """Platform ID must be in format 'platform:id'."""
    config = RLCoachConfig(
        identity=IdentityConfig(platform_ids=["invalid_format"]),
        paths=PathsConfig(
            watch_folder=Path("~/Replays"),
            data_dir=Path("~/.rlcoach/data"),
            reports_dir=Path("~/.rlcoach/reports"),
        ),
        preferences=PreferencesConfig(),
    )

    with pytest.raises(ConfigError, match="platform"):
        config.validate()


def test_validate_excluded_names_overlap():
    """Names cannot appear in both display_names and excluded_names."""
    config = RLCoachConfig(
        identity=IdentityConfig(
            display_names=["MainAccount", "TrainingAccount"],
            excluded_names=["CasualAccount", "mainaccount"],  # Overlap (case-insensitive)
        ),
        paths=PathsConfig(
            watch_folder=Path("~/Replays"),
            data_dir=Path("~/.rlcoach/data"),
            reports_dir=Path("~/.rlcoach/reports"),
        ),
        preferences=PreferencesConfig(),
    )

    with pytest.raises(ConfigError, match="display_names and excluded_names"):
        config.validate()


def test_validate_excluded_names_no_overlap():
    """Non-overlapping names should pass validation."""
    config = RLCoachConfig(
        identity=IdentityConfig(
            display_names=["MainAccount"],
            excluded_names=["CasualAccount"],
        ),
        paths=PathsConfig(
            watch_folder=Path("~/Replays"),
            data_dir=Path("~/.rlcoach/data"),
            reports_dir=Path("~/.rlcoach/reports"),
        ),
        preferences=PreferencesConfig(),
    )

    # Should not raise
    config.validate()


def test_load_config_with_excluded_names(tmp_path):
    """Should load excluded_names from TOML config."""
    config_file = tmp_path / "config.toml"
    config_file.write_text('''
[identity]
platform_ids = ["steam:123"]
display_names = ["MainAccount"]
excluded_names = ["CasualAccount", "FamilyAccount"]

[paths]
watch_folder = "~/Replays"
data_dir = "~/.rlcoach/data"
reports_dir = "~/.rlcoach/reports"

[preferences]
primary_playlist = "DOUBLES"
target_rank = "GC1"
''')

    config = load_config(config_file)

    assert config.identity.excluded_names == ["CasualAccount", "FamilyAccount"]


def test_load_config_excluded_names_defaults_empty(tmp_path):
    """excluded_names should default to empty list if not specified."""
    config_file = tmp_path / "config.toml"
    config_file.write_text('''
[identity]
display_names = ["MainAccount"]

[paths]
watch_folder = "~/Replays"
data_dir = "~/.rlcoach/data"
reports_dir = "~/.rlcoach/reports"

[preferences]
primary_playlist = "DOUBLES"
target_rank = "GC1"
''')

    config = load_config(config_file)

    assert config.identity.excluded_names == []
