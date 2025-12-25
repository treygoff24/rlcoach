"""Challenges/50-50s analysis.

Derives contest counts and outcomes from touch sequences with deterministic
thresholds. Computes first-to-ball percentage, average challenge depth, and a
simple risk index based on player context at the time of the contest.

Deterministic thresholds:
- CHALLENGE_WINDOW_S = 1.2  (max time between opposing touches to form a contest)
- CHALLENGE_RADIUS_UU = 1000.0 (max spatial separation between opposing touches)
- NEUTRAL_RETOUCH_WINDOW_S = 0.25 (rapid re-contest yields neutral)

Risk index factors (0..1), weights sum to 1:
- ahead_of_ball_weight = 0.4  (player is ahead of ball for their team)
- low_boost_weight = 0.3      (boost <= 20)
- last_man_weight = 0.3       (furthest back relative to own goal)

All computations are local-only and reproducible.
"""

from __future__ import annotations

from typing import Any

from ..events import (
    ChallengeEvent,
    TouchEvent,
    detect_challenge_events,
    detect_touches,
)
from ..parser.types import Frame, Header


def analyze_challenges(
    frames: list[Frame],
    events: dict[str, list[Any]] | None = None,
    player_id: str | None = None,
    team: str | None = None,
    header: Header | None = None,
) -> dict[str, Any]:
    """Analyze 50/50 contests and compute outcome metrics.

    Returns schema-aligned dict with:
      contests, wins, losses, neutral, first_to_ball_pct,
      challenge_depth_m, risk_index_avg
    """
    touches: list[TouchEvent] = []
    if events and isinstance(events.get("touches"), list):
        touches = list(events.get("touches", []))
    if not touches and frames:
        touches = detect_touches(frames)

    challenge_events: list[ChallengeEvent] = []
    if events and isinstance(events.get("challenges"), list):
        challenge_events = [
            evt
            for evt in events.get("challenges", [])
            if isinstance(evt, ChallengeEvent)
        ]
    if not challenge_events:
        challenge_events = detect_challenge_events(frames, touches)

    team_stats: dict[str, dict[str, Any]] = {
        "BLUE": {
            "contests": 0,
            "wins": 0,
            "losses": 0,
            "neutral": 0,
            "first_to_ball": 0,
            "depth_sum": 0.0,
            "risk_sum": 0.0,
            "risk_count": 0,
        },
        "ORANGE": {
            "contests": 0,
            "wins": 0,
            "losses": 0,
            "neutral": 0,
            "first_to_ball": 0,
            "depth_sum": 0.0,
            "risk_sum": 0.0,
            "risk_count": 0,
        },
    }

    player_stats: dict[str, dict[str, Any]] = {}

    def ensure_player(pid: str) -> dict[str, Any]:
        if pid not in player_stats:
            player_stats[pid] = {
                "contests": 0,
                "wins": 0,
                "losses": 0,
                "neutral": 0,
                "first_to_ball": 0,
                "depth_sum": 0.0,
                "risk_sum": 0.0,
                "risk_count": 0,
            }
        return player_stats[pid]

    for evt in challenge_events:
        first_team_stats = team_stats.get(evt.first_team)
        second_team_stats = team_stats.get(evt.second_team)
        if first_team_stats is None or second_team_stats is None:
            continue

        first_team_stats["contests"] += 1
        second_team_stats["contests"] += 1
        first_team_stats["first_to_ball"] += 1
        first_team_stats["depth_sum"] += evt.depth_m
        second_team_stats["depth_sum"] += evt.depth_m
        first_team_stats["risk_sum"] += evt.risk_first
        first_team_stats["risk_count"] += 1
        second_team_stats["risk_sum"] += evt.risk_second
        second_team_stats["risk_count"] += 1

        if evt.outcome == "WIN":
            first_team_stats["wins"] += 1
            second_team_stats["losses"] += 1
        elif evt.outcome == "LOSS":
            first_team_stats["losses"] += 1
            second_team_stats["wins"] += 1
        else:
            first_team_stats["neutral"] += 1
            second_team_stats["neutral"] += 1

        first_player_stats = ensure_player(evt.first_player)
        second_player_stats = ensure_player(evt.second_player)

        first_player_stats["contests"] += 1
        first_player_stats["first_to_ball"] += 1
        first_player_stats["depth_sum"] += evt.depth_m
        first_player_stats["risk_sum"] += evt.risk_first
        first_player_stats["risk_count"] += 1

        second_player_stats["contests"] += 1
        second_player_stats["depth_sum"] += evt.depth_m
        second_player_stats["risk_sum"] += evt.risk_second
        second_player_stats["risk_count"] += 1

        if evt.outcome == "WIN":
            first_player_stats["wins"] += 1
            second_player_stats["losses"] += 1
        elif evt.outcome == "LOSS":
            first_player_stats["losses"] += 1
            second_player_stats["wins"] += 1
        else:
            first_player_stats["neutral"] += 1
            second_player_stats["neutral"] += 1

    def compose(stats: dict[str, Any]) -> dict[str, Any]:
        contests_val = stats.get("contests", 0)
        first_val = stats.get("first_to_ball", 0)
        depth_sum_val = stats.get("depth_sum", 0.0)
        risk_sum_val = stats.get("risk_sum", 0.0)
        risk_cnt_val = stats.get("risk_count", 0)
        first_pct = (first_val / contests_val * 100.0) if contests_val else 0.0
        depth_avg = (depth_sum_val / contests_val) if contests_val else 0.0
        risk_avg = (risk_sum_val / risk_cnt_val) if risk_cnt_val else 0.0
        return {
            "contests": contests_val,
            "wins": stats.get("wins", 0),
            "losses": stats.get("losses", 0),
            "neutral": stats.get("neutral", 0),
            "first_to_ball_pct": round(first_pct, 1),
            "challenge_depth_m": round(depth_avg, 2),
            "risk_index_avg": round(risk_avg, 2),
        }

    if player_id:
        return compose(player_stats.get(player_id, {}))

    if team:
        target_team = team.upper()
        return compose(team_stats.get(target_team, {}))

    return compose({})
