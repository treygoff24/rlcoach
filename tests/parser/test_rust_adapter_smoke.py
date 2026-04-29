from pathlib import Path

import pytest

PARITY_REPLAY_PATH = Path("Replay_files/0925.replay")


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
def test_ltm_replay_reports_parse_reason_not_silent_none():
    from rlcoach.parser import get_adapter

    path = Path("replays/A181B28546BBD8AC71E63793B65BABAE.replay")
    adapter = get_adapter("rust")
    nf = adapter.parse_network(path)

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
