#!/usr/bin/env python
"""Dump one replay as rlinput ReplaySeries-compatible JSON."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rlcoach.normalize import build_timeline  # noqa: E402
from rlcoach.parser.rust_adapter import RustAdapter  # noqa: E402
from rlcoach.parser.types import Rotation, Vec3  # noqa: E402


def vec3(value: Vec3 | None) -> list[float]:
    if value is None:
        return [0.0, 0.0, 0.0]
    return [float(value.x), float(value.y), float(value.z)]


def quat_xyzw(rotation: Any) -> list[float]:
    if isinstance(rotation, Rotation) and rotation.quaternion is not None:
        q = rotation.quaternion
        return [float(q.x), float(q.y), float(q.z), float(q.w)]
    if isinstance(rotation, Rotation):
        cy = math.cos(rotation.yaw * 0.5)
        sy = math.sin(rotation.yaw * 0.5)
        cp = math.cos(rotation.pitch * 0.5)
        sp = math.sin(rotation.pitch * 0.5)
        cr = math.cos(rotation.roll * 0.5)
        sr = math.sin(rotation.roll * 0.5)
        return [
            sr * cp * cy - cr * sp * sy,
            cr * sp * cy + sr * cp * sy,
            cr * cp * sy - sr * sp * cy,
            cr * cp * cy + sr * sp * sy,
        ]
    return [0.0, 0.0, 0.0, 1.0]


def raw_byte(value: int | None, default: int) -> int:
    if value is None:
        return default
    return max(0, min(255, int(value)))


def component_kind(component: str) -> str | None:
    return {
        "jump": "Jump",
        "dodge": "DodgeTorque",
        "double_jump": "DoubleJumpImpulse",
        "boost": "Boost",
    }.get(component)


def export_series(path: Path) -> dict[str, Any]:
    adapter = RustAdapter()
    header = adapter.parse_header(path)
    network = adapter.parse_network(path)
    if network is None or not network.frames:
        raise SystemExit(
            "network frames unavailable; build/install rlreplay_rust first"
        )

    frames = build_timeline(header, network.frames)
    if not frames:
        raise SystemExit("normalized timeline was empty")

    player_sets = [
        {player.player_id for player in frame.players}
        for frame in frames
        if frame.players
    ]
    player_ids = sorted(set.intersection(*player_sets)) if player_sets else []
    if not player_ids:
        raise SystemExit("no complete player streams found")

    deltas = [0.0]
    deltas.extend(
        max(0.0, frames[index].timestamp - frames[index - 1].timestamp)
        for index in range(1, len(frames))
    )

    players = []
    component_events = {player_id: [] for player_id in player_ids}
    touch_events = []
    demo_events = []
    kickoff_markers = []

    for frame_index, frame in enumerate(frames):
        for event in frame.component_events:
            if event.player_id in component_events:
                kind = component_kind(event.component)
                if kind is not None:
                    component_events[event.player_id].append(
                        {
                            "t": float(event.timestamp),
                            "frame_index": frame_index,
                            "component": kind,
                            "vector": vec3(event.vector) if event.vector else None,
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

    for player_id in player_ids:
        stream = [frame.get_player_by_id(player_id) for frame in frames]
        if any(player is None for player in stream):
            continue
        player_frames = [player for player in stream if player is not None]
        players.append(
            {
                "player_id": player_id,
                "frames": {
                    "pos": [vec3(player.position) for player in player_frames],
                    "vel": [vec3(player.velocity) for player in player_frames],
                    "quat_xyzw": [
                        quat_xyzw(player.rotation) for player in player_frames
                    ],
                    "ang_vel": [
                        vec3(player.angular_velocity) for player in player_frames
                    ],
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
                        raw_byte(player.throttle_raw, 128) for player in player_frames
                    ],
                    "steer_raw": [
                        raw_byte(player.steer_raw, 128) for player in player_frames
                    ],
                    "handbrake": [bool(player.handbrake) for player in player_frames],
                    "boost_amount_raw": [
                        raw_byte(player.boost_amount_raw, int(player.boost_amount))
                        for player in player_frames
                    ],
                    "boost_active_raw": [
                        bool(player.boost_active) for player in player_frames
                    ],
                },
                "component": {
                    "jump_raw": [
                        raw_byte(player.jump_active_raw, 0) for player in player_frames
                    ],
                    "dodge_raw": [
                        raw_byte(player.dodge_active_raw, 0) for player in player_frames
                    ],
                    "double_jump_raw": [
                        raw_byte(player.double_jump_active_raw, 0)
                        for player in player_frames
                    ],
                    "boost_raw": [
                        raw_byte(player.boost_active_raw, 0) for player in player_frames
                    ],
                    "events": component_events[player_id],
                },
            }
        )

    return {
        "tick_rate": 120.0,
        "build_bucket": header.engine_build or "unknown",
        "players": players,
        "ball": {
            "pos": [vec3(frame.ball.position) for frame in frames],
            "vel": [vec3(frame.ball.velocity) for frame in frames],
        },
        "deltas": deltas,
        "demo_events": demo_events,
        "touch_events": touch_events,
        "kickoff_markers": kickoff_markers,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("replay", type=Path)
    args = parser.parse_args()
    json.dump(export_series(args.replay), sys.stdout, separators=(",", ":"))
    print()


if __name__ == "__main__":
    main()
