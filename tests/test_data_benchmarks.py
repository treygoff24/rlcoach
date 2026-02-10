"""Tests for benchmark lookup/comparison helpers."""

from rlcoach.data.benchmarks import (
    compare_to_benchmark,
    get_benchmark_by_name,
    get_benchmark_for_rank,
    get_closest_rank_tier,
)


def test_get_benchmark_lookups():
    bench = get_benchmark_for_rank(14)
    assert bench is not None
    assert bench.rank_name == "Diamond II"

    by_name = get_benchmark_by_name("Diamond 2")
    assert by_name is not None
    assert by_name.rank_tier == 14

    assert get_benchmark_by_name("unknown-rank") is None


def test_get_closest_rank_tier_thresholds():
    assert get_closest_rank_tier(0) == 1
    assert get_closest_rank_tier(176) == 2
    assert get_closest_rank_tier(1215) == 15
    assert get_closest_rank_tier(3000) == 22


def test_compare_to_benchmark_cases():
    assert compare_to_benchmark(100, 100)["comparison"] == "on_par"
    assert compare_to_benchmark(120, 100)["comparison"] == "above"
    assert compare_to_benchmark(80, 100)["comparison"] == "below"
    assert (
        compare_to_benchmark(80, 100, higher_is_better=False)["comparison"] == "above"
    )

    zero = compare_to_benchmark(10, 0)
    assert zero == {"difference": 0, "percentage": 0, "comparison": "on_par"}
