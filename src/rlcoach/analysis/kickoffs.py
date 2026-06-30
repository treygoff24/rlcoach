"""Kickoff analysis.

Aggregates kickoff events into schema-aligned metrics for teams and players.
Uses deterministic counting based on KickoffEvent fields; when extra details
are missing, returns zeros for those metrics.
"""

from __future__ import annotations

import bisect
from typing import Any

from ..events import GoalEvent, KickoffEvent
from ..parser.types import Frame, Header

APPROACH_KEYS = [
    "SPEEDFLIP",
    "STANDARD_FRONTFLIP",
    "STANDARD_DIAGONAL",
    "STANDARD_WAVEDASH",
    "STANDARD_BOOST",
    "DELAY",
    "FAKE_STATIONARY",
    "FAKE_HALFFLIP",
    "FAKE_AGGRESSIVE",
    "STANDARD",  # Generic fallback for backwards compatibility
    "UNKNOWN",
]

# A goal counts as scored "off the kickoff" only if it lands within this many
# seconds of the kickoff. Without the bound, every goal maps to some kickoff
# window (goals trigger kickoffs, so windows partition the match) and the metric
# collapses to the final scoreline instead of measuring kickoff conversions.
KICKOFF_GOAL_WINDOW_S = 10.0


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

    goals: list[GoalEvent] = []
    if events and isinstance(events.get("goals"), list):
        goals = list(events.get("goals", []))

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
            "approach_types": dict.fromkeys(APPROACH_KEYS, 0),
        }

    if not kickoffs:
        return empty_result()

    if player_id:
        player_team = player_team_name.get(player_id)
        return _analyze_kickoffs_for_player(kickoffs, player_id, player_team, goals)
    elif team:
        return _analyze_kickoffs_for_team(
            kickoffs, team.upper(), player_team_name, goals
        )
    else:
        return empty_result()


def _count_kickoff_goals(
    kickoffs: list[KickoffEvent],
    goals: list[GoalEvent],
    team_name: str | None,
    allowed_starts: set[float] | None = None,
) -> tuple[int, int]:
    """Attribute goals to kickoff windows and split by team.

    Each kickoff "owns" the window ``[t_start, next_t_start)`` (the final
    kickoff's window runs to ``+inf``). A goal is attributed to the single window
    whose ``t_start <= goal.t < next_t_start`` AND only when it lands within
    ``KICKOFF_GOAL_WINDOW_S`` seconds of that kickoff (a goal scored off the
    kickoff play, not minutes later). ``goals_for`` counts such goals scored by
    ``team_name``, ``goals_against`` counts the rest.

    ``kickoffs`` must be the full match list so each goal is attributed to its
    true owning kickoff. When ``allowed_starts`` is given (player scope), a goal
    only counts if its owning kickoff's ``t_start`` is in that set — i.e. the
    player was actually on that kickoff.
    """
    if not goals or not kickoffs or team_name is None:
        return 0, 0

    starts = sorted(ko.t_start for ko in kickoffs)

    goals_for = 0
    goals_against = 0
    for goal in goals:
        gt = goal.t
        gteam = goal.team
        if gt is None or gteam is None:
            continue
        # Window index = largest t_start <= gt. ``bisect_right - 1`` yields the
        # single owning window; a goal before the first kickoff maps to -1 and
        # is ignored. This counts each goal at most once.
        window_idx = bisect.bisect_right(starts, gt) - 1
        if window_idx < 0:
            continue
        owning_start = starts[window_idx]
        # Only goals shortly after the owning kickoff count as kickoff goals.
        if gt - owning_start > KICKOFF_GOAL_WINDOW_S:
            continue
        # Player scope: skip goals off kickoffs the player did not take part in.
        if allowed_starts is not None and owning_start not in allowed_starts:
            continue
        if gteam == team_name:
            goals_for += 1
        else:
            goals_against += 1
    return goals_for, goals_against


def _analyze_kickoffs_for_player(
    kickoffs: list[KickoffEvent],
    player_id: str,
    player_team: str | None,
    goals: list[GoalEvent],
) -> dict[str, Any]:
    count = 0
    first_possession = 0
    neutral = 0
    times: list[float] = []
    approach_types = dict.fromkeys(APPROACH_KEYS, 0)

    won_outcome = f"FIRST_POSSESSION_{player_team}" if player_team is not None else None

    participated: list[KickoffEvent] = []
    for ko in kickoffs:
        # Check if player participated
        pdata = None
        for entry in ko.players:
            if entry.get("player_id") == player_id:
                pdata = entry
                break
        if pdata is None:
            continue
        participated.append(ko)

        count += 1
        if ko.outcome == "NEUTRAL":
            neutral += 1

        # First possession: the player took the first touch and won it for their
        # own team (outcome matches FIRST_POSSESSION_<player's team>).
        if (
            won_outcome is not None
            and ko.first_touch_player == player_id
            and ko.outcome == won_outcome
        ):
            first_possession += 1

        # Time to first touch
        tft = pdata.get("time_to_first_touch")
        if isinstance(tft, (int, float)):
            times.append(float(tft))

        # Approach type
        at = pdata.get("approach_type", "UNKNOWN")
        if at not in approach_types:
            at = "UNKNOWN"
        approach_types[at] += 1

    # Window over the full kickoff list for correct attribution, but only credit
    # goals whose owning kickoff this player actually took part in.
    participated_starts = {ko.t_start for ko in participated}
    goals_for, goals_against = _count_kickoff_goals(
        kickoffs, goals, player_team, allowed_starts=participated_starts
    )

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
    kickoffs: list[KickoffEvent],
    team_name: str,
    player_team_name: dict[str, str],
    goals: list[GoalEvent],
) -> dict[str, Any]:
    count = len(kickoffs)
    first_possession = 0
    neutral = 0
    times: list[float] = []
    approach_types = dict.fromkeys(APPROACH_KEYS, 0)
    total_approaches = 0

    goals_for, goals_against = _count_kickoff_goals(kickoffs, goals, team_name)

    for ko in kickoffs:
        # First-possession outcomes for this team.
        if ko.outcome == "NEUTRAL":
            neutral += 1
        elif ko.outcome == "FIRST_POSSESSION_BLUE" and team_name == "BLUE":
            first_possession += 1
        elif ko.outcome == "FIRST_POSSESSION_ORANGE" and team_name == "ORANGE":
            first_possession += 1

        # Aggregate player stats for this team
        for entry in ko.players:
            pid = entry.get("player_id")
            if not pid:
                continue
            if player_team_name.get(pid) != team_name:
                continue
            total_approaches += 1
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
        "total_approaches": total_approaches,
    }
