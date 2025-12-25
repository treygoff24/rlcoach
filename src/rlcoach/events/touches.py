"""Touch detection for Rocket League replays.

Detects player-ball contact events with context classification
(ground, aerial, wall, etc.) and outcome classification.
"""

from __future__ import annotations

from ..field_constants import FIELD, Vec3
from ..parser.types import Frame, PlayerFrame
from ..physics_constants import UU_S_TO_KPH
from .constants import (
    TOUCH_PROXIMITY_THRESHOLD,
    TOUCH_DEBOUNCE_TIME,
    TOUCH_LOCATION_EPS,
    MIN_BALL_SPEED_FOR_TOUCH,
    MIN_RELATIVE_SPEED_FOR_TOUCH,
    WALL_PROXIMITY_THRESHOLD,
    CEILING_HEIGHT_THRESHOLD,
    AERIAL_HEIGHT_THRESHOLD,
    HALF_VOLLEY_HEIGHT,
)
from .types import TouchEvent, TouchContext
from .utils import (
    distance_3d,
    vector_magnitude,
    relative_speed,
    is_toward_opponent_goal,
    is_toward_own_goal,
    is_shot_on_target,
    is_in_defensive_third,
)


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
        ball_speed = vector_magnitude(ball_velocity)

        for player in frame.players:
            dist = distance_3d(player.position, frame.ball.position)
            if dist >= TOUCH_PROXIMITY_THRESHOLD:
                continue

            prev_event = last_touch_event.get(player.player_id)
            if prev_event is not None:
                delta_t = frame.timestamp - prev_event.t
                if delta_t < 0.05:
                    continue
                same_area = distance_3d(player.position, prev_event.location) <= TOUCH_LOCATION_EPS
                if same_area and delta_t < TOUCH_DEBOUNCE_TIME:
                    rel_speed = relative_speed(player.velocity, frame.ball.velocity)
                    if ball_speed < MIN_BALL_SPEED_FOR_TOUCH and rel_speed < MIN_RELATIVE_SPEED_FOR_TOUCH:
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


def _classify_touch_outcome(
    player: PlayerFrame,
    frame: Frame,
    prev_ball_velocity: Vec3 | None,
    prev_ball_position: Vec3 | None,
) -> tuple[str, bool]:
    """Return (outcome, is_save) for a detected touch."""
    ball_velocity = frame.ball.velocity
    ball_speed = vector_magnitude(ball_velocity)
    team_idx = 0 if player.team == 0 else 1

    if ball_speed > 1500.0:
        return "SHOT", False

    shot_on_target = is_shot_on_target(team_idx, frame.ball.position, ball_velocity)

    if shot_on_target and ball_speed >= 650.0:
        return "SHOT", False

    is_save_touch = False
    if prev_ball_velocity is not None and prev_ball_position is not None:
        if is_toward_own_goal(team_idx, prev_ball_velocity) and not is_toward_own_goal(
            team_idx, ball_velocity
        ):
            if is_in_defensive_third(team_idx, prev_ball_position):
                is_save_touch = True

    if is_save_touch:
        return "CLEAR", True

    if ball_speed > 900.0 and is_toward_opponent_goal(team_idx, ball_velocity):
        return "PASS", False

    if ball_speed < 250.0:
        return "DRIBBLE", False

    if ball_speed > 600.0 and is_toward_opponent_goal(team_idx, ball_velocity):
        return "PASS", False

    return "NEUTRAL", False
