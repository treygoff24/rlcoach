"""Kickoff detection for Rocket League replays.

Detects kickoff events with enriched per-player metrics including
roles, approach types, and timing analysis.
"""

from __future__ import annotations

from typing import Any

from ..field_constants import Vec3
from ..parser.types import Frame, Header
from .constants import (
    BALL_STATIONARY_THRESHOLD,
    KICKOFF_CENTER_POSITION,
    KICKOFF_MAX_DURATION,
    KICKOFF_MIN_COOLDOWN,
    KICKOFF_POSITION_TOLERANCE,
    TOUCH_PROXIMITY_THRESHOLD,
)
from .types import KickoffEvent
from .utils import distance_3d, vector_magnitude


def detect_kickoffs(
    frames: list[Frame], header: Header | None = None
) -> list[KickoffEvent]:
    """Detect kickoff events with enriched per-player metrics.

    The detector tracks the full kickoff window (ball at center -> first
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
            abs(ball.position.x - KICKOFF_CENTER_POSITION.x)
            <= KICKOFF_POSITION_TOLERANCE
            and abs(ball.position.y - KICKOFF_CENTER_POSITION.y)
            <= KICKOFF_POSITION_TOLERANCE
            and abs(ball.position.z - KICKOFF_CENTER_POSITION.z) <= 60.0
        )
        ball_speed = vector_magnitude(ball.velocity)
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
            # New tracking fields for improved classification
            "velocities": [],  # List of (t, speed) tuples
            "max_speed": 0.0,
            "speed_at_contact": 0.0,
            "positions": [],  # List of (t, Vec3) for path analysis
            "distance_to_ball_min": float("inf"),
            "reached_ball": False,
            "moved_toward_ball": False,
            "moved_away_from_ball": False,
            "jumped": False,
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
        entries.sort(
            key=lambda item: distance_3d(
                item[1]["start_pos"], Vec3(0.0, 0.0, item[1]["start_pos"].z)
            )
        )

        for index, (_pid, state) in enumerate(entries):
            role = _classify_kickoff_role(state["start_pos"], team, index)
            state["role"] = role


def _update_kickoff_state(state: dict[str, Any], frame: Frame) -> None:
    """Update kickoff tracking state with the latest frame data."""
    ball = frame.ball
    t = frame.timestamp
    t_start = state["t_start"]
    rel_time = t - t_start

    for player in frame.players:
        pid = player.player_id
        if pid not in state["players"]:
            # Ignore substitute players appearing mid-kickoff; rare but safe.
            continue

        pdata = state["players"][pid]
        pdata["last_pos"] = player.position
        pdata["min_boost"] = min(pdata["min_boost"], float(player.boost_amount))
        distance_from_start = distance_3d(player.position, pdata["start_pos"])
        pdata["max_distance"] = max(pdata["max_distance"], distance_from_start)

        if pdata["movement_start_time"] is None and distance_from_start > 150.0:
            pdata["movement_start_time"] = t

        # Track velocity for delay/speedflip detection
        speed = vector_magnitude(player.velocity)
        pdata["velocities"].append((rel_time, speed))
        pdata["max_speed"] = max(pdata["max_speed"], speed)

        # Track position trajectory
        pdata["positions"].append((rel_time, player.position))

        # Track minimum distance to ball
        separation = distance_3d(player.position, ball.position)
        pdata["distance_to_ball_min"] = min(pdata["distance_to_ball_min"], separation)

        # Track if player reached ball proximity
        if separation < TOUCH_PROXIMITY_THRESHOLD * 1.2:
            pdata["reached_ball"] = True

        # Track directional movement relative to ball (at center)
        ball_center = KICKOFF_CENTER_POSITION
        start_dist_to_ball = distance_3d(pdata["start_pos"], ball_center)
        current_dist_to_ball = distance_3d(player.position, ball_center)
        if current_dist_to_ball < start_dist_to_ball - 100.0:
            pdata["moved_toward_ball"] = True
        if current_dist_to_ball > start_dist_to_ball + 100.0:
            pdata["moved_away_from_ball"] = True

        # Track if player has jumped (for aerial/flip detection)
        if not player.is_on_ground and player.position.z > 30.0:
            pdata["jumped"] = True

        # Detect per-player first touch during kickoff window
        if separation < TOUCH_PROXIMITY_THRESHOLD * 0.9:
            if pdata["first_touch_time"] is None:
                pdata["first_touch_time"] = rel_time
                pdata["speed_at_contact"] = speed

            first_touch = state.get("first_touch")
            if first_touch is None or rel_time < first_touch["time"]:
                state["first_touch"] = {
                    "player_id": pid,
                    "team": pdata["team"],
                    "time": rel_time,
                }


def _finalize_kickoff(
    state: dict[str, Any], frame: Frame, header: Header | None
) -> KickoffEvent | None:
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
                "time_to_first_touch": (
                    None if time_to_contact is None else round(time_to_contact, 3)
                ),
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
        time_to_first_touch=(
            None if time_to_first_touch is None else round(time_to_first_touch, 3)
        ),
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


def _is_speedflip_kickoff(pdata: dict[str, Any]) -> bool:
    """Detect speedflip from fast time to ball + high speed profile.

    Speedflip is characterized by:
    - Fast first touch time from diagonal spawn (~2.4-2.6s)
    - High boost usage during kickoff
    - High max speed achieved
    - Player jumped (flip required)

    Without mechanics data, we use timing and speed heuristics.
    """
    first_touch_time = pdata.get("first_touch_time")
    max_speed = pdata.get("max_speed", 0.0)
    boost_used = max(0.0, pdata["start_boost"] - pdata["min_boost"])
    jumped = pdata.get("jumped", False)

    # Speedflip requires a flip
    if not jumped:
        return False

    # Must have used significant boost
    if boost_used < 20.0:
        return False

    # High max speed is indicative (speedflip maintains supersonic)
    # Supersonic threshold is ~2200 uu/s
    if max_speed < 2000.0:
        return False

    # Fast time to first touch is the key indicator
    # Pro speedflips from diagonal: ~2.4-2.6s
    # Non-speedflip from diagonal: ~2.8-3.2s
    if first_touch_time is not None and first_touch_time <= 2.7:
        return True

    return False


def _is_delay_kickoff(pdata: dict[str, Any]) -> bool:
    """Detect delay kickoff from deceleration near contact.

    Delay kickoff = normal approach but brake right before 50/50.
    Key signature: high speed followed by sudden drop near contact.
    """
    velocities = pdata.get("velocities", [])
    contact_time = pdata.get("first_touch_time")
    max_speed = pdata.get("max_speed", 0.0)

    if not velocities or contact_time is None:
        return False

    # Must have approached at high speed (was going fast)
    if max_speed < 1800.0:
        return False

    # Find velocity profile near contact (last 0.5s before touch)
    pre_contact_velocities = [
        (t, v) for t, v in velocities if contact_time - 0.5 < t < contact_time
    ]

    if len(pre_contact_velocities) < 3:
        return False

    # Look for deceleration spike
    local_max_speed = max(v for _, v in pre_contact_velocities)
    final_speed = pre_contact_velocities[-1][1]

    # Significant deceleration (>30% speed drop) near contact
    if local_max_speed > 0:
        speed_drop = (local_max_speed - final_speed) / local_max_speed
        return speed_drop > 0.30 and local_max_speed > 1500.0

    return False


def _is_fake_kickoff(pdata: dict[str, Any]) -> tuple[bool, str]:
    """Detect fake kickoff and classify subtype.

    Fake types:
    1. FAKE_STATIONARY: Didn't move at all
    2. FAKE_HALFFLIP: Moved backward (half-flip to grab corner boost)
    3. FAKE_AGGRESSIVE: Moved but didn't contest ball

    Returns:
        Tuple of (is_fake, fake_type or "")
    """
    reached_ball = pdata.get("reached_ball", False)
    max_distance = pdata.get("max_distance", 0.0)
    moved_away = pdata.get("moved_away_from_ball", False)
    moved_toward = pdata.get("moved_toward_ball", False)
    boost_used = max(0.0, pdata["start_boost"] - pdata["min_boost"])
    first_touch_time = pdata.get("first_touch_time")

    # If player touched the ball, not a fake
    if first_touch_time is not None:
        return False, ""

    # Type 1: Stationary fake - barely moved
    if max_distance < 100.0 and boost_used < 5.0:
        return True, "FAKE_STATIONARY"

    # Type 2: Half-flip backward (common on diagonal)
    # Moved significant distance but AWAY from ball
    if moved_away and not moved_toward and max_distance > 300.0:
        return True, "FAKE_HALFFLIP"

    # Type 3: Aggressive fake - moved toward but didn't reach ball
    # This happens when they go to intercept where opponent hits ball
    if not reached_ball and moved_toward and max_distance > 500.0:
        return True, "FAKE_AGGRESSIVE"

    # Type 3b: Just didn't contest despite moving
    if not reached_ball and max_distance > 300.0:
        return True, "FAKE_AGGRESSIVE"

    return False, ""


def _classify_standard_kickoff(pdata: dict[str, Any]) -> str:
    """Classify standard kickoff subtype based on movement pattern.

    Subtypes:
    - STANDARD_FRONTFLIP: Jumped, moved toward ball
    - STANDARD_DIAGONAL: High speed diagonal approach
    - STANDARD_WAVEDASH: Would need mechanics data
    - STANDARD_BOOST: No jump, just boost to ball
    """
    jumped = pdata.get("jumped", False)
    boost_used = max(0.0, pdata["start_boost"] - pdata["min_boost"])
    max_speed = pdata.get("max_speed", 0.0)

    # Without detailed flip direction data, we use simpler heuristics
    if not jumped:
        # No flip = boost-only kickoff
        if boost_used > 10.0:
            return "STANDARD_BOOST"
        return "STANDARD"

    # High speed suggests diagonal flip or speedflip attempt
    if max_speed > 2100.0:
        return "STANDARD_DIAGONAL"

    # Default to frontflip if they jumped
    return "STANDARD_FRONTFLIP"


def _classify_approach_type(pdata: dict[str, Any], kickoff_start_time: float) -> str:
    """Classify kickoff approach type from movement, velocity, and timing data.

    Classification priority:
    1. Fake - didn't contest the ball
    2. Delay - contested but braked before contact
    3. Speedflip - fast time with flip characteristics
    4. Standard subtypes - based on flip/boost pattern
    """
    boost_used = max(0.0, pdata["start_boost"] - pdata["min_boost"])
    max_distance = pdata.get("max_distance", 0.0)

    # 1. Check for fake first (didn't contest)
    is_fake, fake_type = _is_fake_kickoff(pdata)
    if is_fake:
        return fake_type

    # 2. Check for delay (contested but braked)
    if _is_delay_kickoff(pdata):
        return "DELAY"

    # 3. Check for speedflip
    if _is_speedflip_kickoff(pdata):
        return "SPEEDFLIP"

    # 4. Classify standard subtypes
    standard_type = _classify_standard_kickoff(pdata)
    if standard_type != "STANDARD":
        return standard_type

    # Fallback
    if boost_used > 0.0 or max_distance > 150.0:
        return "STANDARD"

    return "UNKNOWN"


def _determine_kickoff_phase(kickoff_start: float, header: Header | None) -> str:
    """Determine kickoff phase (INITIAL vs OT)."""
    if header:
        match_length = float(getattr(header, "match_length", 0.0) or 0.0)
        if getattr(header, "overtime", False) and kickoff_start >= max(
            300.0, match_length
        ):
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
