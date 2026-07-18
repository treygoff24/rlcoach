"""Optional input-timeline solver adapter.

This module is the S2 consumption surface for reconstructed player inputs.
`rlinput_py` is optional: if the wheel is missing, or
`RLCOACH_INPUT_SOLVER=off`, the public solver returns ``None`` and the normal
analysis/report pipeline is unchanged.

WP8 contract state: the Rust boundary currently returns segmentation plus
seeded component-edge events. Per-frame input samples stay empty until the WP7
fit/channel solver plugs into the same ``solve_timeline(payload, config)``
interface.
"""

from __future__ import annotations

import importlib
import math
import os
from dataclasses import dataclass
from typing import Any

from .parser.types import Frame, Header, Rotation


@dataclass(frozen=True)
class ChannelValue:
    """One solved or observed input-channel value."""

    value: float | bool
    source: str
    confidence: float
    flags: int = 0


@dataclass(frozen=True)
class InputSample:
    """One recorded-frame interval from the input timeline."""

    frame_index: int
    tick_range: tuple[int, int]
    time_range: tuple[float, float]
    throttle: ChannelValue
    steer: ChannelValue
    pitch: ChannelValue
    yaw: ChannelValue
    roll: ChannelValue
    jump: ChannelValue
    boost: ChannelValue
    handbrake: ChannelValue


@dataclass(frozen=True)
class SolvedEvent:
    """Discrete input/event edge reconstructed by the solver."""

    kind: str
    tick: int
    t: float
    frame_index: int
    confidence: float
    flags: int = 0
    detail: dict[str, Any] | None = None


@dataclass(frozen=True)
class SegmentSummary:
    """Solver segment summary mirrored from Rust."""

    id: int
    tick_span: tuple[int, int]
    boundary_causes: tuple[str, ...]
    confidence: float


@dataclass(frozen=True)
class InputTimeline:
    """Per-player solved input timeline."""

    player_id: str
    samples: tuple[InputSample, ...]
    events: tuple[SolvedEvent, ...]
    segments: tuple[SegmentSummary, ...]
    coverage: dict[str, Any]
    diagnostics: dict[str, Any]


def solve_input_timelines(
    frames: list[Frame],
    header: Header | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, InputTimeline] | None:
    """Build the columnar payload, call ``rlinput_py``, and mirror output.

    Returns ``None`` when the solver is disabled or unavailable.
    """

    if os.getenv("RLCOACH_INPUT_SOLVER", "").strip().lower() == "off":
        return None

    solver = _load_solver()
    if solver is None:
        return None

    payload = build_solver_payload(frames, header)
    if not payload["players"]:
        return None

    raw = solver.solve_timeline(payload, config or {})
    return mirror_solve_output(raw)


def build_solver_payload(
    frames: list[Frame],
    header: Header | None = None,
) -> dict[str, Any]:
    """Build the no-JSON pyo3 payload expected by ``rlinput_py``."""

    player_ids = _complete_player_ids(frames)
    component_events: dict[str, list[dict[str, Any]]] = {
        player_id: [] for player_id in player_ids
    }
    touch_events: list[dict[str, Any]] = []
    demo_events: list[dict[str, Any]] = []
    kickoff_markers: list[dict[str, Any]] = []

    for frame_index, frame in enumerate(frames):
        for event in frame.component_events:
            if event.player_id not in component_events:
                continue
            kind = _component_kind(event.kind, event.component)
            if kind is None:
                continue
            component_events[event.player_id].append(
                {
                    "t": float(event.timestamp),
                    "frame_index": frame_index,
                    "component": kind,
                    "vector": _vec3_list(event.vector) if event.vector else None,
                    "raw_value": event.raw_value,
                }
            )

        for event in frame.parser_touch_events:
            touch_events.append(
                {
                    "t": float(event.timestamp),
                    "frame_index": frame_index,
                    "player_id": event.player_id,
                    "team": event.team,
                }
            )

        for event in frame.parser_demo_events:
            demo_events.append(
                {
                    "t": float(event.timestamp),
                    "frame_index": frame_index,
                    "victim_id": event.victim_id,
                    "attacker_id": event.attacker_id,
                }
            )

        for event in frame.parser_kickoff_markers:
            kickoff_markers.append(
                {
                    "t": float(event.timestamp),
                    "frame_index": frame_index,
                    "phase": event.phase,
                }
            )

    players = []
    for player_id in player_ids:
        stream = [frame.get_player_by_id(player_id) for frame in frames]
        player_frames = [player for player in stream if player is not None]
        if len(player_frames) != len(frames):
            continue
        players.append(
            {
                "player_id": player_id,
                "frames": {
                    "pos": _flat_vec3(player.position for player in player_frames),
                    "vel": _flat_vec3(player.velocity for player in player_frames),
                    "quat_xyzw": _flat_quat(
                        player.rotation for player in player_frames
                    ),
                    "ang_vel": _flat_vec3(
                        player.angular_velocity for player in player_frames
                    ),
                    "on_ground": [
                        bool(player.is_on_ground) for player in player_frames
                    ],
                    "sleeping": [bool(player.sleeping) for player in player_frames],
                    "demolished": [
                        bool(player.is_demolished) for player in player_frames
                    ],
                },
                "replicated": {
                    "throttle_raw": [
                        _raw_byte(player.throttle_raw, 128) for player in player_frames
                    ],
                    "steer_raw": [
                        _raw_byte(player.steer_raw, 128) for player in player_frames
                    ],
                    "handbrake": [bool(player.handbrake) for player in player_frames],
                    "boost_amount_raw": [
                        _raw_byte(player.boost_amount_raw, int(player.boost_amount))
                        for player in player_frames
                    ],
                    "boost_active_raw": [
                        _boost_active_bool(player) for player in player_frames
                    ],
                },
                "component": {
                    "jump_raw": [
                        _raw_byte(player.jump_active_raw, 0) for player in player_frames
                    ],
                    "dodge_raw": [
                        _raw_byte(player.dodge_active_raw, 0)
                        for player in player_frames
                    ],
                    "double_jump_raw": [
                        _raw_byte(player.double_jump_active_raw, 0)
                        for player in player_frames
                    ],
                    "boost_raw": [
                        _raw_byte(player.boost_active_raw, 0)
                        for player in player_frames
                    ],
                    "events": component_events[player_id],
                },
            }
        )

    return {
        "tick_rate": 120.0,
        "build_bucket": getattr(header, "engine_build", None) or "unknown",
        "players": players,
        "ball": {
            "pos": _flat_vec3(frame.ball.position for frame in frames),
            "vel": _flat_vec3(frame.ball.velocity for frame in frames),
        },
        "deltas": _deltas(frames),
        "demo_events": demo_events,
        "touch_events": touch_events,
        "kickoff_markers": kickoff_markers,
    }


def mirror_solve_output(raw: dict[str, Any]) -> dict[str, InputTimeline]:
    """Mirror Rust plain dict/list output into frozen dataclasses keyed by player."""

    coverage = dict(raw.get("coverage") or {})
    diagnostics = dict(raw.get("diagnostics") or {})
    timelines = (
        _timeline_from_dict(item, coverage, diagnostics)
        for item in raw.get("timelines", []) or []
    )
    return {timeline.player_id: timeline for timeline in timelines}


def _load_solver() -> Any | None:
    try:
        return importlib.import_module("rlinput_py")
    except ImportError:
        return None


def _complete_player_ids(frames: list[Frame]) -> list[str]:
    player_sets = [
        {player.player_id for player in frame.players}
        for frame in frames
        if frame.players
    ]
    if not player_sets:
        return []
    return sorted(set.intersection(*player_sets))


def _deltas(frames: list[Frame]) -> list[float]:
    if not frames:
        return []
    deltas = [0.0]
    for index in range(1, len(frames)):
        explicit = frames[index].delta
        if explicit is not None and explicit >= 0:
            deltas.append(float(explicit))
        else:
            deltas.append(
                max(0.0, float(frames[index].timestamp - frames[index - 1].timestamp))
            )
    return deltas


def _component_kind(kind: str, component: str) -> str | None:
    if kind == "dodge_torque":
        return "DodgeTorque"
    if kind == "double_jump_impulse":
        return "DoubleJumpImpulse"
    return {
        "jump": "Jump",
        "dodge": "DodgeTorque",
        "double_jump": "DoubleJumpImpulse",
        "boost": "Boost",
    }.get(component)


def _boost_active_bool(player: Any) -> bool:
    if player.boost_active is not None:
        return bool(player.boost_active)
    if player.boost_active_raw is not None:
        return bool(player.boost_active_raw)
    return False


def _raw_byte(value: int | None, default: int) -> int:
    if value is None:
        value = default
    return max(0, min(255, int(value)))


def _flat_vec3(values: Any) -> list[float]:
    out: list[float] = []
    for value in values:
        out.extend(_vec3_list(value))
    return out


def _vec3_list(value: Any) -> list[float]:
    if value is None:
        return [0.0, 0.0, 0.0]
    return [float(value.x), float(value.y), float(value.z)]


def _flat_quat(values: Any) -> list[float]:
    out: list[float] = []
    for value in values:
        out.extend(_quat_xyzw(value))
    return out


def _quat_xyzw(rotation: Any) -> list[float]:
    if isinstance(rotation, Rotation) and rotation.quaternion is not None:
        quat = rotation.quaternion
        return [float(quat.x), float(quat.y), float(quat.z), float(quat.w)]

    if isinstance(rotation, Rotation):
        pitch = rotation.pitch
        yaw = rotation.yaw
        roll = rotation.roll
    elif all(hasattr(rotation, axis) for axis in ("x", "y", "z")):
        pitch = float(rotation.x)
        yaw = float(rotation.y)
        roll = float(rotation.z)
    else:
        return [0.0, 0.0, 0.0, 1.0]

    cy = math.cos(yaw * 0.5)
    sy = math.sin(yaw * 0.5)
    cp = math.cos(pitch * 0.5)
    sp = math.sin(pitch * 0.5)
    cr = math.cos(roll * 0.5)
    sr = math.sin(roll * 0.5)
    return [
        sr * cp * cy - cr * sp * sy,
        cr * sp * cy + sr * cp * sy,
        cr * cp * sy - sr * sp * cy,
        cr * cp * cy + sr * sp * sy,
    ]


def _timeline_from_dict(
    raw: dict[str, Any],
    coverage: dict[str, Any],
    diagnostics: dict[str, Any],
) -> InputTimeline:
    return InputTimeline(
        player_id=str(raw["player_id"]),
        samples=tuple(_sample_from_dict(item) for item in raw.get("samples", []) or []),
        events=tuple(_event_from_dict(item) for item in raw.get("events", []) or []),
        segments=tuple(
            _segment_from_dict(item) for item in raw.get("segments", []) or []
        ),
        coverage=coverage,
        diagnostics=diagnostics,
    )


def _sample_from_dict(raw: dict[str, Any]) -> InputSample:
    return InputSample(
        frame_index=int(raw["frame_index"]),
        tick_range=_int_pair(raw["tick_range"]),
        time_range=_float_pair(raw["time_range"]),
        throttle=_channel(raw["throttle"]),
        steer=_channel(raw["steer"]),
        pitch=_channel(raw["pitch"]),
        yaw=_channel(raw["yaw"]),
        roll=_channel(raw["roll"]),
        jump=_channel(raw["jump"]),
        boost=_channel(raw["boost"]),
        handbrake=_channel(raw["handbrake"]),
    )


def _channel(raw: dict[str, Any]) -> ChannelValue:
    return ChannelValue(
        value=raw["value"],
        source=str(raw["source"]),
        confidence=float(raw.get("confidence", 0.0)),
        flags=int(raw.get("flags", 0)),
    )


def _event_from_dict(raw: dict[str, Any]) -> SolvedEvent:
    return SolvedEvent(
        kind=str(raw["kind"]),
        tick=int(raw["tick"]),
        t=float(raw["t"]),
        frame_index=int(raw["frame_index"]),
        confidence=float(raw.get("confidence", 0.0)),
        flags=int(raw.get("flags", 0)),
        detail=dict(raw.get("detail") or {}),
    )


def _segment_from_dict(raw: dict[str, Any]) -> SegmentSummary:
    return SegmentSummary(
        id=int(raw["id"]),
        tick_span=_int_pair(raw["tick_span"]),
        boundary_causes=tuple(str(item) for item in raw.get("boundary_causes", [])),
        confidence=float(raw.get("confidence", 0.0)),
    )


def _int_pair(value: Any) -> tuple[int, int]:
    return (int(value[0]), int(value[1]))


def _float_pair(value: Any) -> tuple[float, float]:
    return (float(value[0]), float(value[1]))


__all__ = [
    "ChannelValue",
    "InputSample",
    "InputTimeline",
    "SegmentSummary",
    "SolvedEvent",
    "build_solver_payload",
    "mirror_solve_output",
    "solve_input_timelines",
]
