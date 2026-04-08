"""Integration tests for the Rust replay adapter telemetry."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from rlcoach.parser.rust_adapter import RustAdapter

REPLAY_PATH = Path("Replay_files/4985385d-2a6a-4bea-a312-8e539c7fd098.replay")


def _load_frames(limit: int = 1200):
    adapter = RustAdapter()
    network = adapter.parse_network(REPLAY_PATH)
    if network is None:
        pytest.skip("Rust adapter failed to parse network frames for fixture replay")
    if not network.frames:
        pytest.skip("Rust adapter returned no frames for fixture replay")
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


def test_frame_contains_parser_frame_meta_when_available():
    frames = _load_frames(limit=5)
    meta = frames[0].get("_parser_meta")
    assert isinstance(meta, dict)
    assert "classification_source" in meta


def test_parse_network_returns_diagnostics_on_degradation(monkeypatch):
    class FakeRustDegraded:
        @staticmethod
        def parse_network_with_diagnostics(_path: str):
            return {
                "frames": [],
                "diagnostics": {
                    "status": "degraded",
                    "error_code": "boxcars_network_error",
                    "error_detail": "unknown attributes for object",
                    "frames_emitted": 0,
                },
            }

    monkeypatch.setattr("rlcoach.parser.rust_adapter._rust", FakeRustDegraded())
    monkeypatch.setattr("rlcoach.parser.rust_adapter._RUST_AVAILABLE", True)

    adapter = RustAdapter()
    result = adapter.parse_network(Path("testing_replay.replay"))

    assert result is not None
    assert hasattr(result, "diagnostics")
    diagnostics = result.diagnostics
    assert diagnostics is not None
    assert "network_error" in (diagnostics.error_code or "")


def test_players_expose_optional_component_state_flags():
    frames = _load_frames(limit=10)
    players = []
    for frame in frames:
        players.extend(frame.get("players", []))
    assert players, "no players detected in fixture frames"

    assert any("is_jumping" not in player for player in players)
    assert any("is_dodging" not in player for player in players)
    assert any("is_double_jumping" not in player for player in players)


def test_rust_header_exposes_match_guid_overtime_and_mutators():
    adapter = RustAdapter()
    header = adapter.parse_header(REPLAY_PATH)

    assert hasattr(header, "match_guid")
    assert hasattr(header, "overtime")
    assert hasattr(header, "mutators")
    assert isinstance(header.mutators, dict)


def test_component_state_flags_are_boolean_only_when_present():
    frames = _load_frames(limit=15)
    players = []
    for frame in frames:
        players.extend(frame.get("players", []))
    assert players, "expected player snapshots in replay fixture"

    for player in players[:20]:
        if "is_jumping" in player:
            assert isinstance(player["is_jumping"], bool)
        if "is_dodging" in player:
            assert isinstance(player["is_dodging"], bool)
        if "is_double_jumping" in player:
            assert isinstance(player["is_double_jumping"], bool)


def test_frames_expose_parser_event_carrier_lists():
    frames = _load_frames(limit=1)
    frame = frames[0]
    assert "parser_touch_events" in frame
    assert "parser_demo_events" in frame
    assert "parser_tickmarks" in frame
    assert "parser_kickoff_markers" in frame
    assert isinstance(frame["parser_touch_events"], list)
    assert isinstance(frame["parser_demo_events"], list)
    assert isinstance(frame["parser_tickmarks"], list)
    assert isinstance(frame["parser_kickoff_markers"], list)


def test_parse_header_maps_extended_metadata(monkeypatch):
    class FakeRustHeader:
        @staticmethod
        def parse_header(_path: str):
            return {
                "playlist_id": "ranked_doubles",
                "map_name": "DFHStadium",
                "team_size": 2,
                "team0_score": 4,
                "team1_score": 2,
                "match_length": 305.5,
                "engine_build": "build-1234",
                "match_guid": "GUID-abc",
                "overtime": True,
                "mutators": {"BallMaxSpeed": "Fast"},
                "players": [],
                "goals": [],
                "highlights": [],
                "quality_warnings": [],
            }

    monkeypatch.setattr("rlcoach.parser.rust_adapter._rust", FakeRustHeader())
    monkeypatch.setattr("rlcoach.parser.rust_adapter._RUST_AVAILABLE", True)

    header = RustAdapter().parse_header(Path("testing_replay.replay"))
    assert header.engine_build == "build-1234"
    assert header.match_guid == "GUID-abc"
    assert header.overtime is True
    assert header.mutators == {"BallMaxSpeed": "Fast"}


def test_iter_frames_has_players():
    """Regression: iter_frames must return non-empty players on real replays."""
    adapter = RustAdapter()
    network = adapter.parse_network(REPLAY_PATH)
    assert network is not None, "Rust adapter failed to parse network frames"
    frames = network.frames
    total = len(frames)
    frames_with_players = sum(1 for f in frames if len(f.get("players", [])) > 0)
    assert frames_with_players > total * 0.5, (
        f"Only {frames_with_players}/{total} frames have players — "
        "actor-to-player mapping is broken"
    )
