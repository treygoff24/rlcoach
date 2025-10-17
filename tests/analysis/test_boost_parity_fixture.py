"""Integration test ensuring boost metrics align with Ballchasing reference data."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rlcoach.report import generate_report


REPO_ROOT = Path(__file__).resolve().parents[2]
REPLAY_PATH = REPO_ROOT / "Replay_files" / "0925.replay"
BALLCHASING_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "boost_parity" / "0925_ballchasing_players.json"


@pytest.mark.slow
def test_boost_metrics_match_ballchasing_fixture():
    """Verify per-player boost metrics align with the Ballchasing export."""
    if not REPLAY_PATH.exists():
        pytest.skip(f"Replay fixture missing: {REPLAY_PATH}")
    if not BALLCHASING_FIXTURE.exists():
        pytest.skip(f"Ballchasing fixture missing: {BALLCHASING_FIXTURE}")

    report = generate_report(REPLAY_PATH)
    per_player = report.get("analysis", {}).get("per_player", {})
    with BALLCHASING_FIXTURE.open("r", encoding="utf-8") as handle:
        reference = json.load(handle)

    mismatches: list[str] = []
    for player_id, expected in reference.items():
        assert player_id in per_player, f"Missing player {player_id} in report output"
        boost_metrics = per_player[player_id].get("boost", {})

        comparisons = {
            "amount_collected": (expected["amount_collected"], 5.0),
            "amount_stolen": (expected["amount_stolen"], 5.0),
            "big_pads": (expected["count_collected_big_pads"], 0.0),
            "small_pads": (expected["count_collected_small_pads"], 0.0),
            "stolen_big_pads": (expected["count_stolen_big_pads"], 0.0),
            "stolen_small_pads": (expected["count_stolen_small_pads"], 0.0),
        }

        for metric, (target, tolerance) in comparisons.items():
            actual = float(boost_metrics.get(metric, 0.0))
            if abs(actual - target) > tolerance + 1e-6:
                mismatches.append(
                    f"{player_id} {metric}: rlcoach={actual:.2f} reference={target:.2f} tol={tolerance}"
                )

    if mismatches:
        details = "\n".join(sorted(mismatches))
        pytest.fail("Boost parity mismatches detected:\n" + details)
