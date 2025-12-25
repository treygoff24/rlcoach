# src/rlcoach/analysis/tendencies.py
"""Teammate Tendency Analysis.

Computes playstyle profiles for players to help with adaptation recommendations.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass
class TendencyProfile:
    """Playstyle tendency profile for a player."""

    aggression_score: float  # 0-100, higher = more aggressive
    challenge_rate: float  # % of challenges won
    first_man_tendency: float  # How often they play first man
    boost_priority: float  # How much they prioritize boost
    mechanical_index: float  # Mechanical skill indicator
    defensive_index: float  # Defensive tendency


def _safe_avg(values: list[float | None]) -> float:
    """Compute average, ignoring None values."""
    valid = [v for v in values if v is not None]
    if not valid:
        return 0.0
    return sum(valid) / len(valid)


def _safe_sum(values: list[float | int | None]) -> float:
    """Sum values, treating None as 0."""
    return sum(v or 0 for v in values)


def compute_tendencies(stats: list[dict[str, Any]]) -> TendencyProfile | None:
    """Compute tendency profile from player game stats.

    Args:
        stats: List of stat dicts from multiple games

    Returns:
        TendencyProfile or None if insufficient data
    """
    if not stats:
        return None

    # Extract metrics across games
    goals = [s.get("goals") for s in stats]
    saves = [s.get("saves") for s in stats]
    shots = [s.get("shots") for s in stats]
    [s.get("assists") for s in stats]

    challenge_wins = [s.get("challenge_wins") for s in stats]
    challenge_losses = [s.get("challenge_losses") for s in stats]

    first_man_pct = [s.get("first_man_pct") for s in stats]

    bcpm = [s.get("bcpm") for s in stats]
    avg_boost = [s.get("avg_boost") for s in stats]

    aerial_count = [s.get("aerial_count") for s in stats]
    wavedash_count = [s.get("wavedash_count") for s in stats]

    time_last_defender = [s.get("time_last_defender_s") for s in stats]
    behind_ball_pct = [s.get("behind_ball_pct") for s in stats]

    # Compute aggression score (0-100)
    # Based on: shots, goals, low defensive time
    avg_shots = _safe_avg(shots)
    avg_goals = _safe_avg(goals)
    avg_behind_ball = _safe_avg(behind_ball_pct)

    # Normalize components (rough scaling)
    shots_component = min(avg_shots * 15, 40)  # Max 40 points
    goals_component = min(avg_goals * 20, 30)  # Max 30 points
    forward_component = max(0, (50 - avg_behind_ball)) * 0.6  # Max 30 points

    aggression_score = min(100, shots_component + goals_component + forward_component)

    # Challenge rate
    total_wins = _safe_sum(challenge_wins)
    total_losses = _safe_sum(challenge_losses)
    total_challenges = total_wins + total_losses

    if total_challenges > 0:
        challenge_rate = (total_wins / total_challenges) * 100
    else:
        challenge_rate = 50.0  # Default

    # First man tendency
    first_man_tendency = _safe_avg(first_man_pct)

    # Boost priority (0-100)
    # Based on: high bcpm, low avg_boost (aggressive usage)
    avg_bcpm = _safe_avg(bcpm)
    avg_boost_level = _safe_avg(avg_boost)

    # Higher bcpm = more boost collection = higher priority
    bcpm_component = min(avg_bcpm / 5, 60)  # Scale bcpm, max 60
    # Lower avg boost = using it aggressively = higher priority
    usage_component = max(0, (50 - avg_boost_level)) * 0.8  # Max 40

    boost_priority = min(100, bcpm_component + usage_component)

    # Mechanical index (0-100)
    # Based on: aerials, wavedashes
    avg_aerials = _safe_avg(aerial_count)
    avg_wavedash = _safe_avg(wavedash_count)

    aerial_component = min(avg_aerials * 15, 60)  # Max 60
    wavedash_component = min(avg_wavedash * 10, 40)  # Max 40

    mechanical_index = min(100, aerial_component + wavedash_component)

    # Defensive index (0-100)
    # Based on: saves, time as last defender, behind ball pct
    avg_saves = _safe_avg(saves)
    avg_last_defender = _safe_avg(time_last_defender)

    saves_component = min(avg_saves * 20, 40)  # Max 40
    last_def_component = min(avg_last_defender / 2, 30)  # Max 30
    behind_ball_component = min(avg_behind_ball * 0.5, 30)  # Max 30

    defensive_index = min(
        100, saves_component + last_def_component + behind_ball_component
    )

    return TendencyProfile(
        aggression_score=aggression_score,
        challenge_rate=challenge_rate,
        first_man_tendency=first_man_tendency,
        boost_priority=boost_priority,
        mechanical_index=mechanical_index,
        defensive_index=defensive_index,
    )


def compute_adaptation_score(
    my_profile: TendencyProfile,
    teammate_profile: TendencyProfile,
) -> float:
    """Compute how much adaptation is needed to play with a teammate.

    Lower score = more compatible playstyles.
    Higher score = need to adapt more.

    Args:
        my_profile: My tendency profile
        teammate_profile: Teammate's tendency profile

    Returns:
        Adaptation score 0-100
    """
    # Compute differences for each dimension
    diffs = [
        abs(my_profile.aggression_score - teammate_profile.aggression_score),
        abs(my_profile.challenge_rate - teammate_profile.challenge_rate),
        abs(my_profile.first_man_tendency - teammate_profile.first_man_tendency),
        abs(my_profile.boost_priority - teammate_profile.boost_priority),
        abs(my_profile.mechanical_index - teammate_profile.mechanical_index),
        abs(my_profile.defensive_index - teammate_profile.defensive_index),
    ]

    # RMS of differences (penalizes large differences more)
    rms = math.sqrt(sum(d**2 for d in diffs) / len(diffs))

    # Cap at 100
    return min(100, rms)
