"""Boost pickup detection for Rocket League replays.

Detects boost pad pickups using either parser-provided pad events
or legacy heuristics based on boost deltas.
"""

from __future__ import annotations

import json
import os
from collections import deque
from dataclasses import replace
from pathlib import Path
from typing import Any

from ..field_constants import FIELD, BoostPad, Vec3
from ..parser.types import Frame
from .constants import (
    BIG_PAD_MIN_GAIN,
    BIG_PAD_RESPAWN_S,
    BOOST_HISTORY_MAX_SAMPLES,
    BOOST_HISTORY_WINDOW_S,
    BOOST_PICKUP_MERGE_WINDOW,
    BOOST_PICKUP_MIN_GAIN,
    CHAIN_PAD_RADIUS,
    DEBUG_BOOST_ENV,
    MIN_ORIENTATION_SAMPLES,
    PAD_ENVELOPES,
    PAD_NEUTRAL_TOLERANCE,
    PAD_RESPAWN_TOLERANCE,
    RESPAWN_BOOST_AMOUNT,
    RESPAWN_DISTANCE_THRESHOLD,
    SMALL_PAD_RESPAWN_S,
)
from .types import BoostPickupEvent, PadState
from .utils import distance_3d


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


def _frames_have_pad_events(frames: list[Frame]) -> bool:
    """Return True if any frame includes boost pad events from the parser."""
    for frame in frames:
        events = getattr(frame, "boost_pad_events", None)
        if events:
            return True
    return False


def _detect_boost_pickups_from_pad_events(
    frames: list[Frame],
) -> list[BoostPickupEvent]:
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
                    "Missing player attribution for boost pad event; "
                    "falling back to legacy detection"
                )

            player_frame = players_by_id.get(player_id)
            player_team = getattr(event, "player_team", None)
            if player_team not in (0, 1) and player_frame is not None:
                player_team = player_frame.team

            event_time = getattr(event, "timestamp", None)
            timestamp = float(event_time) if event_time is not None else frame.timestamp

            respawn_window = (
                BIG_PAD_RESPAWN_S if pad_meta.is_big else SMALL_PAD_RESPAWN_S
            )
            last_collect = pad_last_collect.get(pad_meta.pad_id)
            if last_collect is not None and (timestamp - last_collect) < (
                respawn_window - PAD_RESPAWN_TOLERANCE
            ):
                continue

            previous_boost = player_boost.get(player_id)
            current_boost = (
                float(player_frame.boost_amount) if player_frame is not None else None
            )
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
                    boost_after = min(
                        100.0, boost_before + min(pad_capacity, available_room)
                    )
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


def _detect_boost_pickups_legacy(frames: list[Frame]) -> list[BoostPickupEvent]:
    """Legacy heuristic detection of boost pickup events from boost deltas."""
    if not frames:
        return []

    pickups: list[BoostPickupEvent] = []
    player_state: dict[str, dict[str, Any]] = {}
    recent_pickup_index: dict[tuple[str, int], tuple[int, float]] = {}
    pad_states: dict[int, PadState] = {
        pad.pad_id: PadState() for pad in FIELD.BOOST_PADS
    }
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
                if (
                    matched_pad.is_big
                    or boost_increase <= (100.0 if matched_pad.is_big else 12.0) + 1.0
                ):
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
                    respawn = (
                        BIG_PAD_RESPAWN_S if matched_pad.is_big else SMALL_PAD_RESPAWN_S
                    )
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
                    if (
                        existing is not None
                        and frame_time - existing[1] <= BOOST_PICKUP_MERGE_WINDOW
                    ):
                        event_idx, _ = existing
                        prev_event = pickups[event_idx]
                        updated_gain = prev_event.boost_gain + max(
                            0.0, event.boost_gain
                        )
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
                            "decision": decision_debug
                            | ({"chain_index": idx} if idx else {}),
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
        distance, closest_time, height_delta = _minimum_distance_to_pad(
            history, pad.position
        )
        time_in_envelope = max(0.0, timestamp - closest_time)
        inside_radius = distance <= envelope.radius

        if distance > envelope.max_distance:
            # Still consider as low-confidence candidate with penalty.
            distance_penalty = (distance - envelope.max_distance) / max(
                envelope.radius, 1.0
            )
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
        score = (
            distance_score
            + 0.6 * gain_score
            + 0.1 * time_in_envelope
            + distance_penalty
        )
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

    return best_pad, {
        "candidates": candidates,
        "selected_pad": best_pad.pad_id if best_pad else None,
    }


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
        distance = distance_3d(pos, pad_position)
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
        distance = distance_3d(last_pos, pad.position)
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
    return best_pad, {
        "reason": "capacity_adjusted_nearest",
        "score": best_score,
        "candidates": debug_candidates,
    }


def _nearest_pad_distance(history: deque[tuple[float, Vec3]]) -> float:
    """Approximate nearest boost pad distance using latest position."""
    if not history:
        return float("inf")
    last_pos = history[-1][1]
    best = float("inf")
    for pad in FIELD.BOOST_PADS:
        dist = distance_3d(last_pos, pad.position)
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
            last.location
            and event.location
            and distance_3d(last.location, event.location) <= 320.0
        )
        same_pad = (
            last.pad_id >= 0 and event.pad_id >= 0 and last.pad_id == event.pad_id
        )
        no_location = last.location is None and event.location is None
        if same_player and near_time and (same_pad or near_space or no_location):
            merged_gain = max(0.0, last.boost_gain + max(0.0, event.boost_gain))
            merged_after = (
                event.boost_after if event.boost_after is not None else last.boost_after
            )
            merged_before = (
                last.boost_before
                if last.boost_before is not None
                else event.boost_before
            )
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
        distance, closest_time, height_delta = _minimum_distance_to_pad(
            history, pad.position
        )
        if distance > CHAIN_PAD_RADIUS or height_delta > 260.0:
            continue
        if timestamp < pad_states[pad.pad_id].available_at - PAD_RESPAWN_TOLERANCE:
            continue
        candidates.append((closest_time, distance, pad))
        seen.add(pad.pad_id)

    if primary_pad.pad_id not in seen:
        distance = distance_3d(history[-1][1], primary_pad.position)
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
    ordered_pads = _order_small_pad_candidates(
        history, pad_states, timestamp, matched_pad
    )
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
