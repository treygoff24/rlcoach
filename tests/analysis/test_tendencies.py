# tests/analysis/test_tendencies.py
"""Tests for teammate tendency analysis."""

import pytest

from rlcoach.analysis.tendencies import (
    TendencyProfile,
    compute_adaptation_score,
    compute_tendencies,
)


def test_compute_tendencies_basic():
    """Compute tendencies from player stats."""
    stats = [
        {
            "goals": 2, "saves": 1, "shots": 4, "assists": 1,
            "challenge_wins": 5, "challenge_losses": 3,
            "first_man_pct": 40.0, "second_man_pct": 35.0, "third_man_pct": 25.0,
            "bcpm": 380, "avg_boost": 35,
            "aerial_count": 3, "wavedash_count": 2,
            "time_last_defender_s": 60.0, "behind_ball_pct": 55.0,
        },
        {
            "goals": 1, "saves": 2, "shots": 3, "assists": 0,
            "challenge_wins": 4, "challenge_losses": 4,
            "first_man_pct": 35.0, "second_man_pct": 40.0, "third_man_pct": 25.0,
            "bcpm": 360, "avg_boost": 38,
            "aerial_count": 2, "wavedash_count": 1,
            "time_last_defender_s": 80.0, "behind_ball_pct": 60.0,
        },
    ]

    profile = compute_tendencies(stats)

    assert isinstance(profile, TendencyProfile)
    assert profile.aggression_score > 0
    assert 0 <= profile.challenge_rate <= 100
    assert profile.first_man_tendency > 0


def test_compute_tendencies_empty_stats():
    """Should return None for empty stats."""
    profile = compute_tendencies([])
    assert profile is None


def test_compute_tendencies_single_game():
    """Should work with just one game."""
    stats = [{
        "goals": 1, "saves": 1, "shots": 2, "assists": 0,
        "challenge_wins": 3, "challenge_losses": 2,
        "first_man_pct": 50.0,
        "bcpm": 350, "avg_boost": 40,
        "aerial_count": 1, "wavedash_count": 0,
        "time_last_defender_s": 45.0, "behind_ball_pct": 50.0,
    }]

    profile = compute_tendencies(stats)
    assert profile is not None


def test_adaptation_score_similar_playstyles():
    """Similar playstyles should have low adaptation needed."""
    my_profile = TendencyProfile(
        aggression_score=60.0,
        challenge_rate=55.0,
        first_man_tendency=40.0,
        boost_priority=50.0,
        mechanical_index=45.0,
        defensive_index=50.0,
    )
    teammate_profile = TendencyProfile(
        aggression_score=58.0,
        challenge_rate=52.0,
        first_man_tendency=38.0,
        boost_priority=48.0,
        mechanical_index=43.0,
        defensive_index=52.0,
    )

    score = compute_adaptation_score(my_profile, teammate_profile)

    # Similar profiles should need minimal adaptation
    assert score < 30  # Low adaptation needed


def test_adaptation_score_opposite_playstyles():
    """Opposite playstyles should require high adaptation."""
    my_profile = TendencyProfile(
        aggression_score=80.0,  # Very aggressive
        challenge_rate=70.0,
        first_man_tendency=65.0,
        boost_priority=60.0,
        mechanical_index=70.0,
        defensive_index=30.0,
    )
    teammate_profile = TendencyProfile(
        aggression_score=20.0,  # Very passive
        challenge_rate=30.0,
        first_man_tendency=25.0,
        boost_priority=40.0,
        mechanical_index=25.0,
        defensive_index=75.0,
    )

    score = compute_adaptation_score(my_profile, teammate_profile)

    # Very different profiles need significant adaptation
    assert score > 40


def test_adaptation_score_self():
    """Adaptation to self should be 0."""
    profile = TendencyProfile(
        aggression_score=50.0,
        challenge_rate=50.0,
        first_man_tendency=50.0,
        boost_priority=50.0,
        mechanical_index=50.0,
        defensive_index=50.0,
    )

    score = compute_adaptation_score(profile, profile)
    assert score == pytest.approx(0.0, abs=0.01)
