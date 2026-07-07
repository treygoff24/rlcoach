#!/usr/bin/env python
"""Export per-player component streams and minimal kinematics as JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from rlcoach.parser.rust_adapter import RustAdapter

RAW_FIELDS = {
    "jump_raw": "jump_active_raw",
    "dodge_raw": "dodge_active_raw",
    "double_jump_raw": "double_jump_active_raw",
    "boost_raw": "boost_active_raw",
}

EVENT_KIND = {
    ("dodge", "dodge_torque"): "DodgeTorque",
    ("double_jump", "double_jump_impulse"): "DoubleJumpImpulse",
}


def _vec3(raw: Any) -> list[float]:
    if not isinstance(raw, dict):
        return [0.0, 0.0, 0.0]
    return [float(raw.get(axis, 0.0) or 0.0) for axis in ("x", "y", "z")]


def _quat(raw: Any) -> list[float]:
    if not isinstance(raw, dict):
        return [0.0, 0.0, 0.0, 1.0]
    quat = raw.get("quaternion")
    if not isinstance(quat, dict):
        return [0.0, 0.0, 0.0, 1.0]
    return [
        float(quat.get("x", 0.0) or 0.0),
        float(quat.get("y", 0.0) or 0.0),
        float(quat.get("z", 0.0) or 0.0),
        float(quat.get("w", 1.0) or 1.0),
    ]


def _u8(value: Any, default: int) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return max(0, min(255, int(value)))
    return default


def export_component_stream(replay: Path) -> dict[str, Any]:
    adapter = RustAdapter()
    header = adapter.parse_header(replay)
    network = adapter.parse_network(replay)
    if (
        network is None
        or network.diagnostics is None
        or network.diagnostics.status != "ok"
    ):
        detail = None if network is None else network.diagnostics
        raise SystemExit(f"network parse failed or unavailable: {detail}")

    frames = list(network.frames)
    player_ids = sorted(
        {
            str(player["player_id"])
            for frame in frames
            for player in frame.get("players", []) or []
            if isinstance(player, dict) and player.get("player_id") is not None
        }
    )

    players = {
        player_id: {
            "player_id": player_id,
            "component": {
                "jump_raw": [],
                "dodge_raw": [],
                "double_jump_raw": [],
                "boost_raw": [],
                "events": [],
            },
            "kinematics": [],
        }
        for player_id in player_ids
    }
    last_raw = {player_id: dict.fromkeys(RAW_FIELDS, 0) for player_id in player_ids}

    for frame_index, frame in enumerate(frames):
        timestamp = float(frame.get("timestamp", frame.get("time", 0.0)) or 0.0)
        delta = frame.get("delta")
        by_id = {
            str(player.get("player_id")): player
            for player in frame.get("players", []) or []
            if isinstance(player, dict) and player.get("player_id") is not None
        }

        for player_id, out in players.items():
            player = by_id.get(player_id, {})
            component = out["component"]
            for out_field, raw_field in RAW_FIELDS.items():
                value = _u8(player.get(raw_field), last_raw[player_id][out_field])
                last_raw[player_id][out_field] = value
                component[out_field].append(value)

            out["kinematics"].append(
                {
                    "frame_index": frame_index,
                    "t": timestamp,
                    "delta": delta,
                    "ang_vel": _vec3(player.get("angular_velocity")),
                    "quat_xyzw": _quat(player.get("rotation")),
                    "on_ground": bool(player.get("is_on_ground", True)),
                    "sleeping": bool(player.get("sleeping", False)),
                    "demolished": bool(player.get("is_demolished", False)),
                }
            )

        for event in frame.get("component_events", []) or []:
            if not isinstance(event, dict):
                continue
            player_id = event.get("player_id")
            kind = EVENT_KIND.get((event.get("component"), event.get("kind")))
            if player_id not in players or kind is None:
                continue
            vector = event.get("vector")
            players[player_id]["component"]["events"].append(
                {
                    "t": float(event.get("timestamp", timestamp) or 0.0),
                    "frame_index": int(event.get("frame_index", frame_index) or 0),
                    "component": kind,
                    "vector": _vec3(vector) if isinstance(vector, dict) else None,
                    "raw_value": (
                        int(event["raw_value"])
                        if isinstance(event.get("raw_value"), (int, float))
                        else None
                    ),
                }
            )

    return {
        "replay": str(replay),
        "frame_count": len(frames),
        "sample_rate": network.sample_rate,
        "engine_build": header.engine_build,
        "match_guid": header.match_guid,
        "players": list(players.values()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("replay", type=Path)
    parser.add_argument("-o", "--output", type=Path)
    args = parser.parse_args()

    payload = export_component_stream(args.replay)
    text = json.dumps(payload, separators=(",", ":"))
    if args.output:
        args.output.write_text(text + "\n")
    else:
        print(text)


if __name__ == "__main__":
    main()
