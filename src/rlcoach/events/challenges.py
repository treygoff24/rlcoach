"""Challenge (50/50) detection for Rocket League replays.

Detects 50/50 challenge events derived from successive opposing touches.
"""

from __future__ import annotations

from ..field_constants import Vec3
from ..parser.types import Frame, PlayerFrame
from .constants import (
    CHALLENGE_MIN_BALL_SPEED_KPH,
    CHALLENGE_MIN_DISTANCE_UU,
    CHALLENGE_RADIUS_UU,
    CHALLENGE_WINDOW_S,
    NEUTRAL_RETOUCH_WINDOW_S,
    RISK_AHEAD_OF_BALL_WEIGHT,
    RISK_LAST_MAN_WEIGHT,
    RISK_LOW_BOOST_THRESHOLD,
    RISK_LOW_BOOST_WEIGHT,
)
from .touches import detect_touches
from .types import ChallengeEvent, TouchEvent
from .utils import distance_3d, nearest_player_ball_frame, team_name


def detect_challenge_events(
    frames: list[Frame], touches: list[TouchEvent] | None = None
) -> list[ChallengeEvent]:
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

        separation = distance_3d(first.location, second.location)
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
        winner_team: str | None = team_name(team_second)

        used_third = False
        if i + 2 < len(touches_sorted):
            third = touches_sorted[i + 2]
            team_third = player_team_idx.get(third.player_id)
            if (
                team_third is not None
                and (third.t - second.t) <= NEUTRAL_RETOUCH_WINDOW_S
                and distance_3d(second.location, third.location) <= CHALLENGE_RADIUS_UU
            ):
                outcome = "NEUTRAL"
                winner_team = None
                used_third = True

        if outcome != "NEUTRAL" and winner_team == team_name(team_first):
            outcome = "WIN"
        elif outcome != "NEUTRAL" and winner_team == team_name(team_second):
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

        pf_first, ball_first = nearest_player_ball_frame(
            frames, first.player_id, first.t
        )
        pf_second, ball_second = nearest_player_ball_frame(
            frames, second.player_id, second.t
        )
        risk_first = _compute_challenge_risk(pf_first, ball_first, team_first)
        risk_second = _compute_challenge_risk(pf_second, ball_second, team_second)

        challenge_events.append(
            ChallengeEvent(
                t=(first.t + second.t) / 2.0,
                first_player=first.player_id,
                second_player=second.player_id,
                first_team=team_name(team_first),
                second_team=team_name(team_second),
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


def _compute_challenge_risk(
    player_frame: PlayerFrame | None,
    ball_state: tuple[Vec3, Vec3] | None,
    team_idx: int | None,
) -> float:
    """Compute risk score for a player entering a challenge."""
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
    low_boost_score = (
        1.0 if player_frame.boost_amount <= RISK_LOW_BOOST_THRESHOLD else 0.0
    )
    last_man_score = 1.0 if last_man else 0.0

    risk = (
        RISK_AHEAD_OF_BALL_WEIGHT * ahead_score
        + RISK_LOW_BOOST_WEIGHT * low_boost_score
        + RISK_LAST_MAN_WEIGHT * last_man_score
    )
    return max(0.0, min(1.0, risk))
