"""Goal detection for Rocket League replays.

Detects goals using either authoritative header metadata or
ball path analysis as a fallback.
"""

from __future__ import annotations

from typing import Any

from ..field_constants import FIELD, Vec3
from ..normalize import measure_frame_rate
from ..parser.types import Header, Frame, PlayerFrame
from ..utils.identity import build_alias_lookup, build_player_identities, sanitize_display_name
from .constants import (
    GOAL_LINE_THRESHOLD,
    GOAL_EXIT_THRESHOLD,
    GOAL_LOOKBACK_WINDOW_S,
    MIN_SHOT_VELOCITY_UU_S,
    TOUCH_PROXIMITY_THRESHOLD,
)
from .types import GoalEvent
from .utils import distance_3d, vector_magnitude, team_name


def detect_goals(frames: list[Frame], header: Header | None = None) -> list[GoalEvent]:
    """Detect goal events, preferring authoritative header metadata."""
    if not frames:
        return []

    if header is not None and getattr(header, "goals", []):
        return _detect_goals_from_header(frames, header)

    return _detect_goals_from_ball_path(frames, header)


def _find_shot_velocity_before_goal(
    frames: list[Frame],
    goal_frame_idx: int,
    frame_rate: float,
) -> Vec3:
    """Find ball velocity before goal explosion physics reset.

    When a goal is scored, the game engine resets ball physics, often
    resulting in zero or near-zero velocity at the goal frame. This function
    scans backwards to find the actual shot velocity.
    """
    if not frames or goal_frame_idx < 0:
        return Vec3(0.0, 0.0, 0.0)

    lookback_frames = int(GOAL_LOOKBACK_WINDOW_S * frame_rate)
    start_idx = max(0, goal_frame_idx - lookback_frames)

    # Scan backwards from the goal frame to find significant velocity
    for i in range(goal_frame_idx - 1, start_idx - 1, -1):
        if i < 0 or i >= len(frames):
            continue
        velocity = frames[i].ball.velocity
        speed = vector_magnitude(velocity)
        if speed >= MIN_SHOT_VELOCITY_UU_S:
            return velocity

    # Fallback: return velocity at goal frame if no significant velocity found
    if 0 <= goal_frame_idx < len(frames):
        return frames[goal_frame_idx].ball.velocity
    return Vec3(0.0, 0.0, 0.0)


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
            dist = distance_3d(player.position, frame.ball.position)
            if dist < TOUCH_PROXIMITY_THRESHOLD:
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

            scorer_team = team_name(getattr(header_goals[goal_index], "player_team", None))
            scorer = _resolve_goal_scorer(header_goals[goal_index], identities, name_lookup, scorer_team)
            assist = _resolve_recent_assist(
                last_touch_times,
                last_touch_by_player,
                scorer,
                scorer_team,
                goal_time,
            )

            # Use lookback to find actual shot velocity (avoids post-goal physics reset)
            ball_velocity = _find_shot_velocity_before_goal(frames, frame_ref_idx, frame_rate)
            ball_pos = frame_ref.ball.position if frame_ref else Vec3(0.0, 0.0, 0.0)
            goal_line_y = FIELD.BACK_WALL_Y if scorer_team == "BLUE" else -FIELD.BACK_WALL_Y
            distance_m = abs(goal_line_y - ball_pos.y) / 100.0
            shot_speed_kph = vector_magnitude(ball_velocity) * 3.6

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
        scorer_team = team_name(getattr(gh, "player_team", None))
        scorer = _resolve_goal_scorer(gh, identities, name_lookup, scorer_team)

        highlight_frame = highlight_frames[goal_index] if goal_index < len(highlight_frames) else None
        tickmark_lead = 0.0
        if highlight_frame is not None and frame_rate > 0:
            delta_frames = max(0, frame_idx - highlight_frame)
            tickmark_lead = delta_frames / frame_rate

        # Use lookback to find actual shot velocity (avoids post-goal physics reset)
        ball_velocity = _find_shot_velocity_before_goal(frames, frame_ref_idx, frame_rate)
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
                shot_speed_kph=vector_magnitude(ball_velocity) * 3.6,
                distance_m=distance_m,
                on_target=scorer is not None,
                tickmark_lead_seconds=round(tickmark_lead, 3),
            )
        )
        goal_index += 1

    return goals


def _resolve_goal_scorer(
    goal_header: Any, identities: list[Any], name_lookup: dict[str, str], team: str | None
) -> str | None:
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
        if team_name(frame.team) != scorer_team:
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
                dist = distance_3d(player.position, frame.ball.position)
                if dist < TOUCH_PROXIMITY_THRESHOLD:
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

            # Use lookback to find actual shot velocity (avoids post-goal physics reset)
            ball_velocity = _find_shot_velocity_before_goal(frames, i, frame_rate)
            ball_speed = vector_magnitude(ball_velocity)
            shot_speed_kph = ball_speed * 3.6

            goal_line_y = GOAL_LINE_THRESHOLD if goal_team == "BLUE" else -GOAL_LINE_THRESHOLD
            distance_m = abs(ball_y - goal_line_y) / 100.0

            header_goal_frame = (
                header_goal_frames[goal_index] if goal_index < len(header_goal_frames) else None
            )
            highlight_frame = highlight_frames[goal_index] if goal_index < len(highlight_frames) else None

            goal_frame_reference = header_goal_frame if header_goal_frame is not None else i
            tickmark_lead = 0.0
            if highlight_frame is not None and frame_rate > 0 and goal_frame_reference is not None:
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
