"""Challenges/50-50s analysis.

Derives contest counts and outcomes from touch sequences with deterministic
thresholds. Computes first-to-ball percentage, average challenge depth, and a
simple risk index based on player context at the time of the contest.

Deterministic thresholds:
- CHALLENGE_WINDOW_S = 1.2  (max time between opposing touches to form a contest)
- CHALLENGE_RADIUS_UU = 1000.0 (max spatial separation between opposing touches)
- NEUTRAL_RETOUCH_WINDOW_S = 0.25 (rapid re-contest yields neutral)

Risk index factors (0..1), weights sum to 1:
- ahead_of_ball_weight = 0.4  (player is ahead of ball for their team)
- low_boost_weight = 0.3      (boost <= 20)
- last_man_weight = 0.3       (furthest back relative to own goal)

All computations are local-only and reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..parser.types import Header, Frame, PlayerFrame
from ..field_constants import Vec3
from ..events import TouchEvent, detect_touches


CHALLENGE_WINDOW_S = 1.2
CHALLENGE_RADIUS_UU = 1000.0
NEUTRAL_RETOUCH_WINDOW_S = 0.25

RISK_LOW_BOOST_THRESHOLD = 20
RISK_AHEAD_OF_BALL_WEIGHT = 0.4
RISK_LOW_BOOST_WEIGHT = 0.3
RISK_LAST_MAN_WEIGHT = 0.3


def analyze_challenges(
    frames: list[Frame],
    events: dict[str, list[Any]] | None = None,
    player_id: str | None = None,
    team: str | None = None,
    header: Header | None = None,
) -> dict[str, Any]:
    """Analyze 50/50 contests and compute outcome metrics.

    Returns schema-aligned dict with:
      contests, wins, losses, neutral, first_to_ball_pct,
      challenge_depth_m, risk_index_avg
    """
    touches: list[TouchEvent] = []
    if events and isinstance(events.get("touches"), list):
        touches = list(events.get("touches", []))
    if not touches and frames:
        touches = detect_touches(frames)

    touches.sort(key=lambda t: t.t)

    # Player -> team index mapping and helper lookups
    player_team_idx: dict[str, int] = {}
    for f in frames:
        for p in f.players:
            if p.player_id not in player_team_idx:
                player_team_idx[p.player_id] = 0 if p.team == 0 else 1

    # Aggregators per team (0=BLUE, 1=ORANGE)
    contests = [0, 0]
    wins = [0, 0]
    losses = [0, 0]
    neutral = [0, 0]
    first_to_ball = [0, 0]
    depth_sum_m = [0.0, 0.0]
    risk_sum = [0.0, 0.0]
    risk_count = [0, 0]

    # Per-player aggregators (for player scope)
    p_contests = {}
    p_wins = {}
    p_losses = {}
    p_neutral = {}
    p_first = {}
    p_risk_sum = {}
    p_risk_count = {}
    p_depth_sum_m = {}

    def ensure_player(pid: str):
        p_contests.setdefault(pid, 0)
        p_wins.setdefault(pid, 0)
        p_losses.setdefault(pid, 0)
        p_neutral.setdefault(pid, 0)
        p_first.setdefault(pid, 0)
        p_risk_sum.setdefault(pid, 0.0)
        p_risk_count.setdefault(pid, 0)
        p_depth_sum_m.setdefault(pid, 0.0)

    # Iterate consecutive touches to find contests
    i = 0
    while i < len(touches) - 1:
        a = touches[i]
        b = touches[i + 1]
        if a.player_id == b.player_id:
            continue

        a_team = player_team_idx.get(a.player_id)
        b_team = player_team_idx.get(b.player_id)
        if a_team is None or b_team is None or a_team == b_team:
            continue

        dt = b.t - a.t
        if dt <= 0 or dt > CHALLENGE_WINDOW_S:
            i += 1
            continue

        # Spatial proximity check
        if _distance(a.location, b.location) > CHALLENGE_RADIUS_UU:
            i += 1
            continue

        # This pair (a,b) forms a contest
        contests[a_team] += 1
        contests[b_team] += 1
        first_to_ball[a_team] += 1  # team of first touch

        ensure_player(a.player_id)
        ensure_player(b.player_id)
        p_contests[a.player_id] += 1
        p_contests[b.player_id] += 1
        p_first[a.player_id] += 1

        # Determine neutral/win/loss from immediate follow-up
        outcome_neutral = False
        if i + 2 < len(touches):
            c = touches[i + 2]
            c_team = player_team_idx.get(c.player_id)
            if c_team is not None and (c.t - b.t) <= NEUTRAL_RETOUCH_WINDOW_S and _distance(b.location, c.location) <= CHALLENGE_RADIUS_UU:
                outcome_neutral = True

        # Depth measured at mid-point between the two touches (absolute meters)
        depth_y = (a.location.y + b.location.y) / 2.0
        depth_m = abs(depth_y) * 0.019
        depth_sum_m[a_team] += depth_m
        depth_sum_m[b_team] += depth_m
        p_depth_sum_m[a.player_id] += depth_m
        p_depth_sum_m[b.player_id] += depth_m

        if outcome_neutral:
            neutral[a_team] += 1
            neutral[b_team] += 1
            p_neutral[a.player_id] += 1
            p_neutral[b.player_id] += 1
        else:
            # Winner is team of second touch
            wins[b_team] += 1
            losses[a_team] += 1
            p_wins[b.player_id] += 1
            p_losses[a.player_id] += 1

        # Risk index for initiating players (both sides separately)
        for pid, tstamp in ((a.player_id, a.t), (b.player_id, b.t)):
            r_team = player_team_idx.get(pid)
            if r_team is None:
                continue
            pf, bf = _nearest_player_ball_frame(frames, pid, tstamp)
            risk = _compute_risk_index(pf, bf, r_team)
            risk_sum[r_team] += risk
            risk_count[r_team] += 1
            p_risk_sum[pid] += risk
            p_risk_count[pid] += 1

        # Advance index by 2 to avoid double-counting overlapping A-B, B-A pairs
        i += 2

    # Compose results
    def compose(contests_c, wins_c, losses_c, neutral_c, first_c, depth_sum, risk_sum_v, risk_cnt) -> dict[str, Any]:
        first_pct = (first_c / contests_c * 100.0) if contests_c > 0 else 0.0
        depth_avg = (depth_sum / contests_c) if contests_c > 0 else 0.0
        risk_avg = (risk_sum_v / risk_cnt) if risk_cnt > 0 else 0.0
        return {
            "contests": contests_c,
            "wins": wins_c,
            "losses": losses_c,
            "neutral": neutral_c,
            "first_to_ball_pct": round(first_pct, 1),
            "challenge_depth_m": round(depth_avg, 2),
            "risk_index_avg": round(risk_avg, 2),
        }

    if player_id:
        c = p_contests.get(player_id, 0)
        w = p_wins.get(player_id, 0)
        l = p_losses.get(player_id, 0)
        n = p_neutral.get(player_id, 0)
        f = p_first.get(player_id, 0)
        dsum = p_depth_sum_m.get(player_id, 0.0)
        rsum = p_risk_sum.get(player_id, 0.0)
        rcnt = p_risk_count.get(player_id, 0)
        return compose(c, w, l, n, f, dsum, rsum, rcnt)

    if team:
        t_idx = 0 if team.upper() == "BLUE" else 1
        return compose(
            contests[t_idx],
            wins[t_idx],
            losses[t_idx],
            neutral[t_idx],
            first_to_ball[t_idx],
            depth_sum_m[t_idx],
            risk_sum[t_idx],
            risk_count[t_idx],
        )

    # No scope provided
    return compose(0, 0, 0, 0, 0, 0.0, 0.0, 0)


def _distance(a: Vec3, b: Vec3) -> float:
    dx = a.x - b.x
    dy = a.y - b.y
    dz = a.z - b.z
    return (dx * dx + dy * dy + dz * dz) ** 0.5


def _nearest_player_ball_frame(frames: list[Frame], player_id: str, t: float) -> tuple[PlayerFrame | None, tuple[Vec3, Vec3] | None]:
    """Find the player frame and (ball_pos, ball_vel) nearest in time to t."""
    if not frames:
        return None, None
    best = None
    best_dt = float("inf")
    for fr in frames:
        dt = abs(fr.timestamp - t)
        if dt < best_dt:
            best_dt = dt
            best = fr
    if not best:
        return None, None
    pf = best.get_player_by_id(player_id)
    return pf, (best.ball.position, best.ball.velocity)


def _compute_risk_index(pf: PlayerFrame | None, ball: tuple[Vec3, Vec3] | None, team_idx: int) -> float:
    if pf is None or ball is None:
        return 0.0
    ball_pos, _ball_vel = ball
    # Ahead-of-ball: relative to attacking direction (BLUE attacks +Y, ORANGE attacks -Y)
    ahead = False
    if team_idx == 0:  # BLUE
        ahead = pf.position.y > ball_pos.y
    else:  # ORANGE
        ahead = pf.position.y < ball_pos.y
    ahead_score = 1.0 if ahead else 0.0

    low_boost_score = 1.0 if pf.boost_amount <= RISK_LOW_BOOST_THRESHOLD else 0.0

    # Last-man back: furthest back relative to own goal
    # Need team context; approximate using current frame's teammates
    # We lack teammate list here; infer from available attributes by returning 0.0
    # unless frame contains teammates (handled in caller via nearest frame)
    # We'll approximate last-man back using sign on Y only: deeper into own half than ball
    if team_idx == 0:  # BLUE own half is negative Y
        last_man_back = pf.position.y <= ball_pos.y
    else:
        last_man_back = pf.position.y >= ball_pos.y
    last_man_score = 1.0 if last_man_back else 0.0

    risk = (
        RISK_AHEAD_OF_BALL_WEIGHT * ahead_score
        + RISK_LOW_BOOST_WEIGHT * low_boost_score
        + RISK_LAST_MAN_WEIGHT * last_man_score
    )
    return max(0.0, min(1.0, float(risk)))
