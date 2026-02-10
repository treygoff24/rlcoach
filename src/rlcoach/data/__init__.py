# src/rlcoach/data/__init__.py
"""Data modules for rlcoach."""

from .benchmarks import (
    RANK_BENCHMARKS,
    RANK_DISPLAY_NAMES,
    RANK_TIERS,
    RankBenchmarks,
    compare_to_benchmark,
    get_benchmark_by_name,
    get_benchmark_for_rank,
    get_closest_rank_tier,
)

__all__ = [
    "RankBenchmarks",
    "RANK_BENCHMARKS",
    "RANK_TIERS",
    "RANK_DISPLAY_NAMES",
    "get_benchmark_for_rank",
    "get_benchmark_by_name",
    "get_closest_rank_tier",
    "compare_to_benchmark",
]
