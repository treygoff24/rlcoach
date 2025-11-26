"""Parity harness comparing rlcoach JSON to Ballchasing CSV exports."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rlcoach.report import generate_report
from rlcoach.utils.parity import (
    collect_metric_deltas,
    extract_rlcoach_player_metrics,
    extract_rlcoach_team_metrics,
    load_ballchasing_players,
    load_ballchasing_teams,
    summarize_deltas,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
RLCOACH_JSON = REPO_ROOT / "out" / "0925.json"
BALLCHASING_DIR = REPO_ROOT / "Replay_files" / "ballchasing_output"

PLAYER_TOLERANCES = {
    "score": 0.0,
    "goals": 0.0,
    "assists": 0.0,
    "saves": 0.0,
    "shots": 0.0,
    "shooting_percentage": 5.0,
    "bpm": 75.0,
    "avg_boost": 10.0,
    "amount_collected": 400.0,
    "amount_stolen": 400.0,
    "time_slow_s": 60.0,
    "time_boost_speed_s": 60.0,
    "time_supersonic_s": 20.0,
    "time_ground_s": 120.0,
    "time_low_air_s": 120.0,
    "time_high_air_s": 60.0,
    "behind_ball_pct": 10.0,
    "ahead_ball_pct": 10.0,
}

TEAM_TOLERANCES = {
    "score": 0.0,
    "goals": 0.0,
    "assists": 0.0,
    "saves": 0.0,
    "shots": 0.0,
    "shooting_percentage": 5.0,
    "bpm": 120.0,
    "avg_boost": 12.0,
    "time_slow_s": 150.0,
    "time_boost_speed_s": 150.0,
    "time_supersonic_s": 90.0,
}


def _load_report(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _get_report() -> dict:
    replay_path = REPO_ROOT / "Replay_files" / "0925.replay"
    if RLCOACH_JSON.exists():
        try:
            return _load_report(RLCOACH_JSON)
        except (OSError, json.JSONDecodeError):
            pass
    return generate_report(replay_path)


@pytest.mark.skipif(
    not (Path(__file__).resolve().parents[2] / "Replay_files" / "ballchasing_output").exists(),
    reason="Ballchasing parity test requires external fixtures not in repo"
)
def test_ballchasing_parity_snapshot():
    """Compare rlcoach output to Ballchasing CSV exports.

    This test requires external fixture files not committed to the repo:
    - Replay_files/ballchasing_output/0925_players.csv
    - Replay_files/ballchasing_output/0925_teams.csv

    These must be manually exported from ballchasing.com for parity testing.
    """
    players_csv = BALLCHASING_DIR / "0925_players.csv"
    teams_csv = BALLCHASING_DIR / "0925_teams.csv"
    if not players_csv.exists() or not teams_csv.exists():
        pytest.skip("Ballchasing CSV files not found; export from ballchasing.com")

    report = _get_report()
    rlcoach_players = extract_rlcoach_player_metrics(report)
    rlcoach_teams = extract_rlcoach_team_metrics(report)

    bc_players = load_ballchasing_players(players_csv)
    bc_teams = load_ballchasing_teams(teams_csv)

    assert bc_players, "Ballchasing player metrics empty"
    assert rlcoach_players, "rlcoach player metrics empty"
    assert set(bc_players.keys()) <= set(rlcoach_players.keys()), "rlcoach report missing players present in Ballchasing export"

    deltas = []

    for player_id, bc_metrics in bc_players.items():
        rl_metrics = rlcoach_players[player_id]
        subject = f"player {player_id}"
        deltas.extend(collect_metric_deltas(subject, bc_metrics, rl_metrics, PLAYER_TOLERANCES))

    for team_color, bc_metrics in bc_teams.items():
        rl_metrics = rlcoach_teams.get(team_color.upper())
        assert rl_metrics is not None, f"Missing rlcoach team metrics for {team_color}"
        subject = f"team {team_color.lower()}"
        deltas.extend(collect_metric_deltas(subject, bc_metrics, rl_metrics, TEAM_TOLERANCES))

    if deltas:
        deltas.sort(key=lambda d: (d.subject, d.metric))
        summary = summarize_deltas(deltas)
        pytest.fail("Ballchasing parity delta thresholds exceeded:\n" + summary)
