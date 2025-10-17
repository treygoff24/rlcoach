#!/usr/bin/env python3
"""Quick parity diff for boost pickup metrics against Ballchasing exports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping


def _load_rlcoach_players(path: Path) -> dict[str, Mapping[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("analysis", {}).get("per_player", {})


def _load_ballchasing_players(path: Path) -> dict[str, Mapping[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_metrics(payload: Mapping[str, Any]) -> dict[str, float]:
    boost = payload.get("boost", {})
    return {
        "amount_collected": float(boost.get("amount_collected", 0.0)),
        "amount_stolen": float(boost.get("amount_stolen", 0.0)),
        "big_pads": float(boost.get("big_pads", 0.0)),
        "small_pads": float(boost.get("small_pads", 0.0)),
        "stolen_big_pads": float(boost.get("stolen_big_pads", 0.0)),
        "stolen_small_pads": float(boost.get("stolen_small_pads", 0.0)),
    }


def _extract_reference(payload: Mapping[str, Any]) -> dict[str, float]:
    return {
        "amount_collected": float(payload.get("amount_collected", 0.0)),
        "amount_stolen": float(payload.get("amount_stolen", 0.0)),
        "big_pads": float(payload.get("count_collected_big_pads", 0.0)),
        "small_pads": float(payload.get("count_collected_small_pads", 0.0)),
        "stolen_big_pads": float(payload.get("count_stolen_big_pads", 0.0)),
        "stolen_small_pads": float(payload.get("count_stolen_small_pads", 0.0)),
    }


def _format_delta(metric: str, rl_value: float, ref_value: float) -> str:
    delta = rl_value - ref_value
    return f"{metric:>18}: Δ={delta:+7.2f} (rlcoach={rl_value:7.2f}, ref={ref_value:7.2f})"


def run_diff(rlcoach_json: Path, ballchasing_json: Path) -> int:
    rlcoach_players = _load_rlcoach_players(rlcoach_json)
    reference_players = _load_ballchasing_players(ballchasing_json)

    missing = sorted(set(reference_players) - set(rlcoach_players))
    if missing:
        print("Missing rlcoach players:", ", ".join(missing))
        return 1

    exit_code = 0
    for player_id in sorted(reference_players):
        rl_metrics = _extract_metrics(rlcoach_players[player_id])
        ref_metrics = _extract_reference(reference_players[player_id])
        print(f"\nPlayer {player_id}:")
        for metric in sorted(ref_metrics):
            ref_value = ref_metrics[metric]
            rl_value = rl_metrics.get(metric, 0.0)
            print(_format_delta(metric, rl_value, ref_value))
            if abs(rl_value - ref_value) > 0.5:
                exit_code = 2
    return exit_code


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rlcoach-json",
        default=Path("out/0925.json"),
        type=Path,
        help="Path to rlcoach JSON report.",
    )
    parser.add_argument(
        "--ballchasing-json",
        default=Path("tests/fixtures/boost_parity/0925_ballchasing_players.json"),
        type=Path,
        help="Path to normalized Ballchasing player fixture.",
    )
    args = parser.parse_args()
    exit(run_diff(args.rlcoach_json, args.ballchasing_json))


if __name__ == "__main__":
    main()
