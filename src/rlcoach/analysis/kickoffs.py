"""Kickoff analysis.

Aggregates kickoff events into schema-aligned metrics for teams and players.
Uses deterministic counting based on KickoffEvent fields; when extra details
are missing, returns zeros for those metrics.
"""

from __future__ import annotations

from typing import Any

from ..parser.types import Header, Frame
from ..events import KickoffEvent


APPROACH_KEYS = ["STANDARD", "SPEEDFLIP", "FAKE", "DELAY", "UNKNOWN"]


def analyze_kickoffs(
    frames: list[Frame],
    events: dict[str, list[Any]] | None = None,
    player_id: str | None = None,
    team: str | None = None,
    header: Header | None = None,
) -> dict[str, Any]:
    """Analyze kickoff outcomes and approaches.

    Returns schema-aligned dict with:
      count, first_possession, neutral, goals_for, goals_against,
      avg_time_to_first_touch_s, approach_types
    """
    kickoffs: list[KickoffEvent] = []
    if events and isinstance(events.get("kickoffs"), list):
        kickoffs = list(events.get("kickoffs", []))

    # Player->team mapping
    player_team_name: dict[str, str] = {}
    for fr in frames:
        for p in fr.players:
            if p.player_id not in player_team_name:
                player_team_name[p.player_id] = "BLUE" if p.team == 0 else "ORANGE"

    def empty_result() -> dict[str, Any]:
        return {
            "count": 0,
            "first_possession": 0,
            "neutral": 0,
            "goals_for": 0,
            "goals_against": 0,
            "avg_time_to_first_touch_s": 0.0,
            "approach_types": {k: 0 for k in APPROACH_KEYS},
        }

    if not kickoffs:
        return empty_result()

    if player_id:
        return _analyze_kickoffs_for_player(kickoffs, player_id)
    elif team:
        return _analyze_kickoffs_for_team(kickoffs, team.upper(), player_team_name)
    else:
        return empty_result()


def _analyze_kickoffs_for_player(kickoffs: list[KickoffEvent], player_id: str) -> dict[str, Any]:
    count = 0
    first_possession = 0
    neutral = 0
    goals_for = 0
    goals_against = 0
    times: list[float] = []
    approach_types = {k: 0 for k in APPROACH_KEYS}

    # Player team inferred from events' outcome text is not possible; keep goals_* = 0
    for ko in kickoffs:
        # Check if player participated
        pdata = None
        for entry in ko.players:
            if entry.get("player_id") == player_id:
                pdata = entry
                break
        if pdata is None:
            continue

        count += 1
        if ko.outcome == "NEUTRAL":
            neutral += 1

        # First possession: attribute if outcome matches player's team; unavailable -> skip
        # Without team link in event, we cannot resolve — leave 0 by default

        # Time to first touch
        tft = pdata.get("time_to_first_touch")
        if isinstance(tft, (int, float)):
            times.append(float(tft))

        # Approach type
        at = pdata.get("approach_type", "UNKNOWN")
        if at not in approach_types:
            at = "UNKNOWN"
        approach_types[at] += 1

    avg_time = sum(times) / len(times) if times else 0.0
    return {
        "count": count,
        "first_possession": first_possession,
        "neutral": neutral,
        "goals_for": goals_for,
        "goals_against": goals_against,
        "avg_time_to_first_touch_s": round(avg_time, 2),
        "approach_types": approach_types,
    }


def _analyze_kickoffs_for_team(
    kickoffs: list[KickoffEvent], team_name: str, player_team_name: dict[str, str]
) -> dict[str, Any]:
    count = len(kickoffs)
    first_possession = 0
    neutral = 0
    goals_for = 0
    goals_against = 0
    times: list[float] = []
    approach_types = {k: 0 for k in APPROACH_KEYS}

    for ko in kickoffs:
        # Outcomes
        if ko.outcome == "NEUTRAL":
            neutral += 1
        elif ko.outcome == "FIRST_POSSESSION_BLUE" and team_name == "BLUE":
            first_possession += 1
        elif ko.outcome == "FIRST_POSSESSION_ORANGE" and team_name == "ORANGE":
            first_possession += 1
        elif ko.outcome == "GOAL_FOR":
            # No team context — cannot attribute
            pass
        elif ko.outcome == "GOAL_AGAINST":
            pass

        # Aggregate player stats for this team
        for entry in ko.players:
            pid = entry.get("player_id")
            if not pid:
                continue
            if player_team_name.get(pid) != team_name:
                continue
            tft = entry.get("time_to_first_touch")
            if isinstance(tft, (int, float)):
                times.append(float(tft))
            at = entry.get("approach_type", "UNKNOWN")
            if at not in approach_types:
                at = "UNKNOWN"
            approach_types[at] += 1

    avg_time = sum(times) / len(times) if times else 0.0
    return {
        "count": count,
        "first_possession": first_possession,
        "neutral": neutral,
        "goals_for": goals_for,
        "goals_against": goals_against,
        "avg_time_to_first_touch_s": round(avg_time, 2),
        "approach_types": approach_types,
    }

