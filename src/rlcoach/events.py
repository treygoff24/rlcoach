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

import math
from dataclasses import dataclass, replace
from typing import Any

from .field_constants import FIELD, Vec3, BoostPad
from .normalize import measure_frame_rate
from .parser.types import Header, Frame, PlayerFrame, BallFrame


# Detection thresholds - explicitly documented
GOAL_LINE_THRESHOLD = FIELD.BACK_WALL_Y - FIELD.GOAL_DEPTH  # Front plane of goal
GOAL_EXIT_THRESHOLD = GOAL_LINE_THRESHOLD - 200.0
BALL_STATIONARY_THRESHOLD = 50.0  # Ball speed for kickoff detection (units/s)
TOUCH_PROXIMITY_THRESHOLD = 200.0  # Distance for player-ball contact (units)
DEMO_POSITION_TOLERANCE = 500.0  # Max distance for demo attacker detection (units)
BOOST_PICKUP_MIN_GAIN = 1.0  # Minimum net gain to record a pickup event
CENTERLINE_TOLERANCE = 100.0  # Within this Y range is considered neutral half

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


def detect_goals(frames: list[Frame], header: Header | None = None) -> list[GoalEvent]:
    """Detect goal events from ball position crossing goal lines.
    
    Args:
        frames: Normalized frame data
        header: Optional header for team score validation
        
    Returns:
        List of detected goal events
    """
    if not frames:
        return []
    
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


def detect_boost_pickups(frames: list[Frame]) -> list[BoostPickupEvent]:
    """Detect boost pickup events from player boost amount increases.
    
    Args:
        frames: Normalized frame data
        
    Returns:
        List of detected boost pickup events
    """
    if not frames:
        return []
    
    pickups: list[BoostPickupEvent] = []
    previous_boost_amounts: dict[str, float] = {}
    recent_positions: dict[str, list[tuple[float, Vec3]]] = {}
    recent_pickup_index: dict[tuple[str, int], tuple[int, float]] = {}

    pad_radius_padding = {True: 150.0, False: 110.0}
    big_pads = [pad for pad in FIELD.BOOST_PADS if pad.is_big]
    small_pads = [pad for pad in FIELD.BOOST_PADS if not pad.is_big]

    for i, frame in enumerate(frames):
        for player in frame.players:
            player_id = player.player_id
            current_boost = float(player.boost_amount)
            previous_boost = previous_boost_amounts.get(player_id)

            history = recent_positions.setdefault(player_id, [])
            history.append((frame.timestamp, player.position))
            cutoff = frame.timestamp - 0.4
            recent_positions[player_id] = [entry for entry in history if entry[0] >= cutoff]

            if previous_boost is None:
                previous_boost_amounts[player_id] = current_boost
                continue

            boost_increase = current_boost - previous_boost
            if boost_increase >= BOOST_PICKUP_MIN_GAIN:
                within_big: tuple[BoostPad, float, Vec3] | None = None
                nearest_big: tuple[BoostPad, float, Vec3] | None = None
                within_small: tuple[BoostPad, float, Vec3] | None = None
                nearest_small: tuple[BoostPad, float, Vec3] | None = None

                for pad in big_pads:
                    pad_padding = pad_radius_padding[True]
                    for _, position in recent_positions[player_id]:
                        distance = _distance_3d(position, pad.position)
                        if nearest_big is None or distance < nearest_big[1]:
                            nearest_big = (pad, distance, position)
                        if distance <= pad.radius + pad_padding:
                            if within_big is None or distance < within_big[1]:
                                within_big = (pad, distance, position)

                for pad in small_pads:
                    pad_padding = pad_radius_padding[False]
                    for _, position in recent_positions[player_id]:
                        distance = _distance_3d(position, pad.position)
                        if nearest_small is None or distance < nearest_small[1]:
                            nearest_small = (pad, distance, position)
                        if distance <= pad.radius + pad_padding:
                            if within_small is None or distance < within_small[1]:
                                within_small = (pad, distance, position)

                matched_pad: BoostPad | None = None
                pickup_position: Vec3 | None = None
                cand_big = within_big or nearest_big
                cand_small = within_small or nearest_small

                if cand_big and cand_small:
                    pad_big, dist_big, pos_big = cand_big
                    pad_small, dist_small, pos_small = cand_small
                    expected_big = min(100.0, max(0.0, 100.0 - previous_boost))
                    expected_small = min(12.0, max(0.0, 100.0 - previous_boost))
                    diff_big = abs(boost_increase - expected_big)
                    diff_small = abs(boost_increase - expected_small)
                    tolerance = 4.0
                    if diff_big + tolerance < diff_small:
                        matched_pad = pad_big
                        pickup_position = pos_big
                    elif diff_small + tolerance < diff_big:
                        matched_pad = pad_small
                        pickup_position = pos_small
                    else:
                        if dist_big <= dist_small:
                            matched_pad = pad_big
                            pickup_position = pos_big
                        else:
                            matched_pad = pad_small
                            pickup_position = pos_small
                elif cand_big:
                    matched_pad, _, pickup_position = cand_big
                elif cand_small:
                    matched_pad, _, pickup_position = cand_small

                if matched_pad is None:
                    previous_boost_amounts[player_id] = current_boost
                    continue

                key = (player_id, matched_pad.pad_id)
                existing = recent_pickup_index.get(key)
                if existing is not None and frame.timestamp - existing[1] < 0.2:
                    event_idx, _ = existing
                    prev_event = pickups[event_idx]
                    updated_gain = prev_event.boost_gain + max(0.0, boost_increase)
                    updated_event = replace(
                        prev_event,
                        boost_after=current_boost,
                        boost_gain=updated_gain,
                    )
                    pickups[event_idx] = updated_event
                    recent_pickup_index[key] = (event_idx, frame.timestamp)
                    previous_boost_amounts[player_id] = current_boost
                    continue

                is_stolen = False
                pickup_reference = pickup_position or matched_pad.position
                if abs(pickup_reference.y) <= CENTERLINE_TOLERANCE:
                    is_stolen = False
                elif player.team == 0:
                    is_stolen = pickup_reference.y > 0
                elif player.team == 1:
                    is_stolen = pickup_reference.y < 0

                pickup = BoostPickupEvent(
                    t=frame.timestamp,
                    player_id=player_id,
                    pad_type="BIG" if matched_pad.is_big else "SMALL",
                    stolen=is_stolen,
                    pad_id=matched_pad.pad_id,
                    location=matched_pad.position,
                    frame=i,
                    boost_before=previous_boost,
                    boost_after=current_boost,
                    boost_gain=max(0.0, boost_increase),
                )
                pickups.append(pickup)
                recent_pickup_index[key] = (len(pickups) - 1, frame.timestamp)

            previous_boost_amounts[player_id] = current_boost

    return pickups


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


def detect_touches(frames: list[Frame]) -> list[TouchEvent]:
    """Detect player-ball contact events with richer classification."""

    if not frames:
        return []

    touches: list[TouchEvent] = []
    last_touch_event: dict[str, TouchEvent] = {}
    prev_ball_velocity: Vec3 | None = None
    prev_ball_position: Vec3 | None = None

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

            touch = TouchEvent(
                t=frame.timestamp,
                frame=frame_index,
                player_id=player.player_id,
                location=player.position,
                ball_speed_kph=round(ball_speed * 3.6, 2),
                outcome=outcome,
                is_save=is_save,
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

    if ball_speed > 600.0:
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
