# src/rlcoach/analysis/patterns.py
"""Win/Loss Pattern Analysis.

Identifies metrics that significantly differ between wins and losses
using Cohen's d effect size to filter out noise.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass
class PatternResult:
    """Result of pattern analysis for a single metric."""

    metric: str
    win_avg: float
    loss_avg: float
    delta: float
    effect_size: float  # Cohen's d
    win_count: int
    loss_count: int
    direction: str  # "higher_in_wins" or "lower_in_wins"


def compute_cohens_d(
    win_avg: float,
    loss_avg: float,
    win_std: float,
    loss_std: float,
) -> float:
    """Compute Cohen's d effect size.

    Cohen's d = (mean1 - mean2) / pooled_std

    Effect size interpretation:
    - |d| < 0.2: negligible
    - 0.2 <= |d| < 0.5: small
    - 0.5 <= |d| < 0.8: medium
    - |d| >= 0.8: large

    Returns:
        Cohen's d value. Positive means win_avg > loss_avg.
    """
    # Handle zero variance case
    if win_std == 0 and loss_std == 0:
        if win_avg == loss_avg:
            return 0.0
        # Undefined but return large value in direction of difference
        return float("inf") if win_avg > loss_avg else float("-inf")

    # Pooled standard deviation
    pooled_std = math.sqrt((win_std**2 + loss_std**2) / 2)

    if pooled_std == 0:
        return 0.0

    return (win_avg - loss_avg) / pooled_std


def _compute_stats(values: list[float]) -> tuple[float, float]:
    """Compute mean and standard deviation of values."""
    if not values:
        return 0.0, 0.0

    n = len(values)
    mean = sum(values) / n

    if n < 2:
        return mean, 0.0

    variance = sum((x - mean) ** 2 for x in values) / (n - 1)
    std = math.sqrt(variance)

    return mean, std


def compute_pattern_analysis(
    win_stats: list[dict[str, Any]],
    loss_stats: list[dict[str, Any]],
    min_games: int = 5,
    min_effect_size: float = 0.5,
) -> list[PatternResult]:
    """Analyze win/loss patterns across metrics.

    Args:
        win_stats: List of stat dicts from winning games
        loss_stats: List of stat dicts from losing games
        min_games: Minimum games in each category to analyze
        min_effect_size: Minimum |Cohen's d| to consider significant

    Returns:
        List of PatternResult for metrics with significant differences,
        sorted by absolute effect size descending.
    """
    # Check minimum games
    if len(win_stats) < min_games or len(loss_stats) < min_games:
        return []

    # Collect all metrics present in stats
    all_metrics: set[str] = set()
    for stats in win_stats + loss_stats:
        all_metrics.update(k for k, v in stats.items() if isinstance(v, (int, float)))

    results: list[PatternResult] = []

    for metric in all_metrics:
        # Extract values for this metric
        win_values = [
            s[metric] for s in win_stats if metric in s and s[metric] is not None
        ]
        loss_values = [
            s[metric] for s in loss_stats if metric in s and s[metric] is not None
        ]

        # Need enough data points
        if len(win_values) < min_games or len(loss_values) < min_games:
            continue

        # Compute statistics
        win_avg, win_std = _compute_stats(win_values)
        loss_avg, loss_std = _compute_stats(loss_values)

        # Compute effect size
        effect_size = compute_cohens_d(win_avg, loss_avg, win_std, loss_std)

        # Filter by minimum effect size
        if abs(effect_size) < min_effect_size:
            continue

        # Determine direction
        direction = "higher_in_wins" if effect_size > 0 else "lower_in_wins"

        results.append(
            PatternResult(
                metric=metric,
                win_avg=win_avg,
                loss_avg=loss_avg,
                delta=win_avg - loss_avg,
                effect_size=effect_size,
                win_count=len(win_values),
                loss_count=len(loss_values),
                direction=direction,
            )
        )

    # Sort by absolute effect size descending
    results.sort(key=lambda r: abs(r.effect_size), reverse=True)

    return results
