"""Event detection and timeline aggregation for Rocket League replays.

This module identifies significant game events from normalized frame data:
- Goals: Ball crossing goal line with scorer attribution
- Demos: Player demolition events with attacker tracking
- Kickoffs: Match start and overtime kickoff detection
- Boost pickups: Player boost collection with pad classification
- Touches: Player-ball contact events with outcome classification

All detection uses deterministic thresholds and graceful degradation.
"""

from __future__ import annotations

import json
import math
import os
from collections import deque
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Any

from .field_constants import FIELD, Vec3, BoostPad
from .normalize import measure_frame_rate
from .parser.types import Header, Frame, PlayerFrame, BallFrame
from .physics_constants import UU_S_TO_KPH
from .utils.identity import build_alias_lookup, build_player_identities, sanitize_display_name


# Detection thresholds - explicitly documented
GOAL_LINE_THRESHOLD = FIELD.BACK_WALL_Y - FIELD.GOAL_DEPTH  # Front plane of goal
GOAL_EXIT_THRESHOLD = GOAL_LINE_THRESHOLD - 200.0
BALL_STATIONARY_THRESHOLD = 50.0  # Ball speed for kickoff detection (units/s)
TOUCH_PROXIMITY_THRESHOLD = 200.0  # Distance for player-ball contact (units)
DEMO_POSITION_TOLERANCE = 500.0  # Max distance for demo attacker detection (units)
BOOST_PICKUP_MIN_GAIN = 1.0  # Minimum net gain to record a pickup event
CENTERLINE_TOLERANCE = 1200.0  # Within this Y range is considered neutral half
PAD_NEUTRAL_TOLERANCE = 1200.0
RESPAWN_BOOST_AMOUNT = 33.0
RESPAWN_DISTANCE_THRESHOLD = 800.0
CHAIN_PAD_RADIUS = 1500.0

# Boost pickup heuristics (aligned with Ballchasing parity harness)
BOOST_HISTORY_WINDOW_S = 0.45
BOOST_HISTORY_MAX_SAMPLES = 18
BIG_PAD_EXTRA_RADIUS = 220.0
SMALL_PAD_EXTRA_RADIUS = 140.0
BIG_PAD_RESPAWN_S = 10.0
SMALL_PAD_RESPAWN_S = 4.0
PAD_RESPAWN_TOLERANCE = 0.15
BOOST_PICKUP_MERGE_WINDOW = 0.6
DEBUG_BOOST_ENV = "RLCOACH_DEBUG_BOOST_EVENTS"
BIG_PAD_MIN_GAIN = 70.0

# Kickoff heuristics
KICKOFF_CENTER_POSITION = Vec3(0.0, 0.0, 93.15)
KICKOFF_POSITION_TOLERANCE = 120.0
KICKOFF_MAX_DURATION = 5.0
KICKOFF_MIN_COOLDOWN = 5.0

# Challenge detection heuristics (shared with analyzers)
CHALLENGE_WINDOW_S = 1.2
CHALLENGE_RADIUS_UU = 1000.0
CHALLENGE_MIN_DISTANCE_UU = 200.0
CHALLENGE_MIN_BALL_SPEED_KPH = 15.0
NEUTRAL_RETOUCH_WINDOW_S = 0.25

RISK_LOW_BOOST_THRESHOLD = 20
RISK_AHEAD_OF_BALL_WEIGHT = 0.4
RISK_LOW_BOOST_WEIGHT = 0.3
RISK_LAST_MAN_WEIGHT = 0.3


@dataclass(frozen=True)
class GoalEvent:
    """Goal event with scorer and shot metrics."""
    
    t: float  # Timestamp from match start
    frame: int | None = None
    scorer: str | None = None  # Player ID who scored
    team: str | None = None  # "BLUE" or "ORANGE"
    assist: str | None = None  # Player ID with assist
    shot_speed_kph: float = 0.0
    distance_m: float = 0.0
    on_target: bool = True
    tickmark_lead_seconds: float = 0.0


@dataclass(frozen=True)
class DemoEvent:
    """Demolition event with victim and attacker."""
    
    t: float
    victim: str
    attacker: str | None = None
    team_attacker: str | None = None  # "BLUE" or "ORANGE"
    team_victim: str | None = None
    location: Vec3 | None = None


@dataclass(frozen=True)  
class KickoffEvent:
    """Kickoff event with player analysis."""
    
    phase: str  # "INITIAL" or "OT"
    t_start: float
    players: list[dict[str, Any]]  # Player kickoff analysis
    outcome: str = "NEUTRAL"  # Simplified outcome
    first_touch_player: str | None = None
    time_to_first_touch: float | None = None


@dataclass(frozen=True)
class BoostPickupEvent:
    """Boost pad pickup event."""
    
    t: float
    player_id: str
    pad_type: str  # "SMALL" or "BIG"
    stolen: bool = False  # True if on opponent half
    pad_id: int = -1  # Index in boost pad arrays
    location: Vec3 | None = None
    frame: int | None = None
    boost_before: float | None = None
    boost_after: float | None = None
    boost_gain: float = 0.0


@dataclass
class PadState:
    """Runtime tracking for boost pad availability."""

    available_at: float = 0.0
    last_pickup: float | None = None


@dataclass(frozen=True)
class PadEnvelope:
    """Spatial heuristics for matching a player to a boost pad."""

    radius: float
    max_distance: float
    height_tolerance: float


PAD_ENVELOPES: dict[int, PadEnvelope] = {}
for pad in FIELD.BOOST_PADS:
    base_radius = pad.radius + (BIG_PAD_EXTRA_RADIUS if pad.is_big else SMALL_PAD_EXTRA_RADIUS)
    height_tol = 220.0 if pad.is_big else 150.0
    max_distance = base_radius + (650.0 if pad.is_big else 420.0)
    PAD_ENVELOPES[pad.pad_id] = PadEnvelope(radius=base_radius, max_distance=max_distance, height_tolerance=height_tol)


class TouchContext(Enum):
    """Context of a ball touch based on car state."""
    GROUND = "ground"       # Car on ground when touching ball
    AERIAL = "aerial"       # Car in air, ball also elevated
    WALL = "wall"           # Car on/near wall when hitting ball
    CEILING = "ceiling"     # Car on ceiling
    HALF_VOLLEY = "half_volley"  # Just left ground (jumping touch)
    UNKNOWN = "unknown"


# Touch context detection thresholds
WALL_PROXIMITY_THRESHOLD = 150.0  # Distance from wall to consider wall touch
CEILING_HEIGHT_THRESHOLD = 1900.0  # Height to consider ceiling touch
AERIAL_HEIGHT_THRESHOLD = 300.0  # Height to consider aerial touch
HALF_VOLLEY_HEIGHT = 100.0  # Height for half volley detection


@dataclass(frozen=True)
class TouchEvent:
    """Player-ball contact event."""

    t: float
    player_id: str
    location: Vec3
    frame: int | None = None
    ball_speed_kph: float = 0.0
    outcome: str = "NEUTRAL"  # Simplified classification
    is_save: bool = False
    touch_context: TouchContext = TouchContext.UNKNOWN
    car_height: float = 0.0
    is_first_touch: bool = False


@dataclass(frozen=True)
class ChallengeEvent:
    """50/50 contest event between opposing players."""

    t: float
    first_player: str
    second_player: str
    first_team: str
    second_team: str
    outcome: str  # Perspective of first player: WIN/LOSS/NEUTRAL
    winner_team: str | None
    location: Vec3
    depth_m: float
    duration: float
    risk_first: float
    risk_second: float


@dataclass(frozen=True)
class TimelineEvent:
    """Timeline entry for chronological event aggregation."""
    
    t: float
    type: str  # Event type from schema enum
    frame: int | None = None
    player_id: str | None = None
    team: str | None = None
    data: dict[str, Any] | None = None


def detect_boost_pickups(frames: list[Frame]) -> list[BoostPickupEvent]:
    """Detect boost pickups, preferring parser-provided pad events when available."""

    if not frames:
        return []

    pickups: list[BoostPickupEvent] = []

    if _frames_have_pad_events(frames):
        try:
            pad_event_results = _detect_boost_pickups_from_pad_events(frames)
            if pad_event_results:
                pickups = pad_event_results
                return _merge_pickup_events(pickups)
        except Exception:
            # Fall back to legacy heuristics if parsing fails for any reason.
            pass

    pickups = _detect_boost_pickups_legacy(frames)
    return _merge_pickup_events(pickups)


def _frames_have_pad_events(frames: list[Frame]) -> bool:
    """Return True if any frame includes boost pad events from the parser."""

    for frame in frames:
        events = getattr(frame, "boost_pad_events", None)
        if events:
            return True
    return False


def _detect_boost_pickups_from_pad_events(frames: list[Frame]) -> list[BoostPickupEvent]:
    """Compute boost pickups directly from pad replication events."""

    pickups: list[BoostPickupEvent] = []
    team_sides = determine_team_sides(frames)
    player_boost: dict[str, float] = {}
    pad_last_collect: dict[int, float] = {}

    for frame_index, frame in enumerate(frames):
        frame_events = getattr(frame, "boost_pad_events", [])
        if not frame_events:
            for player in frame.players:
                player_boost[player.player_id] = float(player.boost_amount)
            continue

        players_by_id = {player.player_id: player for player in frame.players}
        for event in frame_events:
            status = getattr(event, "status", "").upper()
            pad_index = getattr(event, "pad_id", None)
            if status == "RESPAWNED":
                continue
            if status != "COLLECTED":
                continue

            if pad_index is None or pad_index < 0 or pad_index >= len(FIELD.BOOST_PADS):
                continue
            pad_meta = FIELD.BOOST_PADS[pad_index]

            player_id = getattr(event, "player_id", None)
            if player_id is None and getattr(event, "player_index", None) is not None:
                candidate = f"player_{event.player_index}"
                if candidate in players_by_id:
                    player_id = candidate
            if player_id is None:
                raise ValueError(
                    "Missing player attribution for boost pad event; falling back to legacy detection"
                )

            player_frame = players_by_id.get(player_id)
            player_team = getattr(event, "player_team", None)
            if player_team not in (0, 1) and player_frame is not None:
                player_team = player_frame.team

            event_time = getattr(event, "timestamp", None)
            timestamp = float(event_time) if event_time is not None else frame.timestamp

            respawn_window = BIG_PAD_RESPAWN_S if pad_meta.is_big else SMALL_PAD_RESPAWN_S
            last_collect = pad_last_collect.get(pad_meta.pad_id)
            if last_collect is not None and (timestamp - last_collect) < (respawn_window - PAD_RESPAWN_TOLERANCE):
                continue

            previous_boost = player_boost.get(player_id)
            current_boost = float(player_frame.boost_amount) if player_frame is not None else None
            pad_capacity = 100.0 if pad_meta.is_big else 12.0

            boost_before = previous_boost
            boost_after = current_boost

            if boost_before is None and boost_after is not None:
                boost_before = max(0.0, boost_after - pad_capacity)
            if boost_after is None and boost_before is not None:
                boost_after = min(100.0, boost_before + pad_capacity)
            if boost_before is None:
                boost_before = 0.0
            available_room = max(0.0, 100.0 - boost_before)
            if boost_after is None:
                if available_room > 0.5:
                    boost_after = min(100.0, boost_before + min(pad_capacity, available_room))
                else:
                    boost_after = boost_before

            boost_gain = max(0.0, boost_after - boost_before)
            if boost_gain < 0.5:
                if available_room > 0.5:
                    expected_gain = min(pad_capacity, available_room)
                    boost_gain = expected_gain
                    boost_after = min(100.0, boost_before + boost_gain)
                else:
                    boost_gain = 0.0
                    boost_after = boost_before

            stolen = _is_stolen_pad(pad_meta, player_team, team_sides)

            pickups.append(
                BoostPickupEvent(
                    t=timestamp,
                    player_id=player_id,
                    pad_type="BIG" if pad_meta.is_big else "SMALL",
                    stolen=stolen,
                    pad_id=pad_meta.pad_id,
                    location=pad_meta.position,
                    frame=frame_index,
                    boost_before=round(boost_before, 3),
                    boost_after=round(boost_after, 3),
                    boost_gain=round(boost_gain, 3),
                )
            )

            player_boost[player_id] = boost_after
            pad_last_collect[pad_meta.pad_id] = timestamp

        for player in frame.players:
            player_boost[player.player_id] = float(player.boost_amount)

    pickups.sort(key=lambda evt: evt.t)
    return pickups


def detect_goals(frames: list[Frame], header: Header | None = None) -> list[GoalEvent]:
    """Detect goal events, preferring authoritative header metadata."""

    if not frames:
        return []

    if header is not None and getattr(header, "goals", []):
        return _detect_goals_from_header(frames, header)

    return _detect_goals_from_ball_path(frames, header)


def _detect_goals_from_header(frames: list[Frame], header: Header) -> list[GoalEvent]:
    """Build goal events using authoritative header goal frames."""

    identities = build_player_identities(getattr(header, "players", []))
    alias_lookup = build_alias_lookup(identities)
    name_lookup = {
        sanitize_display_name(getattr(header.players[identity.header_index], "name", "")).lower(): identity.canonical_id
        for identity in identities
    }

    header_goals = list(getattr(header, "goals", []) or [])
    highlight_frames = [
        int(h.frame)
        for h in getattr(header, "highlights", [])
        if getattr(h, "frame", None) is not None
    ]

    frame_rate = measure_frame_rate(frames) if frames else 30.0
    goals: list[GoalEvent] = []
    last_touch_by_player: dict[str, PlayerFrame] = {}
    last_touch_times: dict[str, float] = {}
    goal_index = 0

    for i, frame in enumerate(frames):
        # Track recent touches to attribute assists.
        for player in frame.players:
            raw_id = getattr(player, "player_id", None)
            if raw_id is None:
                continue
            pid = alias_lookup.get(raw_id, raw_id)
            alias_lookup.setdefault(raw_id, pid)
            distance = _distance_3d(player.position, frame.ball.position)
            if distance < TOUCH_PROXIMITY_THRESHOLD:
                last_touch_by_player[pid] = player
                last_touch_times[pid] = frame.timestamp

        while goal_index < len(header_goals):
            target_frame_val = getattr(header_goals[goal_index], "frame", None)
            if target_frame_val is None:
                break
            try:
                target_frame = int(target_frame_val)
            except (TypeError, ValueError):
                break

            if i < target_frame:
                break

            frame_ref_idx = min(max(target_frame, 0), len(frames) - 1) if frames else 0
            frame_ref = frames[frame_ref_idx] if frames else None
            goal_time = (
                frame_ref.timestamp
                if frame_ref is not None
                else ((target_frame / frame_rate) if frame_rate > 0 else 0.0)
            )

            scorer_team = _team_name(getattr(header_goals[goal_index], "player_team", None))
            scorer = _resolve_goal_scorer(header_goals[goal_index], identities, name_lookup, scorer_team)
            assist = _resolve_recent_assist(
                last_touch_times,
                last_touch_by_player,
                scorer,
                scorer_team,
                goal_time,
            )

            ball_velocity = frame_ref.ball.velocity if frame_ref else Vec3(0.0, 0.0, 0.0)
            ball_pos = frame_ref.ball.position if frame_ref else Vec3(0.0, 0.0, 0.0)
            goal_line_y = FIELD.BACK_WALL_Y if scorer_team == "BLUE" else -FIELD.BACK_WALL_Y
            distance_m = abs(goal_line_y - ball_pos.y) / 100.0
            shot_speed_kph = _vector_magnitude(ball_velocity) * 3.6

            highlight_frame = highlight_frames[goal_index] if goal_index < len(highlight_frames) else None
            tickmark_lead = 0.0
            if highlight_frame is not None and frame_rate > 0:
                delta_frames = max(0, target_frame - highlight_frame)
                tickmark_lead = delta_frames / frame_rate

            goals.append(
                GoalEvent(
                    t=goal_time,
                    frame=target_frame,
                    scorer=scorer,
                    team=scorer_team,
                    assist=assist,
                    shot_speed_kph=shot_speed_kph,
                    distance_m=distance_m,
                    on_target=scorer is not None,
                    tickmark_lead_seconds=round(tickmark_lead, 3),
                )
            )
            goal_index += 1

        if goal_index >= len(header_goals):
            break

    # Handle any goals with frame indices beyond the normalized frame list.
    while goal_index < len(header_goals):
        gh = header_goals[goal_index]
        try:
            frame_idx = int(getattr(gh, "frame", len(frames) - 1))
        except (TypeError, ValueError):
            frame_idx = len(frames) - 1

        frame_ref_idx = min(max(frame_idx, 0), len(frames) - 1) if frames else 0
        frame_ref = frames[frame_ref_idx] if frames else None
        goal_time = (
            frame_ref.timestamp
            if frame_ref is not None
            else ((frame_idx / frame_rate) if frame_rate > 0 else 0.0)
        )
        scorer_team = _team_name(getattr(gh, "player_team", None))
        scorer = _resolve_goal_scorer(gh, identities, name_lookup, scorer_team)

        highlight_frame = highlight_frames[goal_index] if goal_index < len(highlight_frames) else None
        tickmark_lead = 0.0
        if highlight_frame is not None and frame_rate > 0:
            delta_frames = max(0, frame_idx - highlight_frame)
            tickmark_lead = delta_frames / frame_rate

        ball_velocity = frame_ref.ball.velocity if frame_ref else Vec3(0.0, 0.0, 0.0)
        ball_pos = frame_ref.ball.position if frame_ref else Vec3(0.0, 0.0, 0.0)
        goal_line_y = FIELD.BACK_WALL_Y if scorer_team == "BLUE" else -FIELD.BACK_WALL_Y
        distance_m = abs(goal_line_y - ball_pos.y) / 100.0

        goals.append(
            GoalEvent(
                t=goal_time,
                frame=frame_idx if frame_idx >= 0 else None,
                scorer=scorer,
                team=scorer_team,
                assist=None,
                shot_speed_kph=_vector_magnitude(ball_velocity) * 3.6,
                distance_m=distance_m,
                on_target=scorer is not None,
                tickmark_lead_seconds=round(tickmark_lead, 3),
            )
        )
        goal_index += 1

    return goals


def _resolve_goal_scorer(goal_header: Any, identities: list[Any], name_lookup: dict[str, str], team: str | None) -> str | None:
    """Resolve scorer ID using header metadata and identity lookup."""
    name_token = sanitize_display_name(getattr(goal_header, "player_name", None)).lower()
    if name_token and name_token in name_lookup:
        return name_lookup[name_token]

    if team:
        for identity in identities:
            if identity.team == team:
                return identity.canonical_id
    return None


def _resolve_recent_assist(
    last_touch_times: dict[str, float],
    last_touch_by_player: dict[str, PlayerFrame],
    scorer: str | None,
    scorer_team: str | None,
    goal_time: float,
) -> str | None:
    """Pick the most recent teammate touch (excluding scorer) within a short window."""
    if scorer_team is None:
        return None

    candidates: list[tuple[float, str]] = []
    for pid, touch_time in last_touch_times.items():
        if pid == scorer:
            continue
        frame = last_touch_by_player.get(pid)
        if frame is None:
            continue
        if _team_name(frame.team) != scorer_team:
            continue
        if goal_time - touch_time <= 6.0:
            candidates.append((touch_time, pid))

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _detect_goals_from_ball_path(frames: list[Frame], header: Header | None) -> list[GoalEvent]:
    """Fallback goal detection using ball travel across goal lines."""

    goals = []
    last_touch_by_player = {}  # Track last player to touch ball
    last_touch_times = {}

    header_goal_frames: list[int] = []
    highlight_frames: list[int] = []
    if header is not None:
        header_goal_frames = [
            int(g.frame) for g in getattr(header, "goals", []) if getattr(g, "frame", None) is not None
        ]
        highlight_frames = [
            int(h.frame)
            for h in getattr(header, "highlights", [])
            if getattr(h, "frame", None) is not None
        ]

    frame_rate = measure_frame_rate(frames) if frames else 30.0
    goal_index = 0

    ball_inside_goal: str | None = None

    for i, frame in enumerate(frames):
        ball_y = frame.ball.position.y

        # Update last touch tracking when ball is in the field of play.
        if abs(ball_y) <= GOAL_LINE_THRESHOLD:
            for player in frame.players:
                distance = _distance_3d(player.position, frame.ball.position)
                if distance < TOUCH_PROXIMITY_THRESHOLD:
                    last_touch_by_player[player.player_id] = player
                    last_touch_times[player.player_id] = frame.timestamp

        # Determine whether ball currently resides inside a goal volume.
        goal_team: str | None = None
        if ball_y > GOAL_LINE_THRESHOLD:
            goal_team = "BLUE"
        elif ball_y < -GOAL_LINE_THRESHOLD:
            goal_team = "ORANGE"

        # Reset goal gating once the ball fully leaves the goal.
        if goal_team is None and ball_inside_goal is not None and abs(ball_y) <= GOAL_EXIT_THRESHOLD:
            ball_inside_goal = None

        if goal_team is not None and ball_inside_goal is None:
            ball_inside_goal = goal_team

            scorer = None
            assist = None
            if last_touch_by_player:
                recent_touches = [
                    (pid, last_touch_times.get(pid, 0.0))
                    for pid in last_touch_by_player.keys()
                    if frame.timestamp - last_touch_times.get(pid, 0.0) < 5.0
                ]
                if recent_touches:
                    recent_touches.sort(key=lambda x: x[1], reverse=True)
                    scorer = recent_touches[0][0]
                    for pid, _t in recent_touches[1:]:
                        if pid != scorer:
                            assist = pid
                            break

            ball_speed = _vector_magnitude(frame.ball.velocity)
            shot_speed_kph = ball_speed * 3.6

            goal_line_y = GOAL_LINE_THRESHOLD if goal_team == "BLUE" else -GOAL_LINE_THRESHOLD
            distance_m = abs(ball_y - goal_line_y) / 100.0

            header_goal_frame = (
                header_goal_frames[goal_index]
                if goal_index < len(header_goal_frames)
                else None
            )
            highlight_frame = (
                highlight_frames[goal_index]
                if goal_index < len(highlight_frames)
                else None
            )

            goal_frame_reference = header_goal_frame if header_goal_frame is not None else i
            tickmark_lead = 0.0
            if (
                highlight_frame is not None
                and frame_rate > 0
                and goal_frame_reference is not None
            ):
                delta_frames = max(0, goal_frame_reference - highlight_frame)
                tickmark_lead = delta_frames / frame_rate

            goal = GoalEvent(
                t=frame.timestamp,
                frame=i,
                scorer=scorer,
                team=goal_team,
                assist=assist,
                shot_speed_kph=shot_speed_kph,
                distance_m=distance_m,
                on_target=scorer is not None,
                tickmark_lead_seconds=round(tickmark_lead, 3),
            )
            goals.append(goal)
            goal_index += 1

            last_touch_by_player.clear()
            last_touch_times.clear()

    return goals


def detect_demos(frames: list[Frame]) -> list[DemoEvent]:
    """Detect demolition events from player state transitions.
    
    Args:
        frames: Normalized frame data
        
    Returns:
        List of detected demo events
    """
    if not frames:
        return []
    
    demos = []
    previous_demo_states = {}  # Track player demolition states
    
    for i, frame in enumerate(frames):
        for player in frame.players:
            player_id = player.player_id
            was_demolished = previous_demo_states.get(player_id, False)
            is_demolished = player.is_demolished
            
            # Detect demolition state transition (False -> True)
            if not was_demolished and is_demolished:
                # Find potential attacker - nearest enemy player
                attacker = None
                attacker_team = None
                min_distance = float('inf')
                
                for other_player in frame.players:
                    if (other_player.player_id != player_id and 
                        other_player.team != player.team and
                        not other_player.is_demolished):
                        
                        distance = _distance_3d(player.position, other_player.position)
                        if distance < DEMO_POSITION_TOLERANCE and distance < min_distance:
                            min_distance = distance
                            attacker = other_player.player_id
                            attacker_team = "BLUE" if other_player.team == 0 else "ORANGE"
                
                victim_team = "BLUE" if player.team == 0 else "ORANGE"
                
                demo = DemoEvent(
                    t=frame.timestamp,
                    victim=player_id,
                    attacker=attacker,
                    team_attacker=attacker_team,
                    team_victim=victim_team,
                    location=player.position
                )
                demos.append(demo)
            
            # Update state tracking
            previous_demo_states[player_id] = is_demolished
    
    return demos


def detect_kickoffs(frames: list[Frame], header: Header | None = None) -> list[KickoffEvent]:
    """Detect kickoff events with enriched per-player metrics.

    The detector tracks the full kickoff window (ball at center → first
    significant movement) and records:
    - Player roles (GO/CHEAT/WING/BACK) inferred from spawn positions
    - Boost consumption prior to the first meaningful action
    - Time-to-first-touch per player and overall first possession outcome
    """

    if not frames:
        return []

    kickoffs: list[KickoffEvent] = []
    kickoff_state: dict[str, Any] | None = None
    last_kickoff_end_time = -KICKOFF_MIN_COOLDOWN

    for frame in frames:
        ball = frame.ball

        at_center = (
            abs(ball.position.x - KICKOFF_CENTER_POSITION.x) <= KICKOFF_POSITION_TOLERANCE
            and abs(ball.position.y - KICKOFF_CENTER_POSITION.y) <= KICKOFF_POSITION_TOLERANCE
            and abs(ball.position.z - KICKOFF_CENTER_POSITION.z) <= 60.0
        )
        ball_speed = _vector_magnitude(ball.velocity)
        is_stationary = ball_speed < BALL_STATIONARY_THRESHOLD

        # Start a new kickoff window when the ball is reset to centre and the
        # previous kickoff has fully completed.
        if (
            kickoff_state is None
            and at_center
            and is_stationary
            and (frame.timestamp - last_kickoff_end_time) >= KICKOFF_MIN_COOLDOWN
        ):
            kickoff_state = _start_kickoff(frame)
            continue

        if kickoff_state is None:
            continue

        _update_kickoff_state(kickoff_state, frame)

        elapsed = frame.timestamp - kickoff_state["t_start"]
        ball_left_center = not at_center or ball_speed > BALL_STATIONARY_THRESHOLD * 1.5
        duration_exceeded = elapsed >= KICKOFF_MAX_DURATION

        if ball_left_center or duration_exceeded:
            kickoff_event = _finalize_kickoff(kickoff_state, frame, header)
            if kickoff_event is not None:
                kickoffs.append(kickoff_event)
                last_kickoff_end_time = frame.timestamp
            kickoff_state = None

    # Handle dangling kickoff if replay ends while still at center
    if kickoff_state is not None:
        kickoff_event = _finalize_kickoff(kickoff_state, frames[-1], header)
        if kickoff_event is not None:
            kickoffs.append(kickoff_event)

    return kickoffs


def _detect_boost_pickups_legacy(frames: list[Frame]) -> list[BoostPickupEvent]:
    """Legacy heuristic detection of boost pickup events from boost deltas.
    
    Args:
        frames: Normalized frame data
        
    Returns:
        List of detected boost pickup events
    """
    if not frames:
        return []

    pickups: list[BoostPickupEvent] = []
    player_state: dict[str, dict[str, Any]] = {}
    recent_pickup_index: dict[tuple[str, int], tuple[int, float]] = {}
    pad_states: dict[int, PadState] = {pad.pad_id: PadState() for pad in FIELD.BOOST_PADS}
    team_sides = determine_team_sides(frames)

    pads_by_id: dict[int, BoostPad] = {pad.pad_id: pad for pad in FIELD.BOOST_PADS}
    debug_sink = os.environ.get(DEBUG_BOOST_ENV)
    debug_records: list[dict[str, Any]] | None = [] if debug_sink else None

    for frame_index, frame in enumerate(frames):
        frame_time = frame.timestamp
        for player in frame.players:
            player_id = player.player_id
            current_boost = float(player.boost_amount)
            state = player_state.setdefault(
                player_id,
                {
                    "boost": None,
                    "history": deque(maxlen=BOOST_HISTORY_MAX_SAMPLES),
                    "team": player.team,
                    "was_demolished": False,
                    "skip_respawn_gain": False,
                },
            )

            history: deque[tuple[float, Vec3]] = state["history"]
            history.append((frame_time, player.position))
            while history and frame_time - history[0][0] > BOOST_HISTORY_WINDOW_S:
                history.popleft()

            previous_boost = state["boost"]
            was_demolished = state.get("was_demolished", False)
            skip_respawn_gain = state.get("skip_respawn_gain", False)
            is_demolished = bool(getattr(player, "is_demolished", False))

            if is_demolished:
                state["was_demolished"] = True
                state["skip_respawn_gain"] = True
            elif was_demolished:
                state["was_demolished"] = False
                state["skip_respawn_gain"] = True

            if previous_boost is None:
                state["boost"] = current_boost
                state["team"] = player.team
                continue

            boost_increase = current_boost - previous_boost

            if abs(boost_increase - RESPAWN_BOOST_AMOUNT) <= 2.0:
                nearest_dist = _nearest_pad_distance(history)
                if nearest_dist > RESPAWN_DISTANCE_THRESHOLD:
                    state["boost"] = current_boost
                    state["team"] = player.team
                    continue

            if skip_respawn_gain and boost_increase > 0 and current_boost <= 35.0:
                state["skip_respawn_gain"] = False
                state["boost"] = current_boost
                state["team"] = player.team
                continue
            if skip_respawn_gain and boost_increase <= 0:
                # Still waiting for respawn fill; keep flag until boost rises.
                state["boost"] = current_boost
                state["team"] = player.team
                continue
            state["skip_respawn_gain"] = False
            if boost_increase >= BOOST_PICKUP_MIN_GAIN:
                matched_pad, decision_debug = _select_boost_pad(
                    history,
                    previous_boost,
                    boost_increase,
                    pad_states,
                    frame_time,
                )
                if matched_pad is None:
                    matched_pad, fallback_debug = _fallback_nearest_pad(
                        history,
                        pads_by_id,
                        pad_states,
                        frame_time,
                        boost_increase,
                    )
                    decision_debug.setdefault("fallback", fallback_debug)

                pad_events: list[BoostPickupEvent]
                if matched_pad.is_big or boost_increase <= (100.0 if matched_pad.is_big else 12.0) + 1.0:
                    event = BoostPickupEvent(
                        t=frame_time,
                        player_id=player_id,
                        pad_type="BIG" if matched_pad.is_big else "SMALL",
                        stolen=_is_stolen_pad(matched_pad, player.team, team_sides),
                        pad_id=matched_pad.pad_id,
                        location=matched_pad.position,
                        frame=frame_index,
                        boost_before=previous_boost,
                        boost_after=current_boost,
                        boost_gain=max(0.0, boost_increase),
                    )
                    pad_events = [event]
                    pad_state = pad_states.setdefault(matched_pad.pad_id, PadState())
                    respawn = BIG_PAD_RESPAWN_S if matched_pad.is_big else SMALL_PAD_RESPAWN_S
                    pad_state.available_at = frame_time + respawn
                    pad_state.last_pickup = frame_time
                else:
                    pad_events = _generate_small_pad_chain(
                        history,
                        matched_pad,
                        pad_states,
                        frame_time,
                        player_id,
                        player.team,
                        team_sides,
                        frame_index,
                        previous_boost,
                        current_boost,
                    )

                for idx, event in enumerate(pad_events):
                    key = (player_id, event.pad_id)
                    existing = recent_pickup_index.get(key)
                    if existing is not None and frame_time - existing[1] <= BOOST_PICKUP_MERGE_WINDOW:
                        event_idx, _ = existing
                        prev_event = pickups[event_idx]
                        updated_gain = prev_event.boost_gain + max(0.0, event.boost_gain)
                        pickups[event_idx] = replace(
                            prev_event,
                            boost_after=event.boost_after,
                            boost_gain=updated_gain,
                        )
                        recent_pickup_index[key] = (event_idx, frame_time)
                    else:
                        pickups.append(event)
                        recent_pickup_index[key] = (len(pickups) - 1, frame_time)

                    if debug_records is not None:
                        record = {
                            "frame": frame_index,
                            "timestamp": frame_time,
                            "player_id": player_id,
                            "pad_id": event.pad_id,
                            "pad_type": event.pad_type,
                            "boost_before": event.boost_before,
                            "boost_after": event.boost_after,
                            "boost_delta": event.boost_gain,
                            "stolen": bool(event.stolen),
                            "decision": decision_debug | ({"chain_index": idx} if idx else {}),
                        }
                        debug_records.append(record)

            state["boost"] = current_boost
            state["team"] = player.team

    if debug_records is not None and debug_sink:
        try:
            debug_path = Path(debug_sink)
            debug_path.parent.mkdir(parents=True, exist_ok=True)
            debug_path.write_text(json.dumps(debug_records, indent=2), encoding="utf-8")
        except OSError:
            # Silently ignore write failures to avoid impacting main flow.
            pass

    return pickups


def _select_boost_pad(
    history: deque[tuple[float, Vec3]],
    previous_boost: float,
    boost_increase: float,
    pad_states: dict[int, PadState],
    timestamp: float,
) -> tuple[BoostPad | None, dict[str, Any]]:
    """Select the boost pad that most likely produced the observed boost gain."""

    candidates: list[dict[str, Any]] = []
    best_pad: BoostPad | None = None
    best_score = float("inf")

    previous_boost = max(0.0, min(100.0, previous_boost))
    available_room = max(0.0, 100.0 - previous_boost)

    for pad in FIELD.BOOST_PADS:
        envelope = PAD_ENVELOPES[pad.pad_id]
        distance, closest_time, height_delta = _minimum_distance_to_pad(history, pad.position)
        time_in_envelope = max(0.0, timestamp - closest_time)
        inside_radius = distance <= envelope.radius

        if distance > envelope.max_distance:
            # Still consider as low-confidence candidate with penalty.
            distance_penalty = (distance - envelope.max_distance) / max(envelope.radius, 1.0)
        else:
            distance_penalty = 0.0
        if height_delta > envelope.height_tolerance:
            continue

        state = pad_states.setdefault(pad.pad_id, PadState())
        time_until_available = state.available_at - timestamp
        available = time_until_available <= PAD_RESPAWN_TOLERANCE
        if not available:
            continue

        pad_capacity = 100.0 if pad.is_big else 12.0
        expected_gain = min(pad_capacity, available_room)
        gain_error = abs(boost_increase - expected_gain)
        gain_denominator = max(1.0, expected_gain if expected_gain > 0 else 1.0)
        gain_score = gain_error / gain_denominator
        if not pad.is_big and boost_increase >= 40.0:
            gain_score += 2.0

        distance_score = distance / max(envelope.radius, 1.0)
        score = distance_score + 0.6 * gain_score + 0.1 * time_in_envelope + distance_penalty
        if not inside_radius:
            score += 0.8
        if not pad.is_big and boost_increase >= BIG_PAD_MIN_GAIN:
            score += 12.0

        candidate = {
            "pad_id": pad.pad_id,
            "distance": distance,
            "radius": envelope.radius,
            "height_delta": height_delta,
            "time_in_envelope": time_in_envelope,
            "expected_gain": expected_gain,
            "boost_delta": boost_increase,
            "score": score,
            "inside_radius": inside_radius,
            "available": available,
            "available_at": state.available_at,
            "pad_capacity": pad_capacity,
        }
        candidates.append(candidate)

        if score < best_score:
            best_score = score
            best_pad = pad

    return best_pad, {"candidates": candidates, "selected_pad": best_pad.pad_id if best_pad else None}


def _minimum_distance_to_pad(
    history: deque[tuple[float, Vec3]],
    pad_position: Vec3,
) -> tuple[float, float, float]:
    """Return the smallest distance, timestamp, and height delta to the pad."""
    if not history:
        return float("inf"), 0.0, float("inf")

    best_distance = float("inf")
    best_time = history[-1][0]
    best_height_delta = float("inf")
    for t, pos in history:
        distance = _distance_3d(pos, pad_position)
        if distance < best_distance:
            best_distance = distance
            best_time = t
            best_height_delta = abs(pos.z - pad_position.z)
    return best_distance, best_time, best_height_delta


def _fallback_nearest_pad(
    history: deque[tuple[float, Vec3]],
    pads_by_id: dict[int, BoostPad],
    pad_states: dict[int, PadState],
    timestamp: float,
    boost_increase: float,
) -> tuple[BoostPad, dict[str, Any]]:
    """Fallback pad selection when no candidate fits in-radius constraints."""
    if not history:
        pad = next(iter(pads_by_id.values()))
        return pad, {"reason": "no_history"}

    last_pos = history[-1][1]
    best_pad = None
    best_score = float("inf")
    debug_candidates: list[dict[str, Any]] = []
    for pad in pads_by_id.values():
        state = pad_states.setdefault(pad.pad_id, PadState())
        if state.available_at - timestamp > PAD_RESPAWN_TOLERANCE:
            continue
        distance = _distance_3d(last_pos, pad.position)
        envelope = PAD_ENVELOPES[pad.pad_id]
        distance_score = distance / envelope.radius if envelope.radius > 0 else distance
        if not pad.is_big:
            distance_score += 0.8
        pad_capacity = 100.0 if pad.is_big else 12.0
        capacity_error = abs(boost_increase - pad_capacity) / max(pad_capacity, 1.0)
        score = distance_score + 2.5 * capacity_error
        if not pad.is_big and boost_increase >= 36.0:
            score += 12.0
        debug_candidates.append(
            {
                "pad_id": pad.pad_id,
                "distance": distance,
                "distance_score": distance_score,
                "capacity_error": capacity_error,
                "score": score,
                "pad_capacity": pad_capacity,
            }
        )
        if score < best_score:
            best_score = score
            best_pad = pad
    if best_pad is None:
        best_pad = next(iter(pads_by_id.values()))
    return best_pad, {"reason": "capacity_adjusted_nearest", "score": best_score, "candidates": debug_candidates}


def _nearest_pad_distance(history: deque[tuple[float, Vec3]]) -> float:
    """Approximate nearest boost pad distance using latest position."""
    if not history:
        return float("inf")
    last_pos = history[-1][1]
    best = float("inf")
    for pad in FIELD.BOOST_PADS:
        dist = _distance_3d(last_pos, pad.position)
        if dist < best:
            best = dist
    return best


def _merge_pickup_events(pickups: list[BoostPickupEvent]) -> list[BoostPickupEvent]:
    """Merge pickups for the same player/pad occurring within a short window."""
    if not pickups:
        return pickups

    merged: list[BoostPickupEvent] = []
    for event in sorted(pickups, key=lambda p: p.t):
        if not merged:
            merged.append(event)
            continue

        last = merged[-1]
        same_player = last.player_id == event.player_id
        near_time = abs(event.t - last.t) <= BOOST_PICKUP_MERGE_WINDOW
        near_space = (
            last.location and event.location and _distance_3d(last.location, event.location) <= 320.0
        )
        same_pad = last.pad_id >= 0 and event.pad_id >= 0 and last.pad_id == event.pad_id
        no_location = last.location is None and event.location is None
        if same_player and near_time and (same_pad or near_space or no_location):
            merged_gain = max(0.0, last.boost_gain + max(0.0, event.boost_gain))
            merged_after = event.boost_after if event.boost_after is not None else last.boost_after
            merged_before = last.boost_before if last.boost_before is not None else event.boost_before
            merged[-1] = replace(
                last,
                t=min(last.t, event.t),
                boost_gain=merged_gain,
                boost_after=merged_after,
                boost_before=merged_before,
            )
            continue

        merged.append(event)

    return merged


def _order_small_pad_candidates(
    history: deque[tuple[float, Vec3]],
    pad_states: dict[int, PadState],
    timestamp: float,
    primary_pad: BoostPad,
) -> list[BoostPad]:
    """Order nearby small pads by approach time for chain attribution."""
    candidates: list[tuple[float, float, BoostPad]] = []
    seen: set[int] = set()

    for pad in FIELD.BOOST_PADS:
        if pad.is_big:
            continue
        distance, closest_time, height_delta = _minimum_distance_to_pad(history, pad.position)
        if distance > CHAIN_PAD_RADIUS or height_delta > 260.0:
            continue
        if timestamp < pad_states[pad.pad_id].available_at - PAD_RESPAWN_TOLERANCE:
            continue
        candidates.append((closest_time, distance, pad))
        seen.add(pad.pad_id)

    if primary_pad.pad_id not in seen:
        distance = _distance_3d(history[-1][1], primary_pad.position)
        candidates.append((history[-1][0], distance, primary_pad))

    candidates.sort(key=lambda item: (item[0], item[1]))
    ordered: list[BoostPad] = []
    for _, _, pad in candidates:
        if pad.pad_id not in {p.pad_id for p in ordered}:
            ordered.append(pad)
    return ordered


def _generate_small_pad_chain(
    history: deque[tuple[float, Vec3]],
    matched_pad: BoostPad,
    pad_states: dict[int, PadState],
    timestamp: float,
    player_id: str,
    player_team: int | None,
    team_sides: dict[int, int],
    frame_index: int,
    previous_boost: float,
    current_boost: float,
) -> list[BoostPickupEvent]:
    """Split large small-pad gains across a chain of nearby pads."""

    remaining_gain = max(0.0, current_boost - previous_boost)
    current_level = previous_boost
    ordered_pads = _order_small_pad_candidates(history, pad_states, timestamp, matched_pad)
    events: list[BoostPickupEvent] = []

    for pad in ordered_pads:
        if remaining_gain <= 1.0:
            break
        pad_capacity = 12.0
        available_room = max(0.0, 100.0 - current_level)
        if available_room <= 0.0:
            break
        gain = min(pad_capacity, remaining_gain, available_room)
        if gain < 1.0:
            continue
        event = BoostPickupEvent(
            t=timestamp,
            player_id=player_id,
            pad_type="SMALL",
            stolen=_is_stolen_pad(pad, player_team, team_sides),
            pad_id=pad.pad_id,
            location=pad.position,
            frame=frame_index,
            boost_before=current_level,
            boost_after=min(100.0, current_level + gain),
            boost_gain=gain,
        )
        events.append(event)
        state = pad_states.setdefault(pad.pad_id, PadState())
        state.available_at = timestamp + SMALL_PAD_RESPAWN_S
        state.last_pickup = timestamp
        current_level = min(100.0, current_level + gain)
        remaining_gain = max(0.0, remaining_gain - gain)

    if remaining_gain > 1.0 and events:
        # Attribute any residual gain to the last pad to preserve totals.
        last_event = events[-1]
        updated_gain = min(100.0, last_event.boost_gain + remaining_gain)
        events[-1] = replace(
            last_event,
            boost_after=min(100.0, last_event.boost_before + updated_gain),
            boost_gain=updated_gain,
        )

    if not events:
        # Fallback: single event using matched pad.
        events.append(
            BoostPickupEvent(
                t=timestamp,
                player_id=player_id,
                pad_type="SMALL",
                stolen=_is_stolen_pad(matched_pad, player_team, team_sides),
                pad_id=matched_pad.pad_id,
                location=matched_pad.position,
                frame=frame_index,
                boost_before=previous_boost,
                boost_after=current_boost,
                boost_gain=remaining_gain or (current_boost - previous_boost),
            )
        )
        state = pad_states.setdefault(matched_pad.pad_id, PadState())
        state.available_at = timestamp + SMALL_PAD_RESPAWN_S
        state.last_pickup = timestamp

    return events


def determine_team_sides(frames: list[Frame]) -> dict[int, int]:
    """Infer which half each team defends (+1 for positive Y, -1 for negative)."""
    sides: dict[int, int] = {}
    samples: dict[int, list[float]] = {0: [], 1: []}

    for frame in frames[:120]:
        for player in frame.players:
            if player.team not in samples:
                continue
            samples[player.team].append(player.position.y)
        if all(len(vals) >= 2 for vals in samples.values()):
            break

    for team, ys in samples.items():
        if len(ys) < MIN_ORIENTATION_SAMPLES:
            sides[team] = -1 if team == 0 else 1
            continue
        avg_y = sum(ys) / len(ys)
        sides[team] = 1 if avg_y >= 0 else -1
    return sides


def _is_stolen_pad(pad: BoostPad, team: int | None, team_sides: dict[int, int]) -> bool:
    """Determine whether collecting the pad counts as stolen boost."""
    if team not in (0, 1):
        return False
    if abs(pad.position.y) <= PAD_NEUTRAL_TOLERANCE:
        return False
    defending_sign = team_sides.get(team, -1 if team == 0 else 1)
    if defending_sign > 0:
        # Team defends positive Y; opponent half is negative.
        return pad.position.y < -PAD_NEUTRAL_TOLERANCE
    return pad.position.y > PAD_NEUTRAL_TOLERANCE


def _start_kickoff(frame: Frame) -> dict[str, Any]:
    """Initialize kickoff tracking state from the kickoff start frame."""

    player_states: dict[str, dict[str, Any]] = {}
    players_order: list[str] = []

    for player in frame.players:
        players_order.append(player.player_id)
        player_states[player.player_id] = {
            "team": player.team,
            "start_pos": player.position,
            "last_pos": player.position,
            "start_boost": float(player.boost_amount),
            "min_boost": float(player.boost_amount),
            "movement_start_time": None,
            "max_distance": 0.0,
            "first_touch_time": None,
            "role": "BACK",  # Placeholder until assigned from spawn ordering
        }

    _assign_kickoff_roles(player_states)

    return {
        "t_start": frame.timestamp,
        "players": player_states,
        "player_order": players_order,
        "first_touch": None,
    }


def _assign_kickoff_roles(player_states: dict[str, dict[str, Any]]) -> None:
    """Assign kickoff roles per team using spawn proximity."""

    by_team: dict[int, list[tuple[str, dict[str, Any]]]] = {0: [], 1: []}
    for pid, state in player_states.items():
        by_team.setdefault(state["team"], []).append((pid, state))

    for team, entries in by_team.items():
        if not entries:
            continue
        # Sort by distance to centre spot (closer players are the goers)
        entries.sort(key=lambda item: _distance_3d(item[1]["start_pos"], Vec3(0.0, 0.0, item[1]["start_pos"].z)))

        for index, (pid, state) in enumerate(entries):
            role = _classify_kickoff_role(state["start_pos"], team, index)
            state["role"] = role


def _update_kickoff_state(state: dict[str, Any], frame: Frame) -> None:
    """Update kickoff tracking state with the latest frame data."""

    ball = frame.ball
    t = frame.timestamp

    for player in frame.players:
        pid = player.player_id
        if pid not in state["players"]:
            # Ignore substitute players appearing mid-kickoff; rare but safe.
            continue

        pdata = state["players"][pid]
        pdata["last_pos"] = player.position
        pdata["min_boost"] = min(pdata["min_boost"], float(player.boost_amount))
        distance_from_start = _distance_3d(player.position, pdata["start_pos"])
        pdata["max_distance"] = max(pdata["max_distance"], distance_from_start)

        if pdata["movement_start_time"] is None and distance_from_start > 150.0:
            pdata["movement_start_time"] = t

        # Detect per-player first touch during kickoff window
        separation = _distance_3d(player.position, ball.position)
        if separation < TOUCH_PROXIMITY_THRESHOLD * 0.9:
            rel_time = t - state["t_start"]
            if pdata["first_touch_time"] is None:
                pdata["first_touch_time"] = rel_time

            first_touch = state.get("first_touch")
            if first_touch is None or rel_time < first_touch["time"]:
                state["first_touch"] = {
                    "player_id": pid,
                    "team": pdata["team"],
                    "time": rel_time,
                }


def _finalize_kickoff(state: dict[str, Any], frame: Frame, header: Header | None) -> KickoffEvent | None:
    """Produce the KickoffEvent dataclass from tracked state."""

    t_start = state["t_start"]
    elapsed = frame.timestamp - t_start
    if elapsed < 0.05:  # Ignore degenerate kickoffs
        return None

    first_touch = state.get("first_touch")
    first_touch_player = first_touch.get("player_id") if first_touch else None
    time_to_first_touch = first_touch.get("time") if first_touch else None

    players_payload = []
    for pid in state["player_order"]:
        pdata = state["players"].get(pid)
        if pdata is None:
            continue

        boost_used = max(0.0, pdata["start_boost"] - pdata["min_boost"])
        time_to_contact = pdata["first_touch_time"]
        approach_type = _classify_approach_type(pdata, state["t_start"])

        players_payload.append(
            {
                "player_id": pid,
                "role": pdata["role"],
                "boost_used": round(boost_used, 2),
                "approach_type": approach_type,
                "time_to_first_touch": None if time_to_contact is None else round(time_to_contact, 3),
            }
        )

    phase = _determine_kickoff_phase(t_start, header)
    outcome = _classify_kickoff_outcome(first_touch)

    return KickoffEvent(
        phase=phase,
        t_start=t_start,
        players=players_payload,
        outcome=outcome,
        first_touch_player=first_touch_player,
        time_to_first_touch=None if time_to_first_touch is None else round(time_to_first_touch, 3),
    )


def _classify_kickoff_role(position: Vec3, team: int, ordinal: int) -> str:
    """Classify kickoff role (GO/CHEAT/WING/BACK) using spawn layout heuristics."""

    x_abs = abs(position.x)
    y_abs = abs(position.y)

    # Primary goer: closest to centre regardless of ordinal
    if ordinal == 0:
        return "GO"

    if x_abs >= 1700.0 and y_abs <= 3600.0:
        return "WING"

    if y_abs <= 3200.0:
        return "CHEAT"

    return "BACK"


def _classify_approach_type(pdata: dict[str, Any], kickoff_start_time: float) -> str:
    """Infer kickoff approach type from movement timing and boost usage."""

    boost_used = max(0.0, pdata["start_boost"] - pdata["min_boost"])
    movement_start = pdata.get("movement_start_time")
    first_touch_time = pdata.get("first_touch_time")
    max_distance = pdata.get("max_distance", 0.0)

    if first_touch_time is not None and first_touch_time <= 0.45 and boost_used >= 25.0:
        return "SPEEDFLIP"

    if movement_start is not None:
        delay = movement_start - kickoff_start_time
        if delay >= 0.8:
            return "DELAY"

    if max_distance < 250.0 and boost_used < 5.0:
        return "FAKE"

    return "STANDARD" if boost_used > 0.0 or max_distance > 150.0 else "UNKNOWN"


def _determine_kickoff_phase(kickoff_start: float, header: Header | None) -> str:
    """Determine kickoff phase (INITIAL vs OT)."""

    if header:
        match_length = float(getattr(header, "match_length", 0.0) or 0.0)
        if getattr(header, "overtime", False) and kickoff_start >= max(300.0, match_length):
            return "OT"
    if kickoff_start >= 300.0:
        return "OT"
    return "INITIAL"


def _classify_kickoff_outcome(first_touch: dict[str, Any] | None) -> str:
    """Map first touch info to schema outcome classification."""

    if not first_touch:
        return "NEUTRAL"

    team = first_touch.get("team")
    if team == 0:
        return "FIRST_POSSESSION_BLUE"
    if team == 1:
        return "FIRST_POSSESSION_ORANGE"
    return "NEUTRAL"


def _classify_touch_context(player: PlayerFrame, ball_position: Vec3) -> TouchContext:
    """Classify touch context based on player and ball positions.

    Args:
        player: Player frame data at touch time
        ball_position: Ball position at touch time

    Returns:
        TouchContext classification
    """
    car_height = player.position.z
    car_x = abs(player.position.x)
    car_y = abs(player.position.y)
    ball_height = ball_position.z

    # Ceiling touch: car is very high
    if car_height >= CEILING_HEIGHT_THRESHOLD:
        return TouchContext.CEILING

    # Wall touch: car is near side wall or back wall
    near_side_wall = car_x >= (FIELD.SIDE_WALL_X - WALL_PROXIMITY_THRESHOLD)
    near_back_wall = car_y >= (FIELD.BACK_WALL_Y - WALL_PROXIMITY_THRESHOLD)

    if near_side_wall or near_back_wall:
        # Additional check: car should be elevated if on wall
        if car_height > 100.0:
            return TouchContext.WALL

    # Aerial touch: both car and ball elevated significantly
    if car_height >= AERIAL_HEIGHT_THRESHOLD and ball_height >= AERIAL_HEIGHT_THRESHOLD:
        return TouchContext.AERIAL

    # Half volley: car slightly off ground (just jumped)
    if car_height > 17.0 and car_height < HALF_VOLLEY_HEIGHT and not player.is_on_ground:
        return TouchContext.HALF_VOLLEY

    # Ground touch: car is on or near ground
    if car_height < 30.0 or player.is_on_ground:
        return TouchContext.GROUND

    # If car is elevated but not clearly aerial/wall, default to aerial for higher touches
    if car_height >= 100.0:
        return TouchContext.AERIAL

    return TouchContext.GROUND


def detect_touches(frames: list[Frame]) -> list[TouchEvent]:
    """Detect player-ball contact events with richer classification."""

    if not frames:
        return []

    touches: list[TouchEvent] = []
    last_touch_event: dict[str, TouchEvent] = {}
    prev_ball_velocity: Vec3 | None = None
    prev_ball_position: Vec3 | None = None
    first_touch_recorded = False

    for frame_index, frame in enumerate(frames):
        ball_velocity = frame.ball.velocity
        ball_speed = _vector_magnitude(ball_velocity)

        for player in frame.players:
            distance = _distance_3d(player.position, frame.ball.position)
            if distance >= TOUCH_PROXIMITY_THRESHOLD:
                continue

            prev_event = last_touch_event.get(player.player_id)
            if prev_event is not None:
                delta_t = frame.timestamp - prev_event.t
                if delta_t < 0.05:
                    continue
                same_area = _distance_3d(player.position, prev_event.location) <= TOUCH_LOCATION_EPS
                if same_area and delta_t < TOUCH_DEBOUNCE_TIME:
                    relative_speed = _relative_speed(player.velocity, frame.ball.velocity)
                    if ball_speed < MIN_BALL_SPEED_FOR_TOUCH and relative_speed < MIN_RELATIVE_SPEED_FOR_TOUCH:
                        continue

            outcome, is_save = _classify_touch_outcome(
                player,
                frame,
                prev_ball_velocity,
                prev_ball_position,
            )

            touch_context = _classify_touch_context(player, frame.ball.position)
            is_first = not first_touch_recorded
            first_touch_recorded = True

            touch = TouchEvent(
                t=frame.timestamp,
                frame=frame_index,
                player_id=player.player_id,
                location=player.position,
                ball_speed_kph=round(ball_speed * UU_S_TO_KPH, 2),
                outcome=outcome,
                is_save=is_save,
                touch_context=touch_context,
                car_height=round(player.position.z, 2),
                is_first_touch=is_first,
            )
            touches.append(touch)
            last_touch_event[player.player_id] = touch

        prev_ball_velocity = ball_velocity
        prev_ball_position = frame.ball.position

    return touches


def detect_challenge_events(frames: list[Frame], touches: list[TouchEvent] | None = None) -> list[ChallengeEvent]:
    """Detect 50/50 challenge events derived from successive opposing touches."""

    if touches is None:
        touches = detect_touches(frames)
    if not touches:
        return []

    touches_sorted = sorted(touches, key=lambda t: (t.t, t.player_id))

    player_team_idx: dict[str, int] = {}
    for frame in frames:
        for player in frame.players:
            if player.player_id in player_team_idx:
                continue
            if player.team is None:
                continue
            player_team_idx[player.player_id] = 0 if player.team == 0 else 1

    challenge_events: list[ChallengeEvent] = []
    i = 0
    while i < len(touches_sorted) - 1:
        first = touches_sorted[i]
        second = touches_sorted[i + 1]

        if first.player_id == second.player_id:
            i += 1
            continue

        team_first = player_team_idx.get(first.player_id)
        team_second = player_team_idx.get(second.player_id)
        if team_first is None or team_second is None or team_first == team_second:
            i += 1
            continue

        dt = second.t - first.t
        if dt < 0 or dt > CHALLENGE_WINDOW_S:
            i += 1
            continue

        separation = _distance_3d(first.location, second.location)
        if separation > CHALLENGE_RADIUS_UU or separation < CHALLENGE_MIN_DISTANCE_UU:
            i += 1
            continue

        if (
            first.ball_speed_kph < CHALLENGE_MIN_BALL_SPEED_KPH
            and second.ball_speed_kph < CHALLENGE_MIN_BALL_SPEED_KPH
        ):
            i += 1
            continue

        outcome = "LOSS"
        winner_team: str | None = _team_name(team_second)

        used_third = False
        if i + 2 < len(touches_sorted):
            third = touches_sorted[i + 2]
            team_third = player_team_idx.get(third.player_id)
            if (
                team_third is not None
                and (third.t - second.t) <= NEUTRAL_RETOUCH_WINDOW_S
                and _distance_3d(second.location, third.location) <= CHALLENGE_RADIUS_UU
            ):
                outcome = "NEUTRAL"
                winner_team = None
                used_third = True

        if outcome != "NEUTRAL" and winner_team == _team_name(team_first):
            outcome = "WIN"
        elif outcome != "NEUTRAL" and winner_team == _team_name(team_second):
            outcome = "LOSS"

        if outcome == "NEUTRAL":
            winner_team = None

        depth_y = (first.location.y + second.location.y) / 2.0
        depth_m = abs(depth_y) * 0.019

        midpoint = Vec3(
            (first.location.x + second.location.x) / 2.0,
            (first.location.y + second.location.y) / 2.0,
            (first.location.z + second.location.z) / 2.0,
        )

        pf_first, ball_first = _nearest_player_ball_frame(frames, first.player_id, first.t)
        pf_second, ball_second = _nearest_player_ball_frame(frames, second.player_id, second.t)
        risk_first = _compute_challenge_risk(pf_first, ball_first, team_first)
        risk_second = _compute_challenge_risk(pf_second, ball_second, team_second)

        challenge_events.append(
            ChallengeEvent(
                t=(first.t + second.t) / 2.0,
                first_player=first.player_id,
                second_player=second.player_id,
                first_team=_team_name(team_first),
                second_team=_team_name(team_second),
                outcome=outcome,
                winner_team=winner_team,
                location=midpoint,
                depth_m=round(depth_m, 3),
                duration=round(dt, 3),
                risk_first=round(risk_first, 3),
                risk_second=round(risk_second, 3),
            )
        )

        i += 3 if used_third else 2

    return challenge_events


def build_timeline(events_dict: dict[str, list[Any]]) -> list[TimelineEvent]:
    """Build chronological timeline from all detected events.
    
    Args:
        events_dict: Dictionary of event type -> event list
        
    Returns:
        Sorted list of timeline events
    """
    timeline = []
    
    # Convert each event type to timeline entries
    for goals in events_dict.get('goals', []):
        timeline.append(TimelineEvent(
            t=goals.t,
            frame=goals.frame,
            type="GOAL",
            player_id=goals.scorer,
            team=goals.team,
            data={
                "shot_speed_kph": goals.shot_speed_kph,
                "distance_m": goals.distance_m,
                "assist": goals.assist
            }
        ))
        if goals.assist:
            timeline.append(TimelineEvent(
                t=goals.t,
                frame=goals.frame,
                type="ASSIST",
                player_id=goals.assist,
                team=goals.team,
                data={"scorer": goals.scorer}
            ))
    
    for demo in events_dict.get('demos', []):
        timeline.append(TimelineEvent(
            t=demo.t,
            type="DEMO",
            player_id=demo.victim,
            team=demo.team_victim,
            data={
                "attacker": demo.attacker,
                "location": demo.location
            }
        ))
    
    for kickoff in events_dict.get('kickoffs', []):
        timeline.append(TimelineEvent(
            t=kickoff.t_start,
            type="KICKOFF",
            data={
                "phase": kickoff.phase,
                "players": kickoff.players,
                "outcome": kickoff.outcome
            }
        ))
    
    for pickup in events_dict.get('boost_pickups', []):
        timeline.append(TimelineEvent(
            t=pickup.t,
            type="BOOST_PICKUP",
            player_id=pickup.player_id,
            data={
                "pad_type": pickup.pad_type,
                "stolen": pickup.stolen,
                "location": pickup.location
            }
        ))
    
    for touch in events_dict.get('touches', []):
        timeline.append(TimelineEvent(
            t=touch.t,
            frame=touch.frame,
            type="TOUCH",
            player_id=touch.player_id,
            data={
                "location": touch.location,
                "ball_speed_kph": touch.ball_speed_kph,
                "outcome": touch.outcome
            }
        ))

        if touch.outcome == "SHOT":
            timeline.append(TimelineEvent(
                t=touch.t,
                frame=touch.frame,
                type="SHOT",
                player_id=touch.player_id,
                data={"ball_speed_kph": touch.ball_speed_kph}
            ))

        if touch.is_save:
            timeline.append(TimelineEvent(
                t=touch.t,
                frame=touch.frame,
                type="SAVE",
                player_id=touch.player_id,
                data={"ball_speed_kph": touch.ball_speed_kph}
            ))

    for challenge in events_dict.get('challenges', []):
        timeline.append(TimelineEvent(
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
            }
        ))

    # Sort chronologically, then by type for stable ordering
    timeline.sort(key=lambda e: (e.t, e.type))

    return timeline


def _classify_touch_outcome(
    player: PlayerFrame,
    frame: Frame,
    prev_ball_velocity: Vec3 | None,
    prev_ball_position: Vec3 | None,
) -> tuple[str, bool]:
    """Return (outcome, is_save) for a detected touch."""

    ball_velocity = frame.ball.velocity
    ball_speed = _vector_magnitude(ball_velocity)
    team_idx = 0 if player.team == 0 else 1

    if ball_speed > 1500.0:
        return "SHOT", False

    shot_on_target = _is_shot_on_target(team_idx, frame.ball.position, ball_velocity)

    if shot_on_target and ball_speed >= 650.0:
        return "SHOT", False

    is_save = False
    if prev_ball_velocity is not None and prev_ball_position is not None:
        if _is_toward_own_goal(team_idx, prev_ball_velocity) and not _is_toward_own_goal(team_idx, ball_velocity):
            if _is_in_defensive_third(team_idx, prev_ball_position):
                is_save = True

    if is_save:
        return "CLEAR", True

    if ball_speed > 900.0 and _is_toward_opponent_goal(team_idx, ball_velocity):
        return "PASS", False

    if ball_speed < 250.0:
        return "DRIBBLE", False

    if ball_speed > 600.0 and _is_toward_opponent_goal(team_idx, ball_velocity):
        return "PASS", False

    return "NEUTRAL", False


def _team_name(idx: int | None) -> str:
    if idx == 0:
        return "BLUE"
    if idx == 1:
        return "ORANGE"
    return "UNKNOWN"


def _is_toward_opponent_goal(team_idx: int, velocity: Vec3) -> bool:
    return velocity.y > 250.0 if team_idx == 0 else velocity.y < -250.0


def _is_toward_own_goal(team_idx: int, velocity: Vec3) -> bool:
    return velocity.y < -400.0 if team_idx == 0 else velocity.y > 400.0


def _is_shot_on_target(team_idx: int, position: Vec3, velocity: Vec3) -> bool:
    if not _is_toward_opponent_goal(team_idx, velocity):
        return False

    dy = velocity.y
    if abs(dy) < 1e-6:
        return False

    goal_y = FIELD.BACK_WALL_Y if team_idx == 0 else -FIELD.BACK_WALL_Y
    time_to_goal = (goal_y - position.y) / dy
    if time_to_goal <= 0 or time_to_goal > 3.5:
        return False

    est_x = position.x + velocity.x * time_to_goal
    est_z = position.z + velocity.z * time_to_goal
    if abs(est_x) > FIELD.GOAL_WIDTH or est_z > FIELD.GOAL_HEIGHT:
        return False

    return True


def _is_in_defensive_third(team_idx: int, position: Vec3) -> bool:
    if team_idx == 0:
        return position.y <= -FIELD.BACK_WALL_Y * 0.33
    return position.y >= FIELD.BACK_WALL_Y * 0.33


def _nearest_player_ball_frame(
    frames: list[Frame], player_id: str, timestamp: float
) -> tuple[PlayerFrame | None, tuple[Vec3, Vec3] | None]:
    if not frames:
        return None, None
    closest: Frame | None = None
    best_delta = float("inf")
    for fr in frames:
        delta = abs(fr.timestamp - timestamp)
        if delta < best_delta:
            best_delta = delta
            closest = fr
    if closest is None:
        return None, None
    return closest.get_player_by_id(player_id), (closest.ball.position, closest.ball.velocity)


def _compute_challenge_risk(
    player_frame: PlayerFrame | None,
    ball_state: tuple[Vec3, Vec3] | None,
    team_idx: int | None,
) -> float:
    if player_frame is None or ball_state is None or team_idx is None:
        return 0.0

    ball_pos, _ball_vel = ball_state

    if team_idx == 0:
        ahead = player_frame.position.y > ball_pos.y
        last_man = player_frame.position.y <= ball_pos.y
    else:
        ahead = player_frame.position.y < ball_pos.y
        last_man = player_frame.position.y >= ball_pos.y

    ahead_score = 1.0 if ahead else 0.0
    low_boost_score = 1.0 if player_frame.boost_amount <= RISK_LOW_BOOST_THRESHOLD else 0.0
    last_man_score = 1.0 if last_man else 0.0

    risk = (
        RISK_AHEAD_OF_BALL_WEIGHT * ahead_score
        + RISK_LOW_BOOST_WEIGHT * low_boost_score
        + RISK_LAST_MAN_WEIGHT * last_man_score
    )
    return max(0.0, min(1.0, risk))


def _distance_3d(pos1: Vec3, pos2: Vec3) -> float:
    """Calculate 3D Euclidean distance between two positions."""
    dx = pos1.x - pos2.x
    dy = pos1.y - pos2.y
    dz = pos1.z - pos2.z
    return math.sqrt(dx*dx + dy*dy + dz*dz)


def _vector_magnitude(vec: Vec3) -> float:
    """Calculate magnitude of a 3D vector."""
    return math.sqrt(vec.x*vec.x + vec.y*vec.y + vec.z*vec.z)


def _relative_speed(player_velocity: Vec3, ball_velocity: Vec3) -> float:
    """Calculate magnitude of the relative velocity between player and ball."""
    dvx = player_velocity.x - ball_velocity.x
    dvy = player_velocity.y - ball_velocity.y
    dvz = player_velocity.z - ball_velocity.z
    return math.sqrt(dvx * dvx + dvy * dvy + dvz * dvz)
TOUCH_DEBOUNCE_TIME = 0.2  # seconds
TOUCH_LOCATION_EPS = 120.0  # uu
MIN_BALL_SPEED_FOR_TOUCH = 120.0  # uu/s
MIN_RELATIVE_SPEED_FOR_TOUCH = 180.0  # uu/s
MIN_ORIENTATION_SAMPLES = 5
