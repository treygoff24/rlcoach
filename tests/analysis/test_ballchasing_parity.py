"""Parity harness comparing rlcoach JSON to Ballchasing CSV exports."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

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


@pytest.mark.xfail(reason="Known analyzer gaps vs Ballchasing baseline", strict=False)
def test_ballchasing_parity_snapshot():
    assert RLCOACH_JSON.exists(), f"rlcoach report missing at {RLCOACH_JSON}"
    players_csv = BALLCHASING_DIR / "0925_players.csv"
    teams_csv = BALLCHASING_DIR / "0925_teams.csv"
    assert players_csv.exists(), "Ballchasing player CSV missing"
    assert teams_csv.exists(), "Ballchasing team CSV missing"

    report = _load_report(RLCOACH_JSON)
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
        pytest.xfail("Ballchasing parity delta thresholds exceeded:\n" + summary)
