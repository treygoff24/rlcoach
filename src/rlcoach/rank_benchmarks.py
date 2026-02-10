"""Static rank benchmark helpers used by API comparison endpoints."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RankBenchmark:
    """Reference stats for a representative rank tier."""

    rank_tier: int
    rank_name: str
    goals_per_game: float
    assists_per_game: float
    saves_per_game: float
    shots_per_game: float
    shooting_pct: float
    boost_per_minute: float
    supersonic_pct: float
    aerials_per_game: float
    wavedashes_per_game: float


RANK_DISPLAY_NAMES: dict[int, str] = {
    1: "Bronze I",
    4: "Silver I",
    7: "Gold I",
    10: "Platinum I",
    13: "Diamond I",
    16: "Champion I",
    19: "Grand Champion I",
    22: "Supersonic Legend",
}


_RANK_BENCHMARKS: dict[int, RankBenchmark] = {
    1: RankBenchmark(1, "Bronze I", 0.25, 0.15, 0.65, 1.8, 14.0, 220.0, 5.0, 0.2, 0.1),
    4: RankBenchmark(4, "Silver I", 0.40, 0.20, 0.80, 2.1, 16.0, 260.0, 7.0, 0.3, 0.2),
    7: RankBenchmark(7, "Gold I", 0.55, 0.28, 0.95, 2.4, 19.0, 300.0, 10.0, 0.5, 0.3),
    10: RankBenchmark(
        10, "Platinum I", 0.72, 0.35, 1.10, 2.8, 22.0, 340.0, 13.0, 0.7, 0.4
    ),
    13: RankBenchmark(
        13, "Diamond I", 0.90, 0.45, 1.25, 3.1, 24.0, 375.0, 16.0, 0.9, 0.5
    ),
    16: RankBenchmark(
        16, "Champion I", 1.05, 0.55, 1.35, 3.5, 27.0, 410.0, 19.0, 1.1, 0.7
    ),
    19: RankBenchmark(
        19,
        "Grand Champion I",
        1.20,
        0.62,
        1.45,
        3.9,
        30.0,
        445.0,
        22.0,
        1.3,
        0.9,
    ),
    22: RankBenchmark(
        22,
        "Supersonic Legend",
        1.35,
        0.70,
        1.60,
        4.2,
        32.0,
        480.0,
        25.0,
        1.6,
        1.1,
    ),
}


def get_benchmark_for_rank(rank_tier: int | None) -> RankBenchmark | None:
    """Return exact or nearest-lower benchmark for a rank tier."""
    if rank_tier is None:
        return None
    if rank_tier in _RANK_BENCHMARKS:
        return _RANK_BENCHMARKS[rank_tier]

    eligible = [tier for tier in _RANK_BENCHMARKS if tier <= rank_tier]
    if not eligible:
        return _RANK_BENCHMARKS[min(_RANK_BENCHMARKS)]
    return _RANK_BENCHMARKS[max(eligible)]


def compare_to_benchmark(
    user_value: float,
    benchmark_value: float,
    higher_is_better: bool = True,
) -> dict[str, float | str]:
    """Compare a user metric against a benchmark metric."""
    difference = float(user_value) - float(benchmark_value)
    if benchmark_value:
        percentage = (difference / float(benchmark_value)) * 100.0
    else:
        percentage = 0.0

    if abs(percentage) <= 5.0:
        comparison = "on_par"
    else:
        is_better = difference > 0 if higher_is_better else difference < 0
        comparison = "above" if is_better else "below"

    return {
        "difference": round(difference, 2),
        "percentage": round(percentage, 2),
        "comparison": comparison,
    }
