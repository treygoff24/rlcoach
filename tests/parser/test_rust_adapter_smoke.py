import math
from pathlib import Path

import pytest

PARITY_REPLAY_PATH = Path("Replay_files/0925.replay")
LTM_REPLAY_PATH = Path("replays/A181B28546BBD8AC71E63793B65BABAE.replay")


def _has_rust_core():
    try:
        import rlreplay_rust  # type: ignore

        return bool(getattr(rlreplay_rust, "RUST_CORE", False))
    except Exception:
        return False


@pytest.mark.skipif(not _has_rust_core(), reason="Rust core not available")
def test_rust_header_and_frames_smoke():
    from rlcoach.parser import get_adapter

    path = Path("testing_replay.replay")

    adapter = get_adapter("rust")
    assert adapter.supports_network_parsing is True

    header = adapter.parse_header(path)
    assert header is not None
    assert isinstance(header.team_size, int)
    # Rust shim appends this marker
    assert any("parsed_with_rust_core" in w for w in header.quality_warnings)

    frames = adapter.parse_network(path)
    assert frames is not None
    assert frames.frame_count >= 1
    assert isinstance(frames.frames, list)
    first = frames.frames[0]
    # Structure sanity checks
    assert isinstance(first, dict)
    assert "timestamp" in first
    assert "ball" in first and isinstance(first["ball"], dict)
    assert "position" in first["ball"] and "velocity" in first["ball"]
    assert "angular_velocity" in first["ball"]
    assert "players" in first and isinstance(first["players"], list)


@pytest.mark.skipif(not _has_rust_core(), reason="Rust core not available")
def test_rust_network_parse_returns_diagnostics_shape():
    import rlreplay_rust  # type: ignore

    result = rlreplay_rust.parse_network_with_diagnostics("testing_replay.replay")

    assert isinstance(result, dict)
    assert "frames" in result
    assert "diagnostics" in result
    diagnostics = result["diagnostics"]
    assert isinstance(diagnostics, dict)
    assert "status" in diagnostics


@pytest.mark.skipif(not _has_rust_core(), reason="Rust core not available")
@pytest.mark.skipif(not LTM_REPLAY_PATH.exists(), reason="LTM replay fixture missing")
def test_ltm_replay_reports_parse_reason_not_silent_none():
    from rlcoach.parser import get_adapter

    adapter = get_adapter("rust")
    nf = adapter.parse_network(LTM_REPLAY_PATH)

    assert nf is not None
    assert hasattr(nf, "diagnostics")
    diagnostics = nf.diagnostics
    assert diagnostics is not None
    assert diagnostics.status == "degraded"
    assert diagnostics.error_code == "boxcars_unknown_attribute_network_error"


@pytest.mark.skipif(not _has_rust_core(), reason="Rust core not available")
@pytest.mark.skipif(
    not PARITY_REPLAY_PATH.exists(), reason="0925 parity replay fixture missing"
)
def test_rust_network_preserves_header_player_frames_after_respawn():
    from rlcoach.parser import get_adapter

    adapter = get_adapter("rust")
    network = adapter.parse_network(PARITY_REPLAY_PATH)

    assert network is not None
    assert network.frames

    player_counts: dict[str, int] = {}
    player_last_timestamp: dict[str, float] = {}
    for frame in network.frames:
        for player in frame.get("players", []):
            player_id = player.get("player_id")
            if not isinstance(player_id, str):
                continue
            player_counts[player_id] = player_counts.get(player_id, 0) + 1
            player_last_timestamp[player_id] = float(frame["timestamp"])

    expected_player_ids = {f"player_{idx}" for idx in range(4)}
    assert expected_player_ids <= player_counts.keys()

    total_frames = len(network.frames)
    for player_id in expected_player_ids:
        assert player_counts[player_id] / total_frames >= 0.95
        assert player_last_timestamp[player_id] == pytest.approx(
            network.frames[-1]["timestamp"]
        )


@pytest.mark.skipif(not _has_rust_core(), reason="Rust core not available")
@pytest.mark.skipif(
    not PARITY_REPLAY_PATH.exists(), reason="0925 parity replay fixture missing"
)
def test_0925_replay_exposes_car_angular_velocity():
    from rlcoach.parser import get_adapter

    adapter = get_adapter("rust")
    network = adapter.parse_network(PARITY_REPLAY_PATH)

    assert network is not None
    assert network.frames

    magnitudes = []
    for frame in network.frames:
        for player in frame.get("players", []):
            angular_velocity = player.get("angular_velocity")
            if not isinstance(angular_velocity, dict):
                continue
            magnitude = math.sqrt(
                sum(float(angular_velocity.get(axis, 0.0)) ** 2 for axis in "xyz")
            )
            magnitudes.append(magnitude)

    assert any(magnitude > 0.01 for magnitude in magnitudes)
    assert max(magnitudes) <= 5.6


@pytest.mark.skipif(not _has_rust_core(), reason="Rust core not available")
@pytest.mark.skipif(
    not PARITY_REPLAY_PATH.exists(), reason="0925 parity replay fixture missing"
)
def test_0925_replay_exposes_rigid_body_sleeping_flags():
    from rlcoach.parser import get_adapter

    adapter = get_adapter("rust")
    network = adapter.parse_network(PARITY_REPLAY_PATH)

    assert network is not None
    assert network.frames

    ball_sleeping = [frame.get("ball", {}).get("sleeping") for frame in network.frames]
    car_sleeping = [
        player.get("sleeping")
        for frame in network.frames
        for player in frame.get("players", [])
    ]

    assert any(value is True for value in ball_sleeping)
    assert any(value is False for value in ball_sleeping)
    assert any(value is True for value in car_sleeping)
    assert any(value is False for value in car_sleeping)


@pytest.mark.skipif(not _has_rust_core(), reason="Rust core not available")
@pytest.mark.skipif(
    not PARITY_REPLAY_PATH.exists(), reason="0925 parity replay fixture missing"
)
def test_0925_replay_exposes_driving_inputs():
    from rlcoach.parser import get_adapter

    adapter = get_adapter("rust")
    network = adapter.parse_network(PARITY_REPLAY_PATH)

    assert network is not None
    assert network.frames

    players = [
        player for frame in network.frames for player in frame.get("players", [])
    ]
    assert any("throttle" in player for player in players)
    assert any("steer" in player for player in players)
    assert any("handbrake" in player for player in players)
    assert any(player.get("throttle_raw") not in (None, 128) for player in players)
    assert any(player.get("steer_raw") not in (None, 128) for player in players)
    assert any(player.get("handbrake") is True for player in players)

    for player in players:
        if "throttle_raw" in player:
            assert 0 <= player["throttle_raw"] <= 255
            assert -1.0 <= player["throttle"] <= 1.0
        if "steer_raw" in player:
            assert 0 <= player["steer_raw"] <= 255
            assert -1.0 <= player["steer"] <= 1.0
        if "handbrake" in player:
            assert isinstance(player["handbrake"], bool)


@pytest.mark.skipif(not _has_rust_core(), reason="Rust core not available")
@pytest.mark.skipif(
    not PARITY_REPLAY_PATH.exists(), reason="0925 parity replay fixture missing"
)
def test_0925_replay_exposes_component_state_and_events():
    from rlcoach.parser import get_adapter

    adapter = get_adapter("rust")
    network = adapter.parse_network(PARITY_REPLAY_PATH)

    assert network is not None
    assert network.frames

    players = [
        player for frame in network.frames for player in frame.get("players", [])
    ]
    assert any("jump_active_raw" in player for player in players)
    assert any("dodge_active_raw" in player for player in players)
    assert any("double_jump_active_raw" in player for player in players)
    assert any("boost_active" in player for player in players)
    assert any("boost_active_raw" in player for player in players)
    assert any("boost_amount_raw" in player for player in players)
    assert any("boost_grant_count" in player for player in players)

    component_events = [
        event for frame in network.frames for event in frame.get("component_events", [])
    ]
    event_kinds = {
        (event.get("component"), event.get("kind")) for event in component_events
    }
    assert ("jump", "active") in event_kinds
    assert ("dodge", "active") in event_kinds
    assert ("boost", "active") in event_kinds
    assert ("dodge", "dodge_torque") in event_kinds
    assert ("double_jump", "double_jump_impulse") in event_kinds
    assert ("air_activate", "air_activate_count") in event_kinds
    assert any(isinstance(event.get("vector"), dict) for event in component_events)
    assert any(isinstance(event.get("raw_value"), int) for event in component_events)

    stat_events = [
        event
        for frame in network.frames
        for event in frame.get("parser_stat_events", [])
    ]
    assert any(
        event.get("object_name") == "StatEvents.Events.Save" for event in stat_events
    )
    assert any(
        event.get("object_name") == "StatEvents.Events.EpicSave"
        for event in stat_events
    )
