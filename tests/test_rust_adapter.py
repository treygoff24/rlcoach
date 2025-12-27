"""Integration tests for the Rust replay adapter telemetry."""

from __future__ import annotations

import math
from pathlib import Path

from rlcoach.parser.rust_adapter import RustAdapter

REPLAY_PATH = Path("Replay_files/4985385d-2a6a-4bea-a312-8e539c7fd098.replay")


def _load_frames(limit: int = 1200):
    adapter = RustAdapter()
    network = adapter.parse_network(REPLAY_PATH)
    assert network is not None, "Rust adapter failed to parse network frames"
    assert network.frames, "No frames returned from Rust adapter"
    return network.frames[:limit]


def test_players_are_unique_per_frame():
    frames = _load_frames()
    for frame in frames[:10]:  # kickoff window
        players = frame.get("players", [])
        ids = [p.get("player_id") for p in players if isinstance(p, dict)]
        assert ids, "no players detected in frame"
        assert len(ids) == len(set(ids)), "duplicate player entries detected"


def test_velocity_and_boost_telemetry_present():
    frames = _load_frames()
    moving_detected = False
    boost_change_detected = False

    previous_boost: dict[str, int] = {}
    for frame in frames:
        players = frame.get("players", [])
        for player in players:
            if not isinstance(player, dict):
                continue
            pid = player.get("player_id")
            vel = player.get("velocity", {})
            if isinstance(vel, dict):
                vx = float(vel.get("x", 0.0))
                vy = float(vel.get("y", 0.0))
                vz = float(vel.get("z", 0.0))
                speed = math.sqrt(vx * vx + vy * vy + vz * vz)
                if speed > 50.0:  # players exceed 50 uu/s almost immediately
                    moving_detected = True
            boost_amount = player.get("boost_amount")
            if isinstance(pid, str) and isinstance(boost_amount, int):
                prev = previous_boost.get(pid)
                if prev is not None and boost_amount != prev:
                    boost_change_detected = True
                previous_boost[pid] = boost_amount
        if moving_detected and boost_change_detected:
            break

    assert moving_detected, "no player velocity updates detected"
    assert boost_change_detected, "no boost telemetry change detected"
