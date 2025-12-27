# RLCoach Full System Implementation Plan (Revised)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the complete RLCoach AI coaching system with SQLite storage, FastAPI backend, React GUI, and Claude Code coaching skill.

**Architecture:** The existing parser/analysis pipeline (ingest → parse → normalize → events → analyze → report) is preserved. We add: (1) Configuration layer for player identity and paths, (2) SQLite storage layer writing denormalized stats from JSON reports, (3) FastAPI REST API exposing all data to GUI and Claude, (4) React frontend for data exploration, (5) Claude Code skill for AI coaching conversations.

**Tech Stack:** Python 3.11+ (FastAPI, SQLAlchemy, Pydantic), React 18+ (TypeScript, Vite, TailwindCSS, Recharts), SQLite, Claude Code Skills.

**Existing Code Integration Points:**
- `src/rlcoach/cli.py` - Extend with new config/db/server commands (refactor to `main(argv)` pattern)
- `src/rlcoach/report.py` - `generate_report()` returns the JSON we'll store in SQLite
- `src/rlcoach/analysis/__init__.py` - `aggregate_analysis()` provides per-player metrics
- `src/rlcoach/ingest.py` - `ingest_replay()` provides file validation and SHA256

**Review Status:** Revised per GPT-5.2 Codex feedback (2025-12-23)

---

## Current Status

**Phase**: 0 - Not Started
**Working on**: Planning complete, awaiting execution
**Cross-agent reviews completed**: GPT-5.2 Codex review (verdict: revise → addressed)
**Blockers**: None
**Runtime**: 0m

---

## Phase 0: Environment & Dependencies

**Objective:** Set up Python 3.11+ environment, add all dependencies, refactor CLI for testability.

**Dependencies:** None (foundational)

**Estimated complexity:** Simple

### Task 0.1: Update pyproject.toml with Dependencies

**Files:**
- Modify: `pyproject.toml`

**Step 1: Read current pyproject.toml**

Run: `cat pyproject.toml`

**Step 2: Update pyproject.toml with new dependencies**

```toml
[project]
name = "rlcoach"
version = "0.1.0"
description = "All-local Rocket League replay analysis tool for coaching"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    "jsonschema>=4.0.0",
    # New dependencies for full system
    "fastapi>=0.104.0",
    "uvicorn[standard]>=0.24.0",
    "sqlalchemy>=2.0.0",
    "pydantic>=2.0.0",
    "pydantic-settings>=2.0.0",
    "python-multipart>=0.0.6",
    "httpx>=0.25.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "pytest-asyncio>=0.21.0",
    "black>=23.0.0",
    "ruff>=0.1.0",
    "maturin>=1.0.0",
]

[project.scripts]
rlcoach = "rlcoach.cli:main"
```

**Step 3: Install updated dependencies**

Run: `source .venv/bin/activate && pip install -e ".[dev]"`

**Step 4: Verify installation**

Run: `source .venv/bin/activate && python -c "import fastapi, sqlalchemy, pydantic; print('OK')"`
Expected: OK

**Step 5: Commit**

```bash
git add pyproject.toml
git commit -m "build: add FastAPI, SQLAlchemy, Pydantic dependencies"
```

### Task 0.2: Refactor CLI for Testability

**Files:**
- Modify: `src/rlcoach/cli.py`
- Test: `tests/test_cli_refactor.py`

**Step 1: Write the failing test for argv-based main**

```python
# tests/test_cli_refactor.py
import pytest
from rlcoach.cli import main


def test_main_with_argv_version(capsys):
    """main() should accept argv parameter for testability."""
    exit_code = main(["--version"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "rlcoach" in captured.out


def test_main_with_argv_help(capsys):
    """main() should show help with no args."""
    exit_code = main([])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "usage" in captured.out.lower() or "help" in captured.out.lower()
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/test_cli_refactor.py -v`
Expected: FAIL (main() doesn't accept argv parameter)

**Step 3: Refactor main() to accept argv parameter**

```python
# src/rlcoach/cli.py - modify main function signature

def main(argv: list[str] | None = None) -> int:
    """Main CLI entry point.

    Args:
        argv: Command line arguments. If None, uses sys.argv[1:].
    """
    parser = argparse.ArgumentParser(
        prog="rlcoach",
        description="All-local Rocket League replay analysis tool for coaching",
    )
    # ... rest of parser setup ...

    args = parser.parse_args(argv)  # Pass argv to parse_args

    # ... rest of function ...
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/test_cli_refactor.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/rlcoach/cli.py tests/test_cli_refactor.py
git commit -m "refactor(cli): accept argv parameter for testability"
```

---

## Phase 1: Metric Catalog & Configuration

**Objective:** Create single-source-of-truth metric catalog, config file parsing, validation, and CLI commands.

**Dependencies:** Phase 0

**Estimated complexity:** Moderate

### Task 1.1: Metric Catalog Module

**Files:**
- Create: `src/rlcoach/metrics.py`
- Test: `tests/test_metrics.py`

**Step 1: Write the failing test**

```python
# tests/test_metrics.py
import pytest
from rlcoach.metrics import (
    METRIC_CATALOG,
    get_metric,
    get_metrics_by_category,
    is_valid_metric,
    MetricDirection,
)


def test_metric_catalog_has_bcpm():
    """Catalog should contain boost metrics."""
    assert "bcpm" in METRIC_CATALOG
    metric = METRIC_CATALOG["bcpm"]
    assert metric.display_name == "Boost/Min"
    assert metric.direction == MetricDirection.HIGHER_BETTER


def test_get_metric_returns_none_for_invalid():
    assert get_metric("invalid_metric_xyz") is None


def test_is_valid_metric():
    assert is_valid_metric("bcpm") is True
    assert is_valid_metric("goals") is True
    assert is_valid_metric("fake_metric") is False


def test_get_metrics_by_category():
    boost_metrics = get_metrics_by_category("boost")
    assert "bcpm" in boost_metrics
    assert "avg_boost" in boost_metrics
    assert "goals" not in boost_metrics
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/test_metrics.py -v`
Expected: FAIL with "No module named 'rlcoach.metrics'"

**Step 3: Write metric catalog module**

```python
# src/rlcoach/metrics.py
"""Metric catalog - single source of truth for all tracked metrics.

This module defines all metrics used throughout RLCoach for:
- Benchmark validation
- Comparison calculations
- Pattern analysis
- Weakness detection
- API responses

IMPORTANT: Add new metrics here ONLY. All other modules import from this catalog.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal


class MetricDirection(Enum):
    """Direction for benchmark comparison."""
    HIGHER_BETTER = "higher"      # ↑ higher is better
    LOWER_BETTER = "lower"        # ↓ lower is better
    CONTEXT_DEPENDENT = "context" # ~ no benchmark comparison


MetricCategory = Literal[
    "fundamentals", "boost", "movement", "positioning",
    "challenges", "kickoffs", "mechanics", "recovery", "defense", "xg"
]


@dataclass(frozen=True)
class MetricDefinition:
    """Definition of a trackable metric."""
    key: str
    display_name: str
    unit: str
    direction: MetricDirection
    category: MetricCategory
    description: str
    valid_modes: tuple[str, ...] = ("1v1", "2v2", "3v3")
    db_column: str | None = None  # Override if different from key

    def __post_init__(self):
        # Set db_column to key if not specified
        if self.db_column is None:
            object.__setattr__(self, "db_column", self.key)


# ============================================================================
# METRIC CATALOG - Single Source of Truth
# ============================================================================

METRIC_CATALOG: dict[str, MetricDefinition] = {}

def _register(m: MetricDefinition) -> MetricDefinition:
    """Register a metric in the catalog."""
    METRIC_CATALOG[m.key] = m
    return m


# --- Fundamentals ---
_register(MetricDefinition(
    key="goals", display_name="Goals", unit="count",
    direction=MetricDirection.HIGHER_BETTER, category="fundamentals",
    description="Goals scored"
))
_register(MetricDefinition(
    key="assists", display_name="Assists", unit="count",
    direction=MetricDirection.HIGHER_BETTER, category="fundamentals",
    description="Passes leading to goals"
))
_register(MetricDefinition(
    key="saves", display_name="Saves", unit="count",
    direction=MetricDirection.HIGHER_BETTER, category="fundamentals",
    description="Shots blocked"
))
_register(MetricDefinition(
    key="shots", display_name="Shots", unit="count",
    direction=MetricDirection.HIGHER_BETTER, category="fundamentals",
    description="Shots on goal"
))
_register(MetricDefinition(
    key="shooting_pct", display_name="Shooting %", unit="percent",
    direction=MetricDirection.HIGHER_BETTER, category="fundamentals",
    description="goals / shots * 100"
))
_register(MetricDefinition(
    key="score", display_name="Score", unit="points",
    direction=MetricDirection.HIGHER_BETTER, category="fundamentals",
    description="In-game score"
))
_register(MetricDefinition(
    key="demos_inflicted", display_name="Demos", unit="count",
    direction=MetricDirection.HIGHER_BETTER, category="fundamentals",
    description="Demolitions made"
))
_register(MetricDefinition(
    key="demos_taken", display_name="Deaths", unit="count",
    direction=MetricDirection.LOWER_BETTER, category="fundamentals",
    description="Times demolished"
))

# --- Boost ---
_register(MetricDefinition(
    key="bcpm", display_name="Boost/Min", unit="boost/min",
    direction=MetricDirection.HIGHER_BETTER, category="boost",
    description="Boost collected per minute"
))
_register(MetricDefinition(
    key="avg_boost", display_name="Avg Boost", unit="0-100",
    direction=MetricDirection.LOWER_BETTER, category="boost",
    description="Average boost amount held (lower = spending efficiently)"
))
_register(MetricDefinition(
    key="time_zero_boost_s", display_name="Zero Boost Time", unit="seconds",
    direction=MetricDirection.LOWER_BETTER, category="boost",
    description="Time at 0 boost"
))
_register(MetricDefinition(
    key="time_full_boost_s", display_name="Full Boost Time", unit="seconds",
    direction=MetricDirection.LOWER_BETTER, category="boost",
    description="Time at 100 boost (should spend it)"
))
_register(MetricDefinition(
    key="boost_collected", display_name="Boost Collected", unit="total",
    direction=MetricDirection.HIGHER_BETTER, category="boost",
    description="Total boost picked up"
))
_register(MetricDefinition(
    key="boost_stolen", display_name="Boost Stolen", unit="total",
    direction=MetricDirection.HIGHER_BETTER, category="boost",
    description="Boost from opponent half"
))
_register(MetricDefinition(
    key="big_pads", display_name="Big Pads", unit="count",
    direction=MetricDirection.CONTEXT_DEPENDENT, category="boost",
    description="100-boost pads collected"
))
_register(MetricDefinition(
    key="small_pads", display_name="Small Pads", unit="count",
    direction=MetricDirection.HIGHER_BETTER, category="boost",
    description="12-boost pads collected"
))

# --- Movement ---
_register(MetricDefinition(
    key="avg_speed_kph", display_name="Avg Speed", unit="km/h",
    direction=MetricDirection.HIGHER_BETTER, category="movement",
    description="Average car speed"
))
_register(MetricDefinition(
    key="time_supersonic_s", display_name="Supersonic Time", unit="seconds",
    direction=MetricDirection.HIGHER_BETTER, category="movement",
    description="Time at supersonic (95%+ max)"
))
_register(MetricDefinition(
    key="time_slow_s", display_name="Slow Time", unit="seconds",
    direction=MetricDirection.LOWER_BETTER, category="movement",
    description="Time below 50% max speed"
))
_register(MetricDefinition(
    key="time_ground_s", display_name="Ground Time", unit="seconds",
    direction=MetricDirection.CONTEXT_DEPENDENT, category="movement",
    description="Time on ground"
))
_register(MetricDefinition(
    key="time_low_air_s", display_name="Low Air Time", unit="seconds",
    direction=MetricDirection.CONTEXT_DEPENDENT, category="movement",
    description="Time in air below goal height"
))
_register(MetricDefinition(
    key="time_high_air_s", display_name="High Air Time", unit="seconds",
    direction=MetricDirection.CONTEXT_DEPENDENT, category="movement",
    description="Time in air above goal height"
))

# --- Positioning ---
_register(MetricDefinition(
    key="time_offensive_third_s", display_name="Off. Third Time", unit="seconds",
    direction=MetricDirection.CONTEXT_DEPENDENT, category="positioning",
    description="Time in offensive third"
))
_register(MetricDefinition(
    key="time_middle_third_s", display_name="Mid Third Time", unit="seconds",
    direction=MetricDirection.CONTEXT_DEPENDENT, category="positioning",
    description="Time in middle third"
))
_register(MetricDefinition(
    key="time_defensive_third_s", display_name="Def. Third Time", unit="seconds",
    direction=MetricDirection.CONTEXT_DEPENDENT, category="positioning",
    description="Time in defensive third"
))
_register(MetricDefinition(
    key="behind_ball_pct", display_name="Behind Ball %", unit="percent",
    direction=MetricDirection.HIGHER_BETTER, category="positioning",
    description="Time positioned behind ball"
))
_register(MetricDefinition(
    key="avg_distance_to_ball_m", display_name="Avg Dist to Ball", unit="meters",
    direction=MetricDirection.CONTEXT_DEPENDENT, category="positioning",
    description="Average distance to ball"
))
_register(MetricDefinition(
    key="avg_distance_to_teammate_m", display_name="Avg Teammate Dist", unit="meters",
    direction=MetricDirection.CONTEXT_DEPENDENT, category="positioning",
    description="Avg distance to teammate", valid_modes=("2v2", "3v3")
))
_register(MetricDefinition(
    key="first_man_pct", display_name="1st Man %", unit="percent",
    direction=MetricDirection.CONTEXT_DEPENDENT, category="positioning",
    description="Time as player closest to ball"
))
_register(MetricDefinition(
    key="second_man_pct", display_name="2nd Man %", unit="percent",
    direction=MetricDirection.CONTEXT_DEPENDENT, category="positioning",
    description="Time as 2nd closest to ball", valid_modes=("2v2", "3v3")
))
_register(MetricDefinition(
    key="third_man_pct", display_name="3rd Man %", unit="percent",
    direction=MetricDirection.CONTEXT_DEPENDENT, category="positioning",
    description="Time as 3rd closest to ball", valid_modes=("3v3",)
))

# --- Challenges ---
_register(MetricDefinition(
    key="challenge_wins", display_name="50/50 Wins", unit="count",
    direction=MetricDirection.HIGHER_BETTER, category="challenges",
    description="Challenges won"
))
_register(MetricDefinition(
    key="challenge_losses", display_name="50/50 Losses", unit="count",
    direction=MetricDirection.LOWER_BETTER, category="challenges",
    description="Challenges lost"
))
_register(MetricDefinition(
    key="first_to_ball_pct", display_name="First to Ball %", unit="percent",
    direction=MetricDirection.HIGHER_BETTER, category="challenges",
    description="% challenges touched first"
))

# --- Kickoffs ---
_register(MetricDefinition(
    key="kickoffs_participated", display_name="Kickoffs", unit="count",
    direction=MetricDirection.CONTEXT_DEPENDENT, category="kickoffs",
    description="Kickoffs participated in"
))
_register(MetricDefinition(
    key="kickoff_first_touches", display_name="Kickoff First Touches", unit="count",
    direction=MetricDirection.CONTEXT_DEPENDENT, category="kickoffs",
    description="First touches on kickoff"
))

# --- Mechanics ---
_register(MetricDefinition(
    key="wavedash_count", display_name="Wavedashes", unit="count",
    direction=MetricDirection.HIGHER_BETTER, category="mechanics",
    description="Wavedash mechanics used"
))
_register(MetricDefinition(
    key="halfflip_count", display_name="Half-Flips", unit="count",
    direction=MetricDirection.HIGHER_BETTER, category="mechanics",
    description="Half-flip mechanics used"
))
_register(MetricDefinition(
    key="speedflip_count", display_name="Speedflips", unit="count",
    direction=MetricDirection.HIGHER_BETTER, category="mechanics",
    description="Speedflip mechanics used"
))
_register(MetricDefinition(
    key="aerial_count", display_name="Aerials", unit="count",
    direction=MetricDirection.HIGHER_BETTER, category="mechanics",
    description="Aerial touches"
))
_register(MetricDefinition(
    key="flip_cancel_count", display_name="Flip Cancels", unit="count",
    direction=MetricDirection.HIGHER_BETTER, category="mechanics",
    description="Flip cancel mechanics used"
))

# --- Recovery ---
_register(MetricDefinition(
    key="total_recoveries", display_name="Recoveries", unit="count",
    direction=MetricDirection.CONTEXT_DEPENDENT, category="recovery",
    description="Total recovery events"
))
_register(MetricDefinition(
    key="avg_recovery_momentum", display_name="Recovery Quality", unit="0-100",
    direction=MetricDirection.HIGHER_BETTER, category="recovery",
    description="Avg momentum after landings"
))

# --- Defense ---
_register(MetricDefinition(
    key="time_last_defender_s", display_name="Last Defender Time", unit="seconds",
    direction=MetricDirection.CONTEXT_DEPENDENT, category="defense",
    description="Time as last player back"
))
_register(MetricDefinition(
    key="time_shadow_defense_s", display_name="Shadow Time", unit="seconds",
    direction=MetricDirection.HIGHER_BETTER, category="defense",
    description="Time in shadow defense"
))

# --- xG ---
_register(MetricDefinition(
    key="total_xg", display_name="Expected Goals", unit="xG",
    direction=MetricDirection.HIGHER_BETTER, category="xg",
    description="Sum of shot xG values"
))


# ============================================================================
# Helper Functions
# ============================================================================

def get_metric(key: str) -> MetricDefinition | None:
    """Get a metric definition by key."""
    return METRIC_CATALOG.get(key)


def is_valid_metric(key: str) -> bool:
    """Check if a metric key exists in the catalog."""
    return key in METRIC_CATALOG


def get_metrics_by_category(category: MetricCategory) -> dict[str, MetricDefinition]:
    """Get all metrics in a category."""
    return {k: v for k, v in METRIC_CATALOG.items() if v.category == category}


def get_all_metric_keys() -> set[str]:
    """Get all valid metric keys."""
    return set(METRIC_CATALOG.keys())


def get_benchmarkable_metrics() -> dict[str, MetricDefinition]:
    """Get metrics that can be compared to benchmarks (not context-dependent)."""
    return {
        k: v for k, v in METRIC_CATALOG.items()
        if v.direction != MetricDirection.CONTEXT_DEPENDENT
    }


# Valid ranks and playlists (also single source of truth)
VALID_RANKS = frozenset({"C2", "C3", "GC1", "GC2", "GC3", "SSL"})
VALID_PLAYLISTS = frozenset({"DUEL", "DOUBLES", "STANDARD"})
```

**Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src pytest tests/test_metrics.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/rlcoach/metrics.py tests/test_metrics.py
git commit -m "feat(metrics): add single-source-of-truth metric catalog"
```

### Task 1.2: Config Model with Timezone Support

**Files:**
- Create: `src/rlcoach/config.py`
- Test: `tests/test_config.py`

**Step 1: Write the failing test for config loading with timezone**

```python
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
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/test_config.py -v`
Expected: FAIL with "No module named 'rlcoach.config'"

**Step 3: Write config module with timezone support**

```python
# src/rlcoach/config.py
"""Configuration management for RLCoach."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .metrics import VALID_RANKS, VALID_PLAYLISTS


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
                "Configuration requires at least one platform_id or display_name in [identity]"
            )

        # Validate platform ID format
        for pid in self.identity.platform_ids:
            if not PLATFORM_ID_PATTERN.match(pid):
                raise ConfigError(
                    f"Invalid platform_id format '{pid}'. "
                    f"Must be 'platform:id' where platform is one of: {', '.join(sorted(VALID_PLATFORMS))}"
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
            except ZoneInfoNotFoundError:
                raise ConfigError(
                    f"Invalid timezone '{self.preferences.timezone}'. "
                    "Must be a valid IANA timezone (e.g., 'America/Los_Angeles')"
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
    )

    paths_data = data.get("paths", {})
    paths = PathsConfig(
        watch_folder=Path(paths_data.get("watch_folder", "~/Replays")).expanduser(),
        data_dir=Path(paths_data.get("data_dir", "~/.rlcoach/data")).expanduser(),
        reports_dir=Path(paths_data.get("reports_dir", "~/.rlcoach/reports")).expanduser(),
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
```

**Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src pytest tests/test_config.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/rlcoach/config.py tests/test_config.py
git commit -m "feat(config): add config loading with timezone and validation"
```

### Task 1.3: Player Identity Resolution

**Files:**
- Create: `src/rlcoach/identity.py`
- Test: `tests/test_identity.py`

**Step 1: Write the failing test**

```python
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
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/test_identity.py -v`
Expected: FAIL

**Step 3: Write identity resolver**

```python
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
```

**Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src pytest tests/test_identity.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/rlcoach/identity.py tests/test_identity.py
git commit -m "feat(identity): add player identity resolution"
```

### Task 1.4: Config CLI Commands

**Files:**
- Modify: `src/rlcoach/cli.py`
- Create: `src/rlcoach/config_templates.py`
- Test: `tests/test_cli_config.py`

**Step 1: Write the failing test**

```python
# tests/test_cli_config.py
import pytest
from pathlib import Path
from unittest.mock import patch
from rlcoach.cli import main
from rlcoach.config import get_default_config_path


def test_config_init_creates_template(tmp_path, capsys):
    config_path = tmp_path / "config.toml"

    with patch("rlcoach.cli.get_default_config_path", return_value=config_path):
        exit_code = main(["config", "--init"])

    assert exit_code == 0
    assert config_path.exists()
    content = config_path.read_text()
    assert "[identity]" in content
    assert "[paths]" in content
    assert "[preferences]" in content
    assert "timezone" in content


def test_config_validate_valid(tmp_path, capsys):
    config_path = tmp_path / "config.toml"
    config_path.write_text('''
[identity]
platform_ids = ["steam:76561198012345678"]

[paths]
watch_folder = "~/Replays"
data_dir = "~/.rlcoach/data"
reports_dir = "~/.rlcoach/reports"

[preferences]
target_rank = "GC1"
timezone = "America/Los_Angeles"
''')

    with patch("rlcoach.cli.get_default_config_path", return_value=config_path):
        exit_code = main(["config", "--validate"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "valid" in captured.out.lower()


def test_config_validate_invalid_shows_error(tmp_path, capsys):
    config_path = tmp_path / "config.toml"
    config_path.write_text('''
[identity]
# No platform_ids or display_names!

[paths]
watch_folder = "~/Replays"
data_dir = "~/.rlcoach/data"
reports_dir = "~/.rlcoach/reports"
''')

    with patch("rlcoach.cli.get_default_config_path", return_value=config_path):
        exit_code = main(["config", "--validate"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "error" in captured.out.lower() or "identity" in captured.out.lower()


def test_config_missing_prevents_startup(tmp_path, capsys):
    """Missing config should give clear error message."""
    config_path = tmp_path / "nonexistent.toml"

    with patch("rlcoach.cli.get_default_config_path", return_value=config_path):
        exit_code = main(["config", "--validate"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "not found" in captured.out.lower() or "error" in captured.out.lower()
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/test_cli_config.py -v`
Expected: FAIL

**Step 3: Create config template**

```python
# src/rlcoach/config_templates.py
"""Configuration file templates."""

CONFIG_TEMPLATE = '''# RLCoach Configuration
# Edit this file with your player info before running RLCoach.

[identity]
# Primary player identification - at least one required
# Platform IDs are checked first, then display_names as fallback
# Format: "platform:id" where platform is steam, epic, psn, xbox, or switch
platform_ids = [
    # "steam:76561198012345678",
    # "epic:abc123def456"
]
# Fallback display names (case-insensitive, used if platform_id not found)
display_names = ["YourGamertag"]

[paths]
# Watch folder for incoming replays (Dropbox sync target)
watch_folder = "~/Dropbox/RocketLeague/Replays"
# Where to store processed data (SQLite database)
data_dir = "~/.rlcoach/data"
# Where to store JSON reports
reports_dir = "~/.rlcoach/reports"

[preferences]
# Primary playlist for comparisons (DOUBLES, STANDARD, DUEL)
primary_playlist = "DOUBLES"
# Target rank for benchmark comparisons (C2, C3, GC1, GC2, GC3, SSL)
target_rank = "GC1"
# Timezone for day boundary calculation (IANA format)
# Uses system timezone if not set
# timezone = "America/Los_Angeles"

[teammates]
# Tagged teammates for tracking (display_name = "optional notes")
[teammates.tagged]
# "DuoPartnerName" = "Main 2s partner"
'''
```

**Step 4: Add config subcommand to CLI**

```python
# src/rlcoach/cli.py - add these imports and handler

from .config import load_config, get_default_config_path, ConfigError
from .config_templates import CONFIG_TEMPLATE


def handle_config_command(args) -> int:
    """Handle the config subcommand."""
    config_path = get_default_config_path()

    if args.init:
        if config_path.exists() and not args.force:
            print(f"Config already exists at {config_path}")
            print("Use --force to overwrite")
            return 1

        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(CONFIG_TEMPLATE)
        print(f"Created config template at {config_path}")
        print("Edit this file with your player info before running RLCoach.")
        return 0

    if args.validate:
        try:
            config = load_config(config_path)
            config.validate()
            print(f"Configuration is valid: {config_path}")
            print(f"  Platform IDs: {len(config.identity.platform_ids)}")
            print(f"  Display names: {len(config.identity.display_names)}")
            print(f"  Target rank: {config.preferences.target_rank}")
            print(f"  Timezone: {config.preferences.timezone or '(system default)'}")
            return 0
        except ConfigError as e:
            print(f"Configuration error: {e}")
            return 1
        except FileNotFoundError:
            print(f"Config file not found: {config_path}")
            print(f"Run 'rlcoach config --init' to create one.")
            return 1
        except Exception as e:
            print(f"Error loading config: {e}")
            return 1

    if args.show:
        try:
            print(config_path.read_text())
            return 0
        except FileNotFoundError:
            print(f"Config file not found: {config_path}")
            return 1

    print("Use --init, --validate, or --show")
    return 1


# Add to main() subparsers:
config_parser = subparsers.add_parser("config", help="Manage RLCoach configuration")
config_parser.add_argument("--init", action="store_true", help="Create template config file")
config_parser.add_argument("--validate", action="store_true", help="Validate current config")
config_parser.add_argument("--show", action="store_true", help="Display current config")
config_parser.add_argument("--force", action="store_true", help="Force overwrite existing config")

# Add to routing in main():
elif args.command == "config":
    return handle_config_command(args)
```

**Step 5: Run tests to verify they pass**

Run: `PYTHONPATH=src pytest tests/test_cli_config.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/rlcoach/cli.py src/rlcoach/config_templates.py tests/test_cli_config.py
git commit -m "feat(cli): add config --init, --validate, --show commands"
```

---

## Phase 2: Database Schema and Models

**Objective:** Create SQLite schema with SQLAlchemy models, proper datetime handling, and all indexes.

**Dependencies:** Phase 1 (config provides db_path)

**Estimated complexity:** Moderate

### Task 2.1: SQLAlchemy Models - All Tables

**Files:**
- Create: `src/rlcoach/db/__init__.py`
- Create: `src/rlcoach/db/models.py`
- Test: `tests/db/test_models.py`

**Step 1: Write the failing test**

```python
# tests/db/test_models.py
import pytest
from datetime import datetime, timezone, date
from pathlib import Path
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from rlcoach.db.models import Base, Replay, Player, PlayerGameStats, DailyStats, Benchmark


def test_create_tables(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)

    assert db_path.exists()

    inspector = inspect(engine)
    tables = inspector.get_table_names()
    assert "replays" in tables
    assert "players" in tables
    assert "player_game_stats" in tables
    assert "daily_stats" in tables
    assert "benchmarks" in tables


def test_insert_replay_with_utc_datetime(tmp_path):
    """Replay should use timezone-aware UTC datetime."""
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        # First create the player
        player = Player(
            player_id="steam:123",
            display_name="TestPlayer",
            platform="steam",
            is_me=True,
        )
        session.add(player)
        session.flush()

        replay = Replay(
            replay_id="abc123",
            source_file="/path/to/replay.replay",
            file_hash="sha256hash",
            played_at_utc=datetime.now(timezone.utc),  # Must be UTC aware
            play_date=date(2024, 12, 23),
            map="DFH Stadium",
            playlist="DOUBLES",
            team_size=2,
            duration_seconds=312.5,
            my_player_id="steam:123",
            my_team="BLUE",
            my_score=3,
            opponent_score=1,
            result="WIN",
            json_report_path="/path/to/report.json",
        )
        session.add(replay)
        session.commit()

        fetched = session.get(Replay, "abc123")
        assert fetched is not None
        assert fetched.result == "WIN"
        assert fetched.play_date == date(2024, 12, 23)


def test_indexes_exist(tmp_path):
    """Verify performance indexes are created."""
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)

    inspector = inspect(engine)

    # Check replays indexes
    replay_indexes = {idx["name"] for idx in inspector.get_indexes("replays")}
    assert "ix_replays_play_date" in replay_indexes
    assert "ix_replays_playlist" in replay_indexes

    # Check player_game_stats indexes
    pgs_indexes = {idx["name"] for idx in inspector.get_indexes("player_game_stats")}
    assert "ix_player_game_stats_is_me" in pgs_indexes
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/db/test_models.py -v`
Expected: FAIL

**Step 3: Write SQLAlchemy models**

```python
# src/rlcoach/db/__init__.py
"""Database module for RLCoach."""

from .models import Base, Replay, Player, PlayerGameStats, DailyStats, Benchmark
from .session import init_db, get_session, create_session

__all__ = [
    "Base", "Replay", "Player", "PlayerGameStats", "DailyStats", "Benchmark",
    "init_db", "get_session", "create_session",
]
```

```python
# src/rlcoach/db/models.py
"""SQLAlchemy models for RLCoach database.

IMPORTANT: All datetime fields store UTC. Use datetime.now(timezone.utc).
The play_date field is computed from played_at_utc + configured timezone.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Float, ForeignKey, Index, Integer,
    String, Text, UniqueConstraint, create_engine
)
from sqlalchemy.orm import DeclarativeBase, relationship


def _utc_now() -> datetime:
    """Get current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Replay(Base):
    __tablename__ = "replays"

    replay_id = Column(String, primary_key=True)
    source_file = Column(String, nullable=False)
    file_hash = Column(String, nullable=False, index=True)  # For dedup
    ingested_at = Column(DateTime(timezone=True), default=_utc_now)
    played_at_utc = Column(DateTime(timezone=True), nullable=False)
    play_date = Column(Date, nullable=False, index=True)  # Local date from timezone
    map = Column(String, nullable=False)
    playlist = Column(String, nullable=False, index=True)
    team_size = Column(Integer, nullable=False)
    duration_seconds = Column(Float, nullable=False)
    overtime = Column(Boolean, default=False)
    my_player_id = Column(String, ForeignKey("players.player_id"), nullable=False)
    my_team = Column(String, nullable=False)
    my_score = Column(Integer, nullable=False)
    opponent_score = Column(Integer, nullable=False)
    result = Column(String, nullable=False, index=True)
    json_report_path = Column(String, nullable=False)

    player_stats = relationship("PlayerGameStats", back_populates="replay", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_replays_play_date", play_date.desc()),
        Index("ix_replays_playlist", playlist),
        Index("ix_replays_result", result),
    )


class Player(Base):
    __tablename__ = "players"

    player_id = Column(String, primary_key=True)
    display_name = Column(String, nullable=False)
    platform = Column(String)
    is_me = Column(Boolean, default=False, index=True)
    is_tagged_teammate = Column(Boolean, default=False)
    teammate_notes = Column(Text)
    first_seen_utc = Column(DateTime(timezone=True), default=_utc_now)
    last_seen_utc = Column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now)
    games_with_me = Column(Integer, default=0)


class PlayerGameStats(Base):
    __tablename__ = "player_game_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    replay_id = Column(String, ForeignKey("replays.replay_id", ondelete="CASCADE"), nullable=False)
    player_id = Column(String, ForeignKey("players.player_id"), nullable=False)
    team = Column(String, nullable=False)
    is_me = Column(Boolean, default=False, index=True)
    is_teammate = Column(Boolean, default=False)
    is_opponent = Column(Boolean, default=False)

    # Fundamentals
    goals = Column(Integer, default=0)
    assists = Column(Integer, default=0)
    saves = Column(Integer, default=0)
    shots = Column(Integer, default=0)
    shooting_pct = Column(Float)
    score = Column(Integer, default=0)
    demos_inflicted = Column(Integer, default=0)
    demos_taken = Column(Integer, default=0)

    # Boost
    bcpm = Column(Float)
    avg_boost = Column(Float)
    time_zero_boost_s = Column(Float)
    time_full_boost_s = Column(Float)
    boost_collected = Column(Float)
    boost_stolen = Column(Float)
    big_pads = Column(Integer)
    small_pads = Column(Integer)

    # Movement
    avg_speed_kph = Column(Float)
    time_supersonic_s = Column(Float)
    time_slow_s = Column(Float)
    time_ground_s = Column(Float)
    time_low_air_s = Column(Float)
    time_high_air_s = Column(Float)

    # Positioning
    time_offensive_third_s = Column(Float)
    time_middle_third_s = Column(Float)
    time_defensive_third_s = Column(Float)
    behind_ball_pct = Column(Float)
    avg_distance_to_ball_m = Column(Float)
    avg_distance_to_teammate_m = Column(Float)
    first_man_pct = Column(Float)
    second_man_pct = Column(Float)
    third_man_pct = Column(Float)

    # Challenges
    challenge_wins = Column(Integer)
    challenge_losses = Column(Integer)
    challenge_neutral = Column(Integer)
    first_to_ball_pct = Column(Float)

    # Kickoffs
    kickoffs_participated = Column(Integer)
    kickoff_first_touches = Column(Integer)

    # Mechanics
    wavedash_count = Column(Integer)
    halfflip_count = Column(Integer)
    speedflip_count = Column(Integer)
    aerial_count = Column(Integer)
    flip_cancel_count = Column(Integer)

    # Recovery
    total_recoveries = Column(Integer)
    avg_recovery_momentum = Column(Float)

    # Defense
    time_last_defender_s = Column(Float)
    time_shadow_defense_s = Column(Float)

    # xG
    total_xg = Column(Float)
    shots_xg_list = Column(Text)  # JSON array

    __table_args__ = (
        UniqueConstraint("replay_id", "player_id", name="uq_replay_player"),
        Index("ix_player_game_stats_replay", "replay_id"),
        Index("ix_player_game_stats_player", "player_id"),
        Index("ix_player_game_stats_is_me", "is_me", sqlite_where=is_me == True),
    )

    replay = relationship("Replay", back_populates="player_stats")


class DailyStats(Base):
    __tablename__ = "daily_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    play_date = Column(Date, nullable=False)
    playlist = Column(String, nullable=False)
    games_played = Column(Integer, default=0)
    wins = Column(Integer, default=0)
    losses = Column(Integer, default=0)
    draws = Column(Integer, default=0)
    win_rate = Column(Float)

    # Averaged stats
    avg_goals = Column(Float)
    avg_assists = Column(Float)
    avg_saves = Column(Float)
    avg_shots = Column(Float)
    avg_shooting_pct = Column(Float)
    avg_bcpm = Column(Float)
    avg_boost = Column(Float)
    avg_speed_kph = Column(Float)
    avg_supersonic_pct = Column(Float)
    avg_behind_ball_pct = Column(Float)
    avg_first_man_pct = Column(Float)
    avg_challenge_win_pct = Column(Float)

    updated_at = Column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now)

    __table_args__ = (
        UniqueConstraint("play_date", "playlist", name="uq_daily_playlist"),
        Index("ix_daily_stats_lookup", play_date.desc(), "playlist"),
    )


class Benchmark(Base):
    __tablename__ = "benchmarks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    metric = Column(String, nullable=False)
    playlist = Column(String, nullable=False)
    rank_tier = Column(String, nullable=False)
    median_value = Column(Float, nullable=False)
    p25_value = Column(Float)
    p75_value = Column(Float)
    elite_threshold = Column(Float)
    source = Column(String, nullable=False)
    source_date = Column(Date)
    notes = Column(Text)
    imported_at = Column(DateTime(timezone=True), default=_utc_now)

    __table_args__ = (
        UniqueConstraint("metric", "playlist", "rank_tier", name="uq_benchmark"),
        Index("ix_benchmarks_lookup", "metric", "playlist", "rank_tier"),
    )
```

**Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src pytest tests/db/test_models.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/rlcoach/db/ tests/db/
git commit -m "feat(db): add SQLAlchemy models with proper UTC datetime handling"
```

### Task 2.2: Database Session Factory

**Files:**
- Create: `src/rlcoach/db/session.py`
- Test: `tests/db/test_session.py`

**Step 1: Write the failing test**

```python
# tests/db/test_session.py
import pytest
from pathlib import Path
from sqlalchemy import inspect
from rlcoach.db.session import init_db, create_session, reset_engine


@pytest.fixture(autouse=True)
def reset_db():
    """Reset global engine between tests."""
    yield
    reset_engine()


def test_init_db_creates_tables(tmp_path):
    db_path = tmp_path / "test.db"
    engine = init_db(db_path)

    assert db_path.exists()

    inspector = inspect(engine)
    tables = inspector.get_table_names()
    assert "replays" in tables
    assert "benchmarks" in tables


def test_create_session_works_after_init(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)

    session = create_session()
    assert session is not None
    session.close()


def test_create_session_fails_without_init():
    with pytest.raises(RuntimeError, match="not initialized"):
        create_session()
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/db/test_session.py -v`
Expected: FAIL

**Step 3: Write session factory**

```python
# src/rlcoach/db/session.py
"""Database session management."""

from __future__ import annotations

from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base


_engine: Engine | None = None
_SessionFactory: sessionmaker | None = None


def get_engine() -> Engine:
    """Get the database engine (must call init_db first)."""
    if _engine is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _engine


def init_db(db_path: Path) -> Engine:
    """Initialize the database, creating tables if needed.

    Args:
        db_path: Path to SQLite database file

    Returns:
        SQLAlchemy engine
    """
    global _engine, _SessionFactory

    db_path.parent.mkdir(parents=True, exist_ok=True)

    _engine = create_engine(
        f"sqlite:///{db_path}",
        echo=False,
        # SQLite-specific optimizations
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(_engine)

    _SessionFactory = sessionmaker(bind=_engine, expire_on_commit=False)

    return _engine


def reset_engine() -> None:
    """Reset the global engine (for testing)."""
    global _engine, _SessionFactory
    if _engine:
        _engine.dispose()
    _engine = None
    _SessionFactory = None


def get_session() -> Generator[Session, None, None]:
    """Get a database session (for use with FastAPI Depends)."""
    if _SessionFactory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")

    session = _SessionFactory()
    try:
        yield session
    finally:
        session.close()


def create_session() -> Session:
    """Create a database session directly (for scripts/CLI).

    Remember to close the session when done!
    """
    if _SessionFactory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _SessionFactory()
```

**Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src pytest tests/db/test_session.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/rlcoach/db/session.py tests/db/test_session.py
git commit -m "feat(db): add session factory with init_db"
```

---

## Phase 3: Benchmark Import

**Objective:** Import benchmark data using the metric catalog for validation.

**Dependencies:** Phase 2 (database), Phase 1 (metric catalog)

**Estimated complexity:** Moderate

### Task 3.1: Benchmark Import Logic (Using Metric Catalog)

**Files:**
- Create: `src/rlcoach/benchmarks.py`
- Test: `tests/test_benchmarks.py`

**Step 1: Write the failing test**

```python
# tests/test_benchmarks.py
import pytest
import json
from pathlib import Path
from rlcoach.benchmarks import import_benchmarks, validate_benchmark_data, BenchmarkValidationError
from rlcoach.db.session import init_db, create_session, reset_engine
from rlcoach.db.models import Benchmark


@pytest.fixture(autouse=True)
def reset_db():
    yield
    reset_engine()


def test_validate_uses_metric_catalog():
    """Validation should use the metric catalog, not a hardcoded list."""
    from rlcoach.metrics import METRIC_CATALOG

    data = {
        "metadata": {"source": "test"},
        "benchmarks": [
            {
                "metric": "bcpm",  # Valid metric from catalog
                "playlist": "DOUBLES",
                "rank_tier": "GC1",
                "median": 380
            }
        ]
    }
    errors = validate_benchmark_data(data)
    assert errors == []


def test_validate_rejects_invalid_metric():
    """Should reject metrics not in the catalog."""
    data = {
        "metadata": {"source": "test"},
        "benchmarks": [
            {
                "metric": "made_up_metric",
                "playlist": "DOUBLES",
                "rank_tier": "GC1",
                "median": 100
            }
        ]
    }
    errors = validate_benchmark_data(data)
    assert any("metric" in e.lower() for e in errors)


def test_import_benchmarks_success(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)

    benchmark_file = tmp_path / "benchmarks.json"
    benchmark_file.write_text(json.dumps({
        "metadata": {
            "source": "Test Source",
            "collected_date": "2024-12-01",
            "notes": "Test data"
        },
        "benchmarks": [
            {
                "metric": "bcpm",
                "playlist": "DOUBLES",
                "rank_tier": "GC1",
                "median": 380,
                "p25": 330,
                "p75": 420,
                "elite": 420
            },
            {
                "metric": "avg_boost",
                "playlist": "DOUBLES",
                "rank_tier": "GC1",
                "median": 30,
                "p25": 25,
                "p75": 34,
                "elite": 20
            }
        ]
    }))

    count = import_benchmarks(benchmark_file)
    assert count == 2

    session = create_session()
    try:
        benchmark = session.query(Benchmark).filter_by(metric="bcpm", rank_tier="GC1").first()
        assert benchmark is not None
        assert benchmark.median_value == 380
        assert benchmark.source == "Test Source"
    finally:
        session.close()


def test_import_benchmarks_upserts(tmp_path):
    """Re-importing should update existing records."""
    db_path = tmp_path / "test.db"
    init_db(db_path)

    benchmark_file = tmp_path / "benchmarks.json"

    # First import
    benchmark_file.write_text(json.dumps({
        "metadata": {"source": "v1"},
        "benchmarks": [{"metric": "bcpm", "playlist": "DOUBLES", "rank_tier": "GC1", "median": 100}]
    }))
    import_benchmarks(benchmark_file)

    # Second import with updated value
    benchmark_file.write_text(json.dumps({
        "metadata": {"source": "v2"},
        "benchmarks": [{"metric": "bcpm", "playlist": "DOUBLES", "rank_tier": "GC1", "median": 200}]
    }))
    import_benchmarks(benchmark_file)

    session = create_session()
    try:
        benchmarks = session.query(Benchmark).filter_by(metric="bcpm", rank_tier="GC1").all()
        assert len(benchmarks) == 1
        assert benchmarks[0].median_value == 200
        assert benchmarks[0].source == "v2"
    finally:
        session.close()
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/test_benchmarks.py -v`
Expected: FAIL

**Step 3: Write benchmark import using metric catalog**

```python
# src/rlcoach/benchmarks.py
"""Benchmark data import and validation.

Uses the metric catalog as single source of truth for valid metrics.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .db.session import create_session
from .db.models import Benchmark
from .metrics import is_valid_metric, VALID_RANKS, VALID_PLAYLISTS


class BenchmarkValidationError(Exception):
    """Benchmark validation error."""
    pass


def validate_benchmark_data(data: dict[str, Any]) -> list[str]:
    """Validate benchmark import data structure.

    Uses metric catalog for validation.

    Returns list of validation errors (empty if valid).
    """
    errors = []

    if "benchmarks" not in data:
        errors.append("Missing 'benchmarks' key")
        return errors

    for i, b in enumerate(data["benchmarks"]):
        prefix = f"benchmarks[{i}]"

        if "metric" not in b:
            errors.append(f"{prefix}: Missing 'metric'")
        elif not is_valid_metric(b["metric"]):
            errors.append(f"{prefix}: Invalid metric '{b['metric']}' (not in metric catalog)")

        if "playlist" not in b:
            errors.append(f"{prefix}: Missing 'playlist'")
        elif b["playlist"] not in VALID_PLAYLISTS:
            errors.append(f"{prefix}: Invalid playlist '{b['playlist']}'")

        if "rank_tier" not in b:
            errors.append(f"{prefix}: Missing 'rank_tier'")
        elif b["rank_tier"] not in VALID_RANKS:
            errors.append(f"{prefix}: Invalid rank_tier '{b['rank_tier']}'")

        if "median" not in b:
            errors.append(f"{prefix}: Missing 'median'")

    return errors


def import_benchmarks(file_path: Path, replace: bool = False) -> int:
    """Import benchmarks from JSON file.

    Args:
        file_path: Path to benchmark JSON file
        replace: If True, delete ALL existing benchmarks before import

    Returns:
        Number of benchmarks imported/updated
    """
    with open(file_path) as f:
        data = json.load(f)

    errors = validate_benchmark_data(data)
    if errors:
        raise BenchmarkValidationError(f"Validation errors:\n" + "\n".join(f"  - {e}" for e in errors))

    metadata = data.get("metadata", {})
    source = metadata.get("source", "unknown")
    source_date_str = metadata.get("collected_date")
    source_date = None
    if source_date_str:
        source_date = date.fromisoformat(source_date_str)
    notes = metadata.get("notes")

    session = create_session()
    try:
        if replace:
            session.query(Benchmark).delete()

        count = 0
        for b in data["benchmarks"]:
            # Check for existing (upsert)
            existing = session.query(Benchmark).filter_by(
                metric=b["metric"],
                playlist=b["playlist"],
                rank_tier=b["rank_tier"],
            ).first()

            if existing:
                existing.median_value = b["median"]
                existing.p25_value = b.get("p25")
                existing.p75_value = b.get("p75")
                existing.elite_threshold = b.get("elite")
                existing.source = source
                existing.source_date = source_date
                existing.notes = b.get("notes") or notes
                existing.imported_at = datetime.now(timezone.utc)
            else:
                benchmark = Benchmark(
                    metric=b["metric"],
                    playlist=b["playlist"],
                    rank_tier=b["rank_tier"],
                    median_value=b["median"],
                    p25_value=b.get("p25"),
                    p75_value=b.get("p75"),
                    elite_threshold=b.get("elite"),
                    source=source,
                    source_date=source_date,
                    notes=b.get("notes") or notes,
                )
                session.add(benchmark)

            count += 1

        session.commit()
        return count

    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

**Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src pytest tests/test_benchmarks.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/rlcoach/benchmarks.py tests/test_benchmarks.py
git commit -m "feat(benchmarks): add import with metric catalog validation"
```

### Task 3.2: Create Benchmark JSON from Research Data

**Files:**
- Create: `data/benchmarks/gc_benchmarks_2v2.json`

This task converts the data from `RANK_BENCHMARKS_MASTER.md` into the import format.

**Step 1: Create the benchmark JSON file**

Create `data/benchmarks/gc_benchmarks_2v2.json` with all metrics from the research document. (Full JSON provided in original plan - keeping reference here for brevity. Should include all metrics: bcpm, avg_boost, time_supersonic_s, behind_ball_pct, goals, saves, small_pads, avg_speed_kph, etc. for ranks C2 through SSL.)

**Step 2: Commit**

```bash
mkdir -p data/benchmarks
git add data/benchmarks/gc_benchmarks_2v2.json
git commit -m "data(benchmarks): add GC benchmark data for 2v2 from research"
```

### Task 3.3: Benchmark CLI Commands

**Files:**
- Modify: `src/rlcoach/cli.py`
- Test: `tests/test_cli_benchmarks.py`

(Same as original plan Task 3.3 - add benchmarks import/list commands to CLI)

---

## Phase 4: Report-to-Database Writer (Split into Tasks)

**Objective:** Transform JSON reports into SQLite records with proper identity resolution, timezone handling, and deduplication.

**Dependencies:** Phase 2 (database), Phase 1 (config, identity)

**Estimated complexity:** Complex (split into 4 tasks)

### Task 4.1: Upsert Players

**Files:**
- Create: `src/rlcoach/db/writer.py`
- Test: `tests/db/test_writer_players.py`

**Step 1: Write the failing test**

```python
# tests/db/test_writer_players.py
import pytest
from datetime import datetime, timezone
from rlcoach.db.writer import upsert_players
from rlcoach.db.session import init_db, create_session, reset_engine
from rlcoach.db.models import Player
from rlcoach.config import IdentityConfig


@pytest.fixture(autouse=True)
def reset_db():
    yield
    reset_engine()


def test_upsert_players_creates_new(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)

    identity = IdentityConfig(platform_ids=["steam:me123"])
    players = [
        {"player_id": "steam:me123", "display_name": "MePlayer", "team": "BLUE"},
        {"player_id": "steam:other456", "display_name": "OtherPlayer", "team": "ORANGE"},
    ]

    upsert_players(players, identity)

    session = create_session()
    try:
        me = session.get(Player, "steam:me123")
        assert me is not None
        assert me.is_me is True
        assert me.games_with_me == 0  # I don't count as game with myself

        other = session.get(Player, "steam:other456")
        assert other is not None
        assert other.is_me is False
        assert other.games_with_me == 1  # This player was in a game with me
    finally:
        session.close()


def test_upsert_players_updates_existing(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)

    identity = IdentityConfig(platform_ids=["steam:me123"])

    # First call
    upsert_players([
        {"player_id": "steam:other456", "display_name": "OldName", "team": "BLUE"},
    ], identity)

    # Second call with new name
    upsert_players([
        {"player_id": "steam:other456", "display_name": "NewName", "team": "BLUE"},
    ], identity)

    session = create_session()
    try:
        player = session.get(Player, "steam:other456")
        assert player.display_name == "NewName"
        assert player.games_with_me == 2  # Appeared in 2 games
    finally:
        session.close()
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/db/test_writer_players.py -v`
Expected: FAIL

**Step 3: Write upsert_players function**

```python
# src/rlcoach/db/writer.py
"""Transform JSON reports into database records."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .session import create_session
from .models import Player
from ..config import IdentityConfig
from ..identity import PlayerIdentityResolver


def upsert_players(
    players: list[dict[str, Any]],
    identity_config: IdentityConfig,
) -> None:
    """Create or update player records.

    Args:
        players: List of player dicts with 'player_id' and 'display_name'
        identity_config: Config for determining who is "me"
    """
    resolver = PlayerIdentityResolver(identity_config)

    session = create_session()
    try:
        for p in players:
            pid = p["player_id"]
            display_name = p["display_name"]
            is_me = resolver.is_me(pid, display_name)
            platform = pid.split(":")[0] if ":" in pid else None

            existing = session.get(Player, pid)

            if existing:
                # Update
                existing.display_name = display_name
                existing.last_seen_utc = datetime.now(timezone.utc)
                if not is_me:
                    existing.games_with_me = (existing.games_with_me or 0) + 1
            else:
                # Create
                player = Player(
                    player_id=pid,
                    display_name=display_name,
                    platform=platform,
                    is_me=is_me,
                    first_seen_utc=datetime.now(timezone.utc),
                    last_seen_utc=datetime.now(timezone.utc),
                    games_with_me=0 if is_me else 1,
                )
                session.add(player)

        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

**Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src pytest tests/db/test_writer_players.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/rlcoach/db/writer.py tests/db/test_writer_players.py
git commit -m "feat(db): add upsert_players for player registry"
```

### Task 4.2: Insert Replay Record

**Files:**
- Modify: `src/rlcoach/db/writer.py`
- Test: `tests/db/test_writer_replay.py`

**Step 1: Write the failing test**

```python
# tests/db/test_writer_replay.py
import pytest
from datetime import datetime, date, timezone
from pathlib import Path
from rlcoach.db.writer import insert_replay, ReplayExistsError
from rlcoach.db.session import init_db, create_session, reset_engine
from rlcoach.db.models import Replay, Player
from rlcoach.config import IdentityConfig, PathsConfig, PreferencesConfig, RLCoachConfig


@pytest.fixture(autouse=True)
def reset_db():
    yield
    reset_engine()


@pytest.fixture
def config():
    return RLCoachConfig(
        identity=IdentityConfig(platform_ids=["steam:me123"]),
        paths=PathsConfig(
            watch_folder=Path("~/Replays"),
            data_dir=Path("~/.rlcoach/data"),
            reports_dir=Path("~/.rlcoach/reports"),
        ),
        preferences=PreferencesConfig(timezone="America/Los_Angeles"),
    )


@pytest.fixture
def sample_report():
    return {
        "replay_id": "abc123hash",
        "source_file": "/path/to/replay.replay",
        "metadata": {
            "playlist": "DOUBLES",
            "map": "DFH Stadium",
            "team_size": 2,
            "duration_seconds": 312.5,
            "overtime": False,
            "started_at_utc": "2024-12-24T02:00:00Z",  # Dec 23 in LA time
        },
        "teams": {
            "blue": {"score": 3, "players": ["steam:me123"]},
            "orange": {"score": 1, "players": ["steam:opp456"]},
        },
        "players": [
            {"player_id": "steam:me123", "display_name": "MePlayer", "team": "BLUE"},
            {"player_id": "steam:opp456", "display_name": "Opponent", "team": "ORANGE"},
        ],
        "analysis": {"per_player": {}},
    }


def test_insert_replay_creates_record(tmp_path, config, sample_report):
    db_path = tmp_path / "test.db"
    init_db(db_path)

    # Pre-create player
    session = create_session()
    session.add(Player(player_id="steam:me123", display_name="Me", is_me=True))
    session.commit()
    session.close()

    replay_id = insert_replay(sample_report, "filehash123", config)

    assert replay_id == "abc123hash"

    session = create_session()
    try:
        replay = session.get(Replay, "abc123hash")
        assert replay is not None
        assert replay.result == "WIN"
        assert replay.my_team == "BLUE"
        # Timezone conversion: 2024-12-24 02:00 UTC = 2024-12-23 in LA
        assert replay.play_date == date(2024, 12, 23)
    finally:
        session.close()


def test_insert_replay_rejects_duplicate_replay_id(tmp_path, config, sample_report):
    db_path = tmp_path / "test.db"
    init_db(db_path)

    session = create_session()
    session.add(Player(player_id="steam:me123", display_name="Me", is_me=True))
    session.commit()
    session.close()

    insert_replay(sample_report, "filehash123", config)

    # Try to insert same replay_id
    with pytest.raises(ReplayExistsError, match="replay_id"):
        insert_replay(sample_report, "different_hash", config)


def test_insert_replay_rejects_duplicate_file_hash(tmp_path, config, sample_report):
    db_path = tmp_path / "test.db"
    init_db(db_path)

    session = create_session()
    session.add(Player(player_id="steam:me123", display_name="Me", is_me=True))
    session.commit()
    session.close()

    insert_replay(sample_report, "samehash", config)

    # Different replay_id but same file_hash
    sample_report["replay_id"] = "different_id"
    with pytest.raises(ReplayExistsError, match="file_hash"):
        insert_replay(sample_report, "samehash", config)
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/db/test_writer_replay.py -v`
Expected: FAIL

**Step 3: Write insert_replay function**

```python
# src/rlcoach/db/writer.py (add)

from .models import Replay
from ..config import RLCoachConfig, compute_play_date


class ReplayExistsError(Exception):
    """Raised when trying to insert a duplicate replay."""
    pass


class PlayerNotFoundError(Exception):
    """Raised when player identity cannot be resolved."""
    pass


def insert_replay(
    report: dict[str, Any],
    file_hash: str,
    config: RLCoachConfig,
) -> str:
    """Insert a replay record into the database.

    Args:
        report: Parsed JSON report from generate_report()
        file_hash: SHA256 hash of the replay file
        config: RLCoach configuration

    Returns:
        The replay_id

    Raises:
        ReplayExistsError: If replay_id or file_hash already exists
        PlayerNotFoundError: If player identity cannot be resolved
    """
    from ..identity import PlayerIdentityResolver

    replay_id = report["replay_id"]
    metadata = report["metadata"]
    teams = report["teams"]
    players = report["players"]

    session = create_session()
    try:
        # Check for duplicate replay_id
        if session.get(Replay, replay_id):
            raise ReplayExistsError(f"Replay with replay_id '{replay_id}' already exists")

        # Check for duplicate file_hash
        existing_hash = session.query(Replay).filter_by(file_hash=file_hash).first()
        if existing_hash:
            raise ReplayExistsError(f"Replay with file_hash '{file_hash}' already exists")

        # Find "me" in players
        resolver = PlayerIdentityResolver(config.identity)
        my_player = resolver.find_me(players)
        if not my_player:
            raise PlayerNotFoundError(
                f"Could not identify player in replay. "
                f"Config platform_ids: {config.identity.platform_ids}, "
                f"display_names: {config.identity.display_names}"
            )

        my_player_id = my_player["player_id"]
        my_team = my_player["team"]

        # Determine result
        my_score = teams["blue"]["score"] if my_team == "BLUE" else teams["orange"]["score"]
        opp_score = teams["orange"]["score"] if my_team == "BLUE" else teams["blue"]["score"]

        if my_score > opp_score:
            result = "WIN"
        elif my_score < opp_score:
            result = "LOSS"
        else:
            result = "DRAW"

        # Parse timestamp and compute play_date with timezone
        played_at_str = metadata.get("started_at_utc", "")
        if played_at_str:
            played_at_str = played_at_str.replace("Z", "+00:00")
            played_at_utc = datetime.fromisoformat(played_at_str)
        else:
            played_at_utc = datetime.now(timezone.utc)

        play_date = compute_play_date(played_at_utc, config.preferences.timezone)

        # Build json_report_path
        json_report_path = str(
            config.paths.reports_dir / play_date.isoformat() / f"{replay_id}.json"
        )

        replay = Replay(
            replay_id=replay_id,
            source_file=report.get("source_file", ""),
            file_hash=file_hash,
            played_at_utc=played_at_utc,
            play_date=play_date,
            map=metadata.get("map", "unknown"),
            playlist=metadata.get("playlist", "UNKNOWN"),
            team_size=metadata.get("team_size", 2),
            duration_seconds=metadata.get("duration_seconds", 0),
            overtime=metadata.get("overtime", False),
            my_player_id=my_player_id,
            my_team=my_team,
            my_score=my_score,
            opponent_score=opp_score,
            result=result,
            json_report_path=json_report_path,
        )
        session.add(replay)
        session.commit()

        return replay_id

    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

**Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src pytest tests/db/test_writer_replay.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/rlcoach/db/writer.py tests/db/test_writer_replay.py
git commit -m "feat(db): add insert_replay with deduplication and timezone"
```

### Task 4.3: Insert Player Stats

**Files:**
- Modify: `src/rlcoach/db/writer.py`
- Test: `tests/db/test_writer_stats.py`

(Similar pattern: extract stats from report analysis block, insert PlayerGameStats records)

### Task 4.4: Full Write Report Function

**Files:**
- Modify: `src/rlcoach/db/writer.py`
- Test: `tests/db/test_writer_full.py`

Combines upsert_players, insert_replay, insert_stats into a single write_report() function.

---

## Phase 5: Core Algorithms (Patterns, Weaknesses, Tendencies)

**Objective:** Implement the analysis algorithms BEFORE building API endpoints.

**Dependencies:** Phase 2 (database with data)

**Estimated complexity:** Complex

### Task 5.1: Win/Loss Pattern Analysis

**Files:**
- Create: `src/rlcoach/analysis/patterns.py`
- Test: `tests/analysis/test_patterns.py`

Implements the algorithm from SPEC.md section "Win/Loss Pattern Analysis":
- Compute win_avg, loss_avg, delta, effect_size (Cohen's d)
- Filter by significance thresholds
- Return significant patterns

### Task 5.2: Weakness Detection

**Files:**
- Create: `src/rlcoach/analysis/weaknesses.py`
- Test: `tests/analysis/test_weaknesses.py`

Implements the algorithm from SPEC.md section "Weakness Detection Algorithm":
- Compare my_averages against benchmarks
- Compute z-scores from percentiles
- Assign severity levels (critical, high, medium, low, strength)
- Incorporate pattern evidence

### Task 5.3: Teammate Tendency Analysis

**Files:**
- Create: `src/rlcoach/analysis/tendencies.py`
- Test: `tests/analysis/test_tendencies.py`

Implements tendency metrics and adaptation score from SPEC.md:
- aggression_score, challenge_rate, first_man_tendency
- boost_priority, mechanical_index, defensive_index
- compute_adaptation_score()

### Task 5.4: Daily Stats Aggregation

**Files:**
- Create: `src/rlcoach/db/aggregates.py`
- Test: `tests/db/test_aggregates.py`

Implements incremental daily_stats update after ingestion.

---

## Phase 6: Extended Ingestion Pipeline

**Objective:** Add watch folder service, file stability check, and integrated ingestion.

**Dependencies:** Phase 4 (writer), Phase 5 (daily aggregation)

**Estimated complexity:** Moderate

### Task 6.1: File Stability Check

Wait for file size to stabilize (no changes for 2 seconds) before processing.

### Task 6.2: Watch Folder Service

Monitor Dropbox-synced directory for new .replay files.

### Task 6.3: Integrated Ingestion Command

`rlcoach ingest --watch` that runs the full pipeline.

---

## Phases 7-17: API, Frontend, Skill

(Summarized - each has detailed tasks following the same TDD pattern)

### Phase 7: FastAPI Backend Foundation
- App setup with CORS, lifespan, database init
- Pydantic response models
- Health check endpoint
- Error handling middleware
- CLI `serve` command

### Phase 8: API Endpoints - Games & Replays
- GET /dashboard (with contract from SPEC.md)
- GET /games with filtering, pagination, sorting
- GET /replays/{id}
- GET /replays/{id}/events
- GET /replays/{id}/heatmaps
- GET /replays/{id}/full

### Phase 9: API Endpoints - Analysis
- GET /trends with 5-min cache TTL
- GET /benchmarks
- GET /compare
- GET /patterns (uses Phase 5 algorithms)
- GET /weaknesses (uses Phase 5 algorithms)

### Phase 10: API Endpoints - Players
- GET /players with filtering
- GET /players/{id} with tendencies (uses Phase 5)
- POST /players/{id}/tag

### Phase 11: React Frontend Foundation
- Vite + React + TypeScript setup
- TailwindCSS with dark theme
- React Router
- API client with React Query
- Layout with sidebar navigation
- Skeleton loading components
- Empty state components

### Phase 12: Dashboard View
- Quick stats cards
- Recent games list
- Trend sparklines (Recharts)
- Focus areas summary
- vs GC snapshot

### Phase 13: Day & Games Views
- Date picker with timezone
- Games list with expandable cards
- Day summary stats
- Filter state persistence

### Phase 14: Trends View
- Metric dropdown (grouped by category from catalog)
- Recharts line chart
- Benchmark overlay toggle
- Period selector

### Phase 15: Comparison View
- Rank selector
- Comparison table with color coding
- Gap visualization chart
- Summary stats

### Phase 16: Replay Deep-Dive View
- Header with metadata
- Player cards
- Events timeline with filters
- Heatmap visualization

### Phase 17: Focus Areas & Players Views
- Weaknesses list with severity badges
- Strengths section
- Players search/filter
- Player detail with tendencies radar
- Tagging workflow

### Phase 18: Claude Code Coaching Skill
- Create skill directory structure
- Write SKILL.md with:
  - 4-phase coaching loop (Analysis → Diagnosis → Comparison → Prescription)
  - API query examples
  - Timestamp citation format for "why did I lose"
  - Web search strategy for practice resources
  - Fallback behavior when search fails
- Test with mock server
- Integration test with real API

---

## Verification Checklist

Before marking complete:

- [ ] All tests pass: `PYTHONPATH=src pytest -q`
- [ ] `rlcoach config --init` creates valid template
- [ ] `rlcoach config --validate` validates with proper error messages
- [ ] `rlcoach benchmarks import` loads data with metric catalog validation
- [ ] `rlcoach ingest --watch` processes replays with deduplication
- [ ] `rlcoach serve` starts API on localhost:8000
- [ ] Dashboard loads with correct data
- [ ] All API endpoints match SPEC.md contracts
- [ ] Frontend views have skeleton/empty states
- [ ] Claude skill responds to "analyze today" with 4-phase output

---

## API Contract Checklist (from SPEC.md)

| Endpoint | Pagination | Sorting | Filtering | Error Codes | Caching |
|----------|------------|---------|-----------|-------------|---------|
| GET /dashboard | - | - | - | config_error | - |
| GET /games | limit/offset | sort param | playlist, result, dates | invalid_param | - |
| GET /replays/{id} | - | - | - | not_found | - |
| GET /replays/{id}/full | - | - | - | not_found | - |
| GET /trends | - | - | metric, period, playlist | invalid_param | 5-min TTL |
| GET /benchmarks | - | - | playlist, rank | benchmark_missing | - |
| GET /compare | - | - | playlist, period | benchmark_missing | - |
| GET /patterns | - | - | playlist, period | insufficient_data | - |
| GET /weaknesses | - | - | playlist, period | benchmark_missing | - |
| GET /players | limit/offset | sort param | tagged, min_games | - | - |
| GET /players/{id} | - | - | - | not_found | - |
| POST /players/{id}/tag | - | - | - | not_found | - |

**Empty vs 404 Rule:**
- List endpoints → return `{"total": 0, "items": []}`
- Resource endpoints → return 404 if not found

---

**Plan revised and saved to `docs/plans/2025-12-23-rlcoach-full-system.md`.**
