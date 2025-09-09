from pathlib import Path

import pytest


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

