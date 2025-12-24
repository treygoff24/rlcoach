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
    HIGHER_BETTER = "higher"      # higher is better
    LOWER_BETTER = "lower"        # lower is better
    CONTEXT_DEPENDENT = "context" # no benchmark comparison


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
