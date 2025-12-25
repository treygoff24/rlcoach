"""Timeline aggregation for Rocket League replay events.

Builds a chronological timeline from all detected event types.
"""

from __future__ import annotations

from typing import Any

from .types import TimelineEvent


def build_timeline(events_dict: dict[str, list[Any]]) -> list[TimelineEvent]:
    """Build chronological timeline from all detected events.

    Args:
        events_dict: Dictionary of event type -> event list

    Returns:
        Sorted list of timeline events
    """
    timeline = []

    # Convert each event type to timeline entries
    for goals in events_dict.get("goals", []):
        timeline.append(
            TimelineEvent(
                t=goals.t,
                frame=goals.frame,
                type="GOAL",
                player_id=goals.scorer,
                team=goals.team,
                data={
                    "shot_speed_kph": goals.shot_speed_kph,
                    "distance_m": goals.distance_m,
                    "assist": goals.assist,
                },
            )
        )
        if goals.assist:
            timeline.append(
                TimelineEvent(
                    t=goals.t,
                    frame=goals.frame,
                    type="ASSIST",
                    player_id=goals.assist,
                    team=goals.team,
                    data={"scorer": goals.scorer},
                )
            )

    for demo in events_dict.get("demos", []):
        timeline.append(
            TimelineEvent(
                t=demo.t,
                type="DEMO",
                player_id=demo.victim,
                team=demo.team_victim,
                data={"attacker": demo.attacker, "location": demo.location},
            )
        )

    for kickoff in events_dict.get("kickoffs", []):
        timeline.append(
            TimelineEvent(
                t=kickoff.t_start,
                type="KICKOFF",
                data={
                    "phase": kickoff.phase,
                    "players": kickoff.players,
                    "outcome": kickoff.outcome,
                },
            )
        )

    for pickup in events_dict.get("boost_pickups", []):
        timeline.append(
            TimelineEvent(
                t=pickup.t,
                type="BOOST_PICKUP",
                player_id=pickup.player_id,
                data={
                    "pad_type": pickup.pad_type,
                    "stolen": pickup.stolen,
                    "location": pickup.location,
                },
            )
        )

    for touch in events_dict.get("touches", []):
        timeline.append(
            TimelineEvent(
                t=touch.t,
                frame=touch.frame,
                type="TOUCH",
                player_id=touch.player_id,
                data={
                    "location": touch.location,
                    "ball_speed_kph": touch.ball_speed_kph,
                    "outcome": touch.outcome,
                },
            )
        )

        if touch.outcome == "SHOT":
            timeline.append(
                TimelineEvent(
                    t=touch.t,
                    frame=touch.frame,
                    type="SHOT",
                    player_id=touch.player_id,
                    data={"ball_speed_kph": touch.ball_speed_kph},
                )
            )

        if touch.is_save:
            timeline.append(
                TimelineEvent(
                    t=touch.t,
                    frame=touch.frame,
                    type="SAVE",
                    player_id=touch.player_id,
                    data={"ball_speed_kph": touch.ball_speed_kph},
                )
            )

    for challenge in events_dict.get("challenges", []):
        timeline.append(
            TimelineEvent(
                t=challenge.t,
                type="CHALLENGE",
                player_id=challenge.first_player,
                team=challenge.first_team,
                data={
                    "second_player": challenge.second_player,
                    "winner_team": challenge.winner_team,
                    "outcome": challenge.outcome,
                    "depth_m": challenge.depth_m,
                    "duration_s": round(challenge.duration, 3),
                    "risk_first": round(challenge.risk_first, 3),
                    "risk_second": round(challenge.risk_second, 3),
                    "location": challenge.location,
                },
            )
        )

    # Sort chronologically, then by type for stable ordering
    timeline.sort(key=lambda e: (e.t, e.type))

    return timeline
