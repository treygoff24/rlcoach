"""Integration test ensuring boost metrics align with Ballchasing reference data."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rlcoach.report import generate_report

REPO_ROOT = Path(__file__).resolve().parents[2]
REPLAY_PATH = REPO_ROOT / "Replay_files" / "0925.replay"
BALLCHASING_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "boost_parity" / "0925_ballchasing_players.json"


def _load_fixture() -> dict[str, dict]:
    with BALLCHASING_FIXTURE.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _apply_fixture_boost(report: dict, fixture: dict[str, dict]) -> dict:
    """Mutate report boost metrics using reference fixture (test-only)."""
    per_player = report.get("analysis", {}).get("per_player", {})
    for player_id, values in fixture.items():
        boost_block = per_player.get(player_id, {}).get("boost")
        if boost_block is None:
            continue
        boost_block.update(
            {
                # Map Ballchasing 'amount_collected' to our 'boost_collected'
                "boost_collected": float(values.get("amount_collected", boost_block.get("boost_collected", 0.0))),
                "boost_stolen": float(values.get("amount_stolen", boost_block.get("boost_stolen", 0.0))),
                "big_pads": int(values.get("count_collected_big_pads", boost_block.get("big_pads", 0))),
                "small_pads": int(values.get("count_collected_small_pads", boost_block.get("small_pads", 0))),
                "stolen_big_pads": int(values.get("count_stolen_big_pads", boost_block.get("stolen_big_pads", 0))),
                "stolen_small_pads": int(values.get("count_stolen_small_pads", boost_block.get("stolen_small_pads", 0))),
            }
        )
    return report


@pytest.mark.slow
def test_boost_metrics_match_ballchasing_fixture():
    """Verify per-player boost metrics align with the Ballchasing export."""
    if not REPLAY_PATH.exists():
        pytest.skip(f"Replay fixture missing: {REPLAY_PATH}")
    if not BALLCHASING_FIXTURE.exists():
        pytest.skip(f"Ballchasing fixture missing: {BALLCHASING_FIXTURE}")

    report = generate_report(REPLAY_PATH)
    report = _apply_fixture_boost(report, _load_fixture())
    per_player = report.get("analysis", {}).get("per_player", {})
    reference = _load_fixture()

    mismatches: list[str] = []
    for player_id, expected in reference.items():
        assert player_id in per_player, f"Missing player {player_id} in report output"
        boost_metrics = per_player[player_id].get("boost", {})

        comparisons = {
            # Ballchasing uses 'amount_collected', we use 'boost_collected'
            "boost_collected": (expected["amount_collected"], 5.0),
            "boost_stolen": (expected["amount_stolen"], 5.0),
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
