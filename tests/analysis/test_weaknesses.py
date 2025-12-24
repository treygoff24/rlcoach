# tests/analysis/test_weaknesses.py
"""Tests for weakness detection algorithm."""

import pytest
from rlcoach.analysis.weaknesses import (
    compute_z_score,
    detect_weaknesses,
    WeaknessResult,
    Severity,
)


def test_compute_z_score_at_median():
    """Z-score should be 0 at median."""
    z = compute_z_score(value=50.0, p25=40.0, median=50.0, p75=60.0)
    assert z == pytest.approx(0.0, abs=0.01)


def test_compute_z_score_at_p75():
    """Z-score should be ~0.67 at p75 (1 IQR above median = ~0.67 z)."""
    z = compute_z_score(value=60.0, p25=40.0, median=50.0, p75=60.0)
    assert z == pytest.approx(0.67, abs=0.1)


def test_compute_z_score_at_p25():
    """Z-score should be ~-0.67 at p25."""
    z = compute_z_score(value=40.0, p25=40.0, median=50.0, p75=60.0)
    assert z == pytest.approx(-0.67, abs=0.1)


def test_compute_z_score_below_p25():
    """Z-score should be more negative below p25."""
    z = compute_z_score(value=30.0, p25=40.0, median=50.0, p75=60.0)
    assert z < -0.67


def test_detect_weakness_critical():
    """Values far below benchmark should be critical."""
    my_averages = {"bcpm": 250.0}  # Far below GC benchmark
    benchmarks = {
        "bcpm": {"median": 380.0, "p25": 340.0, "p75": 420.0, "direction": "higher"},
    }

    results = detect_weaknesses(my_averages, benchmarks)

    assert len(results) == 1
    assert results[0].metric == "bcpm"
    assert results[0].severity == Severity.CRITICAL


def test_detect_weakness_high():
    """Values moderately below benchmark should be high severity."""
    my_averages = {"bcpm": 320.0}  # Around p25 but still below
    benchmarks = {
        "bcpm": {"median": 380.0, "p25": 340.0, "p75": 420.0, "direction": "higher"},
    }

    results = detect_weaknesses(my_averages, benchmarks)

    assert len(results) == 1
    assert results[0].severity in (Severity.HIGH, Severity.MEDIUM)


def test_detect_strength():
    """Values above p75 for higher-is-better should be a strength."""
    my_averages = {"bcpm": 450.0}  # Above p75
    benchmarks = {
        "bcpm": {"median": 380.0, "p25": 340.0, "p75": 420.0, "direction": "higher"},
    }

    results = detect_weaknesses(my_averages, benchmarks)

    assert len(results) == 1
    assert results[0].severity == Severity.STRENGTH


def test_detect_lower_is_better_weakness():
    """For lower-is-better metrics, high values are weaknesses."""
    my_averages = {"avg_boost": 45.0}  # Higher than optimal (lower is better)
    benchmarks = {
        "avg_boost": {"median": 32.0, "p25": 28.0, "p75": 36.0, "direction": "lower"},
    }

    results = detect_weaknesses(my_averages, benchmarks)

    assert len(results) == 1
    assert results[0].severity in (Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM)


def test_detect_lower_is_better_strength():
    """For lower-is-better metrics, low values are strengths."""
    my_averages = {"avg_boost": 22.0}  # Well below median (lower is better)
    benchmarks = {
        "avg_boost": {"median": 32.0, "p25": 28.0, "p75": 36.0, "direction": "lower"},
    }

    results = detect_weaknesses(my_averages, benchmarks)

    assert len(results) == 1
    assert results[0].severity == Severity.STRENGTH


def test_skip_missing_benchmarks():
    """Metrics without benchmarks should be skipped."""
    my_averages = {"bcpm": 350.0, "unknown_metric": 100.0}
    benchmarks = {
        "bcpm": {"median": 380.0, "p25": 340.0, "p75": 420.0, "direction": "higher"},
    }

    results = detect_weaknesses(my_averages, benchmarks)

    # Only bcpm should be analyzed
    assert len(results) == 1
    assert results[0].metric == "bcpm"
