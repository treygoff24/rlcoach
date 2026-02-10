"""Rank benchmark helpers used by API comparison endpoints."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RankBenchmarks:
    """Benchmark stats for one rank tier."""

    rank_name: str
    rank_tier: int
    goals_per_game: float
    assists_per_game: float
    saves_per_game: float
    shots_per_game: float
    shooting_pct: float
    boost_per_minute: float
    supersonic_pct: float
    aerials_per_game: float
    wavedashes_per_game: float


RANK_TIERS = {
    "bronze_1": 1,
    "bronze_2": 2,
    "bronze_3": 3,
    "silver_1": 4,
    "silver_2": 5,
    "silver_3": 6,
    "gold_1": 7,
    "gold_2": 8,
    "gold_3": 9,
    "platinum_1": 10,
    "platinum_2": 11,
    "platinum_3": 12,
    "diamond_1": 13,
    "diamond_2": 14,
    "diamond_3": 15,
    "champion_1": 16,
    "champion_2": 17,
    "champion_3": 18,
    "grand_champion_1": 19,
    "grand_champion_2": 20,
    "grand_champion_3": 21,
    "supersonic_legend": 22,
}

RANK_DISPLAY_NAMES = {
    1: "Bronze I",
    2: "Bronze II",
    3: "Bronze III",
    4: "Silver I",
    5: "Silver II",
    6: "Silver III",
    7: "Gold I",
    8: "Gold II",
    9: "Gold III",
    10: "Platinum I",
    11: "Platinum II",
    12: "Platinum III",
    13: "Diamond I",
    14: "Diamond II",
    15: "Diamond III",
    16: "Champion I",
    17: "Champion II",
    18: "Champion III",
    19: "Grand Champion I",
    20: "Grand Champion II",
    21: "Grand Champion III",
    22: "Supersonic Legend",
}


def _build_benchmark(tier: int) -> RankBenchmarks:
    """Generate smooth benchmark values by tier.

    These are heuristic values for relative comparison, not hard esports truth.
    """

    i = tier - 1
    return RankBenchmarks(
        rank_name=RANK_DISPLAY_NAMES[tier],
        rank_tier=tier,
        goals_per_game=round(0.8 + (i * 0.052), 2),
        assists_per_game=round(0.2 + (i * 0.038), 2),
        saves_per_game=round(0.6 + (i * 0.085), 2),
        shots_per_game=round(2.0 + (i * 0.20), 2),
        shooting_pct=round(8.0 + (i * 0.85), 1),
        boost_per_minute=round(180 + (i * 13.3), 1),
        supersonic_pct=round(5.0 + (i * 1.4), 1),
        aerials_per_game=round(0.5 + (i * 0.83), 2),
        wavedashes_per_game=round(0.0 + (i * 0.55), 2),
    )


RANK_BENCHMARKS: dict[int, RankBenchmarks] = {
    tier: _build_benchmark(tier) for tier in RANK_DISPLAY_NAMES
}


def get_benchmark_for_rank(rank_tier: int) -> RankBenchmarks | None:
    """Get benchmark by numeric rank tier."""

    return RANK_BENCHMARKS.get(rank_tier)


def get_benchmark_by_name(rank_name: str) -> RankBenchmarks | None:
    """Get benchmark by canonical rank slug, e.g. ``diamond_2``."""

    normalized = rank_name.strip().lower().replace(" ", "_")
    tier = RANK_TIERS.get(normalized)
    if tier is None:
        return None
    return RANK_BENCHMARKS.get(tier)


def get_closest_rank_tier(mmr: int) -> int:
    """Estimate rank tier from MMR using approximate 3v3 thresholds."""

    thresholds = [
        (0, 1),
        (175, 2),
        (255, 3),
        (335, 4),
        (415, 5),
        (495, 6),
        (575, 7),
        (655, 8),
        (735, 9),
        (815, 10),
        (895, 11),
        (975, 12),
        (1055, 13),
        (1135, 14),
        (1215, 15),
        (1295, 16),
        (1375, 17),
        (1455, 18),
        (1535, 19),
        (1615, 20),
        (1695, 21),
        (1775, 22),
    ]

    for mmr_threshold, tier in reversed(thresholds):
        if mmr >= mmr_threshold:
            return tier
    return 1


def compare_to_benchmark(
    value: float,
    benchmark_value: float,
    higher_is_better: bool = True,
) -> dict[str, float | str]:
    """Compare a player stat against benchmark and classify direction."""

    if benchmark_value == 0:
        return {"difference": 0, "percentage": 0, "comparison": "on_par"}

    difference = value - benchmark_value
    percentage = (difference / benchmark_value) * 100

    if abs(percentage) <= 5:
        comparison = "on_par"
    elif (percentage > 0 and higher_is_better) or (
        percentage < 0 and not higher_is_better
    ):
        comparison = "above"
    else:
        comparison = "below"

    return {
        "difference": round(difference, 2),
        "percentage": round(percentage, 1),
        "comparison": comparison,
    }
