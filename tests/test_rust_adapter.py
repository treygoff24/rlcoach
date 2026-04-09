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


def test_players_expose_explicit_false_component_states_when_parser_knows_them():
    frames = _load_frames(limit=300)
    players = []
    for frame in frames:
        players.extend(frame.get("players", []))
    assert players, "no players detected in fixture frames"

    assert any(player.get("is_jumping") is False for player in players)
    assert any(player.get("is_dodging") is False for player in players)
    assert any(player.get("is_double_jumping") is False for player in players)


def test_opening_frames_do_not_mark_every_player_as_actively_jumping():
    frames = _load_frames(limit=5)
    opening_players = [
        player for frame in frames for player in frame.get("players", [])
    ]
    assert opening_players, "expected opening player snapshots from fixture replay"

    active_jump_flags = [
        player.get("is_jumping") is True for player in opening_players if "is_jumping" in player
    ]
    active_dodge_flags = [
        player.get("is_dodging") is True for player in opening_players if "is_dodging" in player
    ]
    active_double_jump_flags = [
        player.get("is_double_jumping") is True
        for player in opening_players
        if "is_double_jumping" in player
    ]

    assert active_jump_flags and not all(active_jump_flags)
    assert active_dodge_flags and not all(active_dodge_flags)
    assert active_double_jump_flags and not all(active_double_jump_flags)


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


def test_real_replay_emits_parser_tickmarks():
    frames = _load_frames()
    tickmarks = [
        tickmark
        for frame in frames
        for tickmark in frame.get("parser_tickmarks", [])
    ]

    assert tickmarks, "expected parser tickmarks from fixture replay"
    assert any(
        isinstance(tickmark.get("kind"), str) and tickmark["kind"]
        for tickmark in tickmarks
    )


def test_real_replay_emits_demo_attacker_authority():
    frames = _load_frames()
    demo_events = [
        demo for frame in frames for demo in frame.get("parser_demo_events", [])
    ]

    assert demo_events, "expected parser demo events from fixture replay"
    assert any(
        isinstance(demo.get("attacker_id"), str) and demo["attacker_id"]
        for demo in demo_events
    ), "expected attacker attribution on at least one parser demo event"


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


def test_parser_touch_events_collected_across_replay():
    """Regression: verify that parser touch events are collected across the replay.

    This test verifies that the Rust parser correctly emits touch events throughout
    the replay, not just at the first touch. It ensures repeated touches from the
    same actor are emitted (not suppressed after the first one).
    """
    adapter = RustAdapter()
    network = adapter.parse_network(REPLAY_PATH)
    if network is None or not network.frames:
        pytest.skip("Rust adapter failed to parse network frames")

    all_touches = []
    frames_with_touches = 0
    for frame in network.frames:
        touches = frame.get("parser_touch_events", [])
        if touches:
            frames_with_touches += 1
            all_touches.extend(touches)

    # The replay should have touches across multiple frames (not just the first one)
    assert frames_with_touches > 1, (
        f"Expected touches across multiple frames, got touches in only "
        f"{frames_with_touches} frame(s). "
        "This may indicate touch suppression after the first touch."
    )

    # We should have multiple touch events total
    assert len(all_touches) >= 2, (
        f"Expected at least 2 touch events across the replay, got {len(all_touches)}. "
        "This may indicate touch events are being suppressed after the first one."
    )

    # Verify touches come from the same player_id appearing in different frames
    player_touches: dict[str, list[float]] = {}
    for touch in all_touches:
        player_id = touch.get("player_id")
        timestamp = touch.get("timestamp")
        if player_id and timestamp is not None:
            player_touches.setdefault(player_id, []).append(float(timestamp))

    # At least one player should have multiple touches across time
    multi_touch_players = {p: ts for p, ts in player_touches.items() if len(ts) >= 2}
    assert multi_touch_players, (
        f"Expected at least one player to have multiple touches across time, "
        f"got player touches: {player_touches}. "
        "This may indicate touch events being suppressed after the first one."
    )
