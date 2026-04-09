"""Demolition detection for Rocket League replays.

Detects player demolition events from state transitions.
"""

from __future__ import annotations

from ..parser.types import Frame
from .constants import DEMO_POSITION_TOLERANCE
from .types import DemoEvent
from .utils import distance_3d


def detect_demos(frames: list[Frame]) -> list[DemoEvent]:
    """Detect demolition events from player state transitions.

    Args:
        frames: Normalized frame data

    Returns:
        List of detected demo events
    """
    if not frames:
        return []

    parser_demos = _demos_from_parser_events(frames)
    if parser_demos:
        return parser_demos

    demos = []
    previous_demo_states = {}  # Track player demolition states

    for frame in frames:
        for player in frame.players:
            player_id = player.player_id
            was_demolished = previous_demo_states.get(player_id, False)
            is_demolished = player.is_demolished

            # Detect demolition state transition (False -> True)
            if not was_demolished and is_demolished:
                # Find potential attacker - nearest enemy player
                attacker = None
                attacker_team = None
                min_distance = float("inf")

                for other_player in frame.players:
                    if (
                        other_player.player_id != player_id
                        and other_player.team != player.team
                        and not other_player.is_demolished
                    ):
                        distance = distance_3d(player.position, other_player.position)
                        if (
                            distance < DEMO_POSITION_TOLERANCE
                            and distance < min_distance
                        ):
                            min_distance = distance
                            attacker = other_player.player_id
                            attacker_team = (
                                "BLUE" if other_player.team == 0 else "ORANGE"
                            )

                victim_team = "BLUE" if player.team == 0 else "ORANGE"

                demo = DemoEvent(
                    t=frame.timestamp,
                    victim=player_id,
                    attacker=attacker,
                    team_attacker=attacker_team,
                    team_victim=victim_team,
                    location=player.position,
                    source="inferred",
                )
                demos.append(demo)

            # Update state tracking
            previous_demo_states[player_id] = is_demolished

    return demos


def _demos_from_parser_events(frames: list[Frame]) -> list[DemoEvent]:
    """Convert parser-emitted demo lists into event-layer DemoEvent objects."""
    converted: list[DemoEvent] = []
    seen: set[tuple[float, str]] = set()
    for frame in frames:
        for event in getattr(frame, "parser_demo_events", []) or []:
            victim = event.victim_id
            key = (round(float(event.timestamp), 4), victim)
            if key in seen:
                continue
            seen.add(key)
            team_victim = (
                "BLUE"
                if event.victim_team == 0
                else "ORANGE" if event.victim_team == 1 else None
            )
            team_attacker = (
                "BLUE"
                if event.attacker_team == 0
                else "ORANGE" if event.attacker_team == 1 else None
            )
            victim_position = next(
                (
                    player.position
                    for player in frame.players
                    if player.player_id == victim
                ),
                None,
            )
            converted.append(
                DemoEvent(
                    t=float(event.timestamp),
                    victim=victim,
                    attacker=event.attacker_id,
                    team_attacker=team_attacker,
                    team_victim=team_victim,
                    location=victim_position,
                    source=event.source or "parser",
                )
            )
    converted.sort(key=lambda demo: demo.t)
    return converted
