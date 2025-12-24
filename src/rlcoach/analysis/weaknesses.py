# src/rlcoach/analysis/weaknesses.py
"""Weakness Detection Algorithm.

Compares player metrics against benchmarks to identify areas for improvement.
Uses z-scores derived from percentiles to quantify distance from target.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class Severity(Enum):
    """Weakness/strength severity levels."""
    CRITICAL = "critical"  # z < -2.0 (far below target)
    HIGH = "high"          # -2.0 <= z < -1.0
    MEDIUM = "medium"      # -1.0 <= z < -0.5
    LOW = "low"            # -0.5 <= z < 0
    NEUTRAL = "neutral"    # z ~ 0
    STRENGTH = "strength"  # z > 0.67 (above p75 equivalent)


@dataclass
class WeaknessResult:
    """Result of weakness analysis for a single metric."""
    metric: str
    my_value: float
    benchmark_median: float
    benchmark_p25: float
    benchmark_p75: float
    z_score: float
    severity: Severity
    gap: float  # Difference from median
    direction: str  # "higher" or "lower" is better


def compute_z_score(
    value: float,
    p25: float,
    median: float,
    p75: float,
) -> float:
    """Compute z-score from percentile-based distribution.

    Uses the interquartile range (IQR) to estimate standard deviation,
    assuming a normal distribution where IQR ≈ 1.35 * σ.

    Args:
        value: The observed value
        p25: 25th percentile benchmark
        median: 50th percentile benchmark
        p75: 75th percentile benchmark

    Returns:
        Approximate z-score (0 = at median, positive = above, negative = below)
    """
    iqr = p75 - p25

    if iqr == 0:
        # No variance in benchmark
        if value == median:
            return 0.0
        return float('inf') if value > median else float('-inf')

    # Estimate standard deviation from IQR
    # For normal distribution: IQR ≈ 1.35 * σ, so σ ≈ IQR / 1.35
    estimated_std = iqr / 1.35

    return (value - median) / estimated_std


def _assign_severity(z_score: float, direction: str) -> Severity:
    """Assign severity based on z-score and metric direction.

    Args:
        z_score: The z-score (positive = above median)
        direction: "higher" if higher is better, "lower" if lower is better

    Returns:
        Severity level
    """
    # For lower-is-better metrics, flip the z-score interpretation
    effective_z = z_score if direction == "higher" else -z_score

    if effective_z >= 0.67:  # Above p75 equivalent
        return Severity.STRENGTH
    elif effective_z >= 0:
        return Severity.NEUTRAL
    elif effective_z >= -0.5:
        return Severity.LOW
    elif effective_z >= -1.0:
        return Severity.MEDIUM
    elif effective_z >= -2.0:
        return Severity.HIGH
    else:
        return Severity.CRITICAL


def detect_weaknesses(
    my_averages: dict[str, float],
    benchmarks: dict[str, dict[str, Any]],
) -> list[WeaknessResult]:
    """Detect weaknesses by comparing player metrics to benchmarks.

    Args:
        my_averages: Dict of metric -> my average value
        benchmarks: Dict of metric -> {median, p25, p75, direction}

    Returns:
        List of WeaknessResult sorted by severity (worst first)
    """
    results: list[WeaknessResult] = []

    for metric, my_value in my_averages.items():
        if metric not in benchmarks:
            continue

        bench = benchmarks[metric]
        median = bench["median"]
        p25 = bench["p25"]
        p75 = bench["p75"]
        direction = bench.get("direction", "higher")

        z_score = compute_z_score(my_value, p25, median, p75)
        severity = _assign_severity(z_score, direction)

        # Compute gap from median
        gap = my_value - median

        results.append(WeaknessResult(
            metric=metric,
            my_value=my_value,
            benchmark_median=median,
            benchmark_p25=p25,
            benchmark_p75=p75,
            z_score=z_score,
            severity=severity,
            gap=gap,
            direction=direction,
        ))

    # Sort by severity (worst first)
    severity_order = {
        Severity.CRITICAL: 0,
        Severity.HIGH: 1,
        Severity.MEDIUM: 2,
        Severity.LOW: 3,
        Severity.NEUTRAL: 4,
        Severity.STRENGTH: 5,
    }
    results.sort(key=lambda r: severity_order[r.severity])

    return results