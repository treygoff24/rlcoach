"""Possession and passing analysis for Rocket League replay data.

This module computes deterministic possession and passing metrics using
synthetic touch sequences and frame data:
- Possession time: team in control if last touch by team within τ seconds
  and ball not traveling toward own half at high speed.
- Passing: attempts/completions/received using teammate touch pairs within
  a fixed time window and forward field progress toward opponent net.
- Turnovers: possession changes between teams on consecutive touches.
- Give-and-go: A->B completed pass followed by B->A completed pass within
  a short window.

Deterministic thresholds (documented):
- POSSESSION_TAU_S: 2.0 seconds window for recent touch control
- OWN_HALF_HIGH_SPEED_UU_S: 1200 UU/s defines "moving hard toward own half"
- PASS_WINDOW_S: 2.0 seconds between teammate touches to qualify
- FORWARD_DELTA_MIN_UU: 200 UU minimum forward progress for a completed pass
- GIVE_AND_GO_WINDOW_S: 3.0 seconds between the two passes

All calculations are local-only and reproducible across runs.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

from ..events import TouchEvent, detect_touches
from ..field_constants import Vec3
from ..parser.types import Frame, Header

# Deterministic thresholds
POSSESSION_TAU_S = 2.0
OWN_HALF_HIGH_SPEED_UU_S = 1200.0
PASS_WINDOW_S = 2.0
FORWARD_DELTA_MIN_UU = 200.0  # Min forward progress for completed pass
GIVE_AND_GO_WINDOW_S = 3.0


def analyze_passing(
    frames: list[Frame],
    events: dict[str, list[Any]] | None = None,
    player_id: str | None = None,
    team: str | None = None,
    header: Header | None = None,
) -> dict[str, Any]:
    """Analyze possession and passing metrics for a player or team.

    Args:
        frames: Normalized frames (used for team mapping and possession time)
        events: Events dict; if 'touches' missing, falls back to detect_touches
        player_id: Analyze a specific player if provided
        team: Analyze a specific team ("BLUE" or "ORANGE") if provided
        header: Unused for now; reserved for context

    Returns:
        Dict with passing metrics matching schema:
        {
            "passes_completed": int,
            "passes_attempted": int,
            "passes_received": int,
            "turnovers": int,
            "give_and_go_count": int,
            "possession_time_s": float
        }
    """
    # Base case: handle empty data gracefully
    if not frames and not events:
        return _empty_passing()

    # Build player->team mapping from frames
    player_team = _extract_players_from_frames(frames)

    # Gather touches
    touches: list[TouchEvent] = []
    if events and isinstance(events.get("touches"), list):
        touches = list(events.get("touches", []))
    if not touches and frames:
        # Deterministic fallback: derive touches from frames
        touches = detect_touches(frames)

    # Sort touches chronologically
    touches.sort(key=lambda t: t.t)

    # Compute possession time for each team
    team_possession = _compute_possession_time(frames, touches)

    # Compute pass/turnover metrics from touch sequence
    team_metrics, player_metrics = _compute_pass_metrics(touches, player_team)

    # Return scoped result
    if player_id:
        # Resolve player's team for possession attribution
        player_team_name = player_team.get(player_id)
        possession_time = 0.0
        if player_team_name:
            possession_time = (
                team_possession[0] if player_team_name == "BLUE" else team_possession[1]
            )
        pm = player_metrics.get(player_id, _zero_counts())
        return {
            "passes_completed": pm["completed"],
            "passes_attempted": pm["attempted"],
            "passes_received": pm["received"],
            "turnovers": pm["turnovers"],
            "give_and_go_count": pm["give_and_go"],
            "possession_time_s": round(possession_time, 2),
        }
    elif team:
        team_name = team.upper()
        team_idx = 0 if team_name == "BLUE" else 1
        tm = team_metrics[team_idx]
        return {
            "passes_completed": tm["completed"],
            "passes_attempted": tm["attempted"],
            "passes_received": tm["received"],
            "turnovers": tm["turnovers"],
            "give_and_go_count": tm["give_and_go"],
            "possession_time_s": round(team_possession[team_idx], 2),
        }
    else:
        # No specific scope: return empty
        return _empty_passing()


def _compute_possession_time(
    frames: list[Frame], touches: list[TouchEvent]
) -> tuple[float, float]:
    """Compute possession time for BLUE and ORANGE teams.

    Team in control at time t if:
    - Latest touch by that team occurred within POSSESSION_TAU_S
    - Ball not traveling toward that team's own half at high speed
    """
    if not frames:
        return 0.0, 0.0

    blue_poss = 0.0
    orange_poss = 0.0

    # Prepare fast access to last touch times by team
    last_touch_time = {0: None, 1: None}  # team index -> time

    # Build player->team index mapping (0 blue, 1 orange)
    player_team_idx: dict[str, int] = {}
    for f in frames:
        for p in f.players:
            if p.player_id not in player_team_idx:
                player_team_idx[p.player_id] = 0 if p.team == 0 else 1

    # Iterate frames accumulating possession time
    touch_i = 0
    n = len(frames)
    for idx, frame in enumerate(frames):
        # Advance touch pointer and update last touch records
        while touch_i < len(touches) and touches[touch_i].t <= frame.timestamp:
            toucher = touches[touch_i].player_id
            team_idx = player_team_idx.get(toucher)
            if team_idx is not None:
                last_touch_time[team_idx] = touches[touch_i].t
            touch_i += 1

        # Determine dt to next frame (or estimate based on previous dt)
        if idx < n - 1:
            dt = frames[idx + 1].timestamp - frame.timestamp
        elif n >= 2:
            dt = frames[idx].timestamp - frames[idx - 1].timestamp
        else:
            dt = 0.0

        # Skip zero/negative dt
        if dt <= 0:
            continue

        # Ball velocity sign indicates direction along field Y-axis
        vy = frame.ball.velocity.y

        # BLUE own half is negative Y; ORANGE own half is positive Y
        blue_has_recent_touch = (
            last_touch_time[0] is not None
            and (frame.timestamp - last_touch_time[0]) <= POSSESSION_TAU_S
        )
        orange_has_recent_touch = (
            last_touch_time[1] is not None
            and (frame.timestamp - last_touch_time[1]) <= POSSESSION_TAU_S
        )

        if blue_has_recent_touch and not (vy < -OWN_HALF_HIGH_SPEED_UU_S):
            blue_poss += dt
        if orange_has_recent_touch and not (vy > OWN_HALF_HIGH_SPEED_UU_S):
            orange_poss += dt

    return blue_poss, orange_poss


def _compute_pass_metrics(
    touches: list[TouchEvent], player_team: dict[str, str]
) -> tuple[list[dict[str, int]], dict[str, dict[str, int]]]:
    """Compute pass attempts/completions/received, turnovers, and give-and-go.

    Returns a tuple of:
      - team_metrics: [blue_dict, orange_dict]
      - player_metrics: dict[player_id] -> counts dict
    """
    # Initialize team metrics
    team_metrics = [
        {
            "attempted": 0,
            "completed": 0,
            "received": 0,
            "turnovers": 0,
            "give_and_go": 0,
        },  # BLUE
        {
            "attempted": 0,
            "completed": 0,
            "received": 0,
            "turnovers": 0,
            "give_and_go": 0,
        },  # ORANGE
    ]

    # Initialize per-player metrics lazily
    player_metrics: dict[str, dict[str, int]] = {}

    def ensure_player(pid: str) -> None:
        if pid not in player_metrics:
            player_metrics[pid] = _zero_counts()

    def team_idx_for(pid: str) -> int | None:
        tname = player_team.get(pid)
        if tname == "BLUE":
            return 0
        if tname == "ORANGE":
            return 1
        return None

    # Track last completed pass for give-and-go detection
    last_completed: tuple[str, str, float] | None = None  # (from_id, to_id, t)

    for i in range(len(touches) - 1):
        a = touches[i]
        b = touches[i + 1]
        if a.player_id == b.player_id:
            # Ignore self touches for pass logic
            continue

        a_team = team_idx_for(a.player_id)
        b_team = team_idx_for(b.player_id)
        if a_team is None or b_team is None:
            continue

        # Turnover detection: team changes on consecutive touches
        if a_team != b_team:
            # Attribute turnover to team that last touched (lost possession)
            team_metrics[a_team]["turnovers"] += 1
            ensure_player(a.player_id)
            player_metrics[a.player_id]["turnovers"] += 1
            # No pass attempt/completion on enemy touch
            continue

        # Same team: potential pass
        dt = b.t - a.t
        if dt <= 0 or dt > PASS_WINDOW_S:
            # Too slow or invalid ordering
            continue

        # Count an attempted pass by passer regardless of forward-ness
        team_metrics[a_team]["attempted"] += 1
        ensure_player(a.player_id)
        ensure_player(b.player_id)
        player_metrics[a.player_id]["attempted"] += 1

        # Forward progress toward opponent goal required for completion
        forward_ok = _is_forward_progress(a.location, b.location, a_team)
        if not forward_ok:
            continue

        # Completed pass
        team_metrics[a_team]["completed"] += 1
        team_metrics[a_team]["received"] += 1
        player_metrics[a.player_id]["completed"] += 1
        player_metrics[b.player_id]["received"] += 1

        # Give-and-go: last was B<-A and now A<-B within window
        if last_completed is not None:
            last_from, last_to, last_t = last_completed
            if (
                last_from == b.player_id
                and last_to == a.player_id
                and (a.t - last_t) <= GIVE_AND_GO_WINDOW_S
            ):
                team_metrics[a_team]["give_and_go"] += 1
                # Attribute to both players for per-player counts
                player_metrics[a.player_id]["give_and_go"] += 1
                player_metrics[b.player_id]["give_and_go"] += 1

        # Update last completed pass record
        last_completed = (a.player_id, b.player_id, a.t)

    return team_metrics, player_metrics


def _is_forward_progress(pos_from: Vec3, pos_to: Vec3, team_idx: int) -> bool:
    """Check if movement from pos_from to pos_to advances toward opponent goal."""

    delta_x = pos_to.x - pos_from.x
    delta_y = pos_to.y - pos_from.y
    attack_vector = (0.0, 1.0) if team_idx == 0 else (0.0, -1.0)
    forward_component = delta_x * attack_vector[0] + delta_y * attack_vector[1]

    if forward_component < FORWARD_DELTA_MIN_UU:
        return False

    planar_distance = math.hypot(delta_x, delta_y)
    return planar_distance >= FORWARD_DELTA_MIN_UU


def _extract_players_from_frames(frames: Iterable[Frame]) -> dict[str, str]:
    """Extract mapping of player_id -> team name ("BLUE"/"ORANGE")."""
    players: dict[str, str] = {}
    for frame in frames:
        for p in frame.players:
            if p.player_id not in players:
                players[p.player_id] = "BLUE" if p.team == 0 else "ORANGE"
    return players


def _zero_counts() -> dict[str, int]:
    return {
        "attempted": 0,
        "completed": 0,
        "received": 0,
        "turnovers": 0,
        "give_and_go": 0,
    }


def _empty_passing() -> dict[str, Any]:
    return {
        "passes_completed": 0,
        "passes_attempted": 0,
        "passes_received": 0,
        "turnovers": 0,
        "give_and_go_count": 0,
        "possession_time_s": 0.0,
    }
