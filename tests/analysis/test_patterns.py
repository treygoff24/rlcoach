# tests/analysis/test_patterns.py
"""Tests for win/loss pattern analysis."""

import pytest
from rlcoach.analysis.patterns import (
    compute_pattern_analysis,
    compute_cohens_d,
    PatternResult,
)


def test_cohens_d_positive_effect():
    """Positive effect size when win avg is higher."""
    d = compute_cohens_d(
        win_avg=400.0,
        loss_avg=350.0,
        win_std=50.0,
        loss_std=50.0,
    )
    assert d > 0
    assert d == pytest.approx(1.0, rel=0.01)  # (400-350) / 50 = 1.0


def test_cohens_d_negative_effect():
    """Negative effect size when loss avg is higher (for lower-is-better metrics)."""
    d = compute_cohens_d(
        win_avg=30.0,
        loss_avg=40.0,
        win_std=10.0,
        loss_std=10.0,
    )
    assert d < 0
    assert d == pytest.approx(-1.0, rel=0.01)


def test_cohens_d_no_variance():
    """Return 0 when there's no variance."""
    d = compute_cohens_d(
        win_avg=100.0,
        loss_avg=100.0,
        win_std=0.0,
        loss_std=0.0,
    )
    assert d == 0.0


def test_pattern_analysis_finds_significant_patterns():
    """Should identify metrics with significant win/loss differences."""
    # Simulated stats grouped by result
    win_stats = [
        {"bcpm": 400, "avg_boost": 30, "behind_ball_pct": 60},
        {"bcpm": 420, "avg_boost": 32, "behind_ball_pct": 62},
        {"bcpm": 380, "avg_boost": 28, "behind_ball_pct": 58},
    ]
    loss_stats = [
        {"bcpm": 320, "avg_boost": 35, "behind_ball_pct": 48},
        {"bcpm": 340, "avg_boost": 38, "behind_ball_pct": 50},
        {"bcpm": 300, "avg_boost": 36, "behind_ball_pct": 46},
    ]

    patterns = compute_pattern_analysis(
        win_stats=win_stats,
        loss_stats=loss_stats,
        min_games=3,
        min_effect_size=0.5,
    )

    # Should find bcpm as a significant pattern (higher in wins)
    bcpm_pattern = next((p for p in patterns if p.metric == "bcpm"), None)
    assert bcpm_pattern is not None
    assert bcpm_pattern.win_avg > bcpm_pattern.loss_avg
    assert bcpm_pattern.effect_size > 0.5


def test_pattern_analysis_respects_min_games():
    """Should not analyze if fewer games than threshold."""
    win_stats = [{"bcpm": 400}]
    loss_stats = [{"bcpm": 300}]

    patterns = compute_pattern_analysis(
        win_stats=win_stats,
        loss_stats=loss_stats,
        min_games=3,
        min_effect_size=0.5,
    )

    # Not enough games
    assert patterns == []


def test_pattern_analysis_respects_min_effect_size():
    """Should only return patterns above effect size threshold."""
    # Very similar stats
    win_stats = [
        {"bcpm": 350, "avg_boost": 33},
        {"bcpm": 355, "avg_boost": 34},
        {"bcpm": 345, "avg_boost": 32},
    ]
    loss_stats = [
        {"bcpm": 340, "avg_boost": 34},
        {"bcpm": 345, "avg_boost": 35},
        {"bcpm": 335, "avg_boost": 33},
    ]

    patterns = compute_pattern_analysis(
        win_stats=win_stats,
        loss_stats=loss_stats,
        min_games=3,
        min_effect_size=0.8,  # High threshold
    )

    # Small differences shouldn't meet threshold
    assert len(patterns) == 0 or all(abs(p.effect_size) >= 0.8 for p in patterns)
