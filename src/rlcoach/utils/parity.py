"""Utilities for comparing rlcoach output to external stat sources."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .identity import sanitize_display_name


def _to_float(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    token = str(value).strip()
    if not token:
        return 0.0
    try:
        return float(token)
    except ValueError:
        return 0.0


def _normalize_platform(name: str | None) -> str:
    if not name:
        return "unknown"
    token = str(name).strip().lower().replace(" ", "")
    aliases = {
        "steam": "steam",
        "epic": "epic",
        "epicgames": "epic",
        "ps4": "psn",
        "ps5": "psn",
        "psn": "psn",
        "playstation": "psn",
        "xbox": "xbox",
        "xboxone": "xbox",
        "xboxseries": "xbox",
        "switch": "switch",
        "nintendo": "switch",
    }
    return aliases.get(token, token)


def _format_value(value: float) -> str:
    if abs(value - round(value)) < 1e-6:
        return str(int(round(value)))
    return f"{value:.2f}"


@dataclass(frozen=True)
class MetricDelta:
    subject: str
    metric: str
    rlcoach_value: float
    reference_value: float
    tolerance: float

    @property
    def delta(self) -> float:
        return self.rlcoach_value - self.reference_value

    def format_row(self) -> str:
        diff = self.delta
        rl_val = _format_value(self.rlcoach_value)
        ref_val = _format_value(self.reference_value)
        tol = _format_value(self.tolerance)
        return (
            f"{self.subject} [{self.metric}]: Δ={diff:+.2f} "
            f"(rlcoach={rl_val}, reference={ref_val}, tol={tol})"
        )


def load_ballchasing_players(csv_path: Path) -> dict[str, dict[str, Any]]:
    """Load core player metrics from a Ballchasing CSV export."""
    players: dict[str, dict[str, Any]] = {}
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        for row in reader:
            platform = _normalize_platform(row.get("platform"))
            player_id = (row.get("player id") or "").strip()
            if not platform or not player_id:
                continue
            canonical_id = f"{platform}:{player_id}"
            players[canonical_id] = {
                "display_name": sanitize_display_name(row.get("player name")),
                "team": (row.get("color") or "").strip().upper() or "UNKNOWN",
                "score": _to_float(row.get("score")),
                "goals": _to_float(row.get("goals")),
                "assists": _to_float(row.get("assists")),
                "saves": _to_float(row.get("saves")),
                "shots": _to_float(row.get("shots")),
                "shooting_percentage": _to_float(row.get("shooting percentage")),
                "bpm": _to_float(row.get("bpm")),
                "avg_boost": _to_float(row.get("avg boost amount")),
                "amount_collected": _to_float(row.get("amount collected")),
                "amount_stolen": _to_float(row.get("amount stolen")),
                "time_slow_s": _to_float(row.get("time slow speed")),
                "time_boost_speed_s": _to_float(row.get("time boost speed")),
                "time_supersonic_s": _to_float(row.get("time supersonic speed")),
                "time_ground_s": _to_float(row.get("time on ground")),
                "time_low_air_s": _to_float(row.get("time low in air")),
                "time_high_air_s": _to_float(row.get("time high in air")),
                "behind_ball_pct": _to_float(row.get("percentage behind ball")),
                "ahead_ball_pct": _to_float(row.get("percentage in front of ball")),
            }
    return players


def load_ballchasing_teams(csv_path: Path) -> dict[str, dict[str, Any]]:
    """Load team-level metrics from a Ballchasing CSV export."""
    teams: dict[str, dict[str, Any]] = {}
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        for row in reader:
            color = (row.get("color") or "").strip().upper()
            if not color:
                continue
            teams[color] = {
                "score": _to_float(row.get("score")),
                "goals": _to_float(row.get("goals")),
                "assists": _to_float(row.get("assists")),
                "saves": _to_float(row.get("saves")),
                "shots": _to_float(row.get("shots")),
                "shooting_percentage": _to_float(row.get("shooting percentage")),
                "bpm": _to_float(row.get("bpm")),
                "avg_boost": _to_float(row.get("avg boost amount")),
                "time_slow_s": _to_float(row.get("time slow speed")),
                "time_boost_speed_s": _to_float(row.get("time boost speed")),
                "time_supersonic_s": _to_float(row.get("time supersonic speed")),
            }
    return teams


def extract_rlcoach_player_metrics(report: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Flatten rlcoach per-player metrics for comparison."""
    players_meta = {p["player_id"]: p for p in report.get("players", [])}
    per_player = report.get("analysis", {}).get("per_player", {})
    flattened: dict[str, dict[str, Any]] = {}
    for player_id, payload in per_player.items():
        fundamentals = payload.get("fundamentals", {})
        boost = payload.get("boost", {})
        movement = payload.get("movement", {})
        positioning = payload.get("positioning", {})
        flattened[player_id] = {
            "display_name": players_meta.get(player_id, {}).get("display_name"),
            "team": players_meta.get(player_id, {}).get("team", "UNKNOWN"),
            "score": _to_float(fundamentals.get("score")),
            "goals": _to_float(fundamentals.get("goals")),
            "assists": _to_float(fundamentals.get("assists")),
            "saves": _to_float(fundamentals.get("saves")),
            "shots": _to_float(fundamentals.get("shots")),
            "shooting_percentage": _to_float(fundamentals.get("shooting_percentage")),
            "bpm": _to_float(boost.get("bpm")),
            "avg_boost": _to_float(boost.get("avg_boost")),
            "amount_collected": _to_float(boost.get("amount_collected")),
            "amount_stolen": _to_float(boost.get("amount_stolen")),
            "time_slow_s": _to_float(movement.get("time_slow_s")),
            "time_boost_speed_s": _to_float(movement.get("time_boost_speed_s")),
            "time_supersonic_s": _to_float(movement.get("time_supersonic_s")),
            "time_ground_s": _to_float(movement.get("time_ground_s")),
            "time_low_air_s": _to_float(movement.get("time_low_air_s")),
            "time_high_air_s": _to_float(movement.get("time_high_air_s")),
            "behind_ball_pct": _to_float(positioning.get("behind_ball_pct")),
            "ahead_ball_pct": _to_float(positioning.get("ahead_ball_pct")),
        }
    return flattened


def extract_rlcoach_team_metrics(report: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Flatten rlcoach per-team metrics for comparison."""
    per_team = report.get("analysis", {}).get("per_team", {})
    teams: dict[str, dict[str, Any]] = {}
    for color in ("blue", "orange"):
        payload = per_team.get(color, {})
        fundamentals = payload.get("fundamentals", {})
        boost = payload.get("boost", {})
        movement = payload.get("movement", {})
        teams[color.upper()] = {
            "score": _to_float(fundamentals.get("score")),
            "goals": _to_float(fundamentals.get("goals")),
            "assists": _to_float(fundamentals.get("assists")),
            "saves": _to_float(fundamentals.get("saves")),
            "shots": _to_float(fundamentals.get("shots")),
            "shooting_percentage": _to_float(fundamentals.get("shooting_percentage")),
            "bpm": _to_float(boost.get("bpm")),
            "avg_boost": _to_float(boost.get("avg_boost")),
            "time_slow_s": _to_float(movement.get("time_slow_s")),
            "time_boost_speed_s": _to_float(movement.get("time_boost_speed_s")),
            "time_supersonic_s": _to_float(movement.get("time_supersonic_s")),
        }
    return teams


def collect_metric_deltas(
    subject: str,
    reference_metrics: Mapping[str, float],
    rlcoach_metrics: Mapping[str, float],
    tolerances: Mapping[str, float],
) -> list[MetricDelta]:
    """Compare two metric dictionaries and record deltas above tolerance."""
    deltas: list[MetricDelta] = []
    for key, tolerance in tolerances.items():
        ref_value = _to_float(reference_metrics.get(key))
        rl_value = _to_float(rlcoach_metrics.get(key))
        if tolerance < 0:
            continue
        if abs(rl_value - ref_value) > tolerance + 1e-6:
            deltas.append(
                MetricDelta(subject=subject, metric=key, rlcoach_value=rl_value, reference_value=ref_value, tolerance=tolerance)
            )
    return deltas


def summarize_deltas(deltas: Iterable[MetricDelta]) -> str:
    """Format a list of metric deltas for reporting."""
    rows = [delta.format_row() for delta in deltas]
    return "\n".join(rows)


__all__ = [
    "MetricDelta",
    "collect_metric_deltas",
    "extract_rlcoach_player_metrics",
    "extract_rlcoach_team_metrics",
    "load_ballchasing_players",
    "load_ballchasing_teams",
    "summarize_deltas",
]

