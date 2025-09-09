"""Tests for the Rust parser adapter shim.

These tests validate that the adapter can be retrieved and that header
parsing returns a valid Header in both environments where the Rust core
is available and where it is not (fallback mode).
"""

import tempfile
from pathlib import Path

import pytest

from rlcoach.parser import Header, get_adapter, list_adapters


@pytest.fixture()
def test_replay_file() -> Path:
    """Create a small binary file that looks like a replay header."""
    from rlcoach.ingest import REPLAY_MAGIC_SEQUENCES

    magic = REPLAY_MAGIC_SEQUENCES[0]
    header_content = bytes([i % 256 for i in range(1000)])
    content = header_content + magic + b"\x00" * 14000  # ~15KB

    with tempfile.NamedTemporaryFile(delete=False, suffix=".replay") as tmp:
        tmp.write(content)
        tmp.flush()
        path = Path(tmp.name)

    yield path
    path.unlink(missing_ok=True)


def test_rust_adapter_registered():
    adapters = list_adapters()
    assert "rust" in adapters


def test_rust_adapter_header_parse(test_replay_file: Path):
    adapter = get_adapter("rust")
    assert adapter.name == "rust"

    header = adapter.parse_header(test_replay_file)
    assert isinstance(header, Header)

    # Ensure key fields are present and typed
    assert header.team_size >= 0
    assert isinstance(header.team0_score, int)
    assert isinstance(header.team1_score, int)
    assert isinstance(header.players, list)

    # Quality warnings should indicate rust path or fallback
    assert any("rust" in w for w in header.quality_warnings)


def test_rust_adapter_network_behavior(test_replay_file: Path):
    adapter = get_adapter("rust")
    frames = adapter.parse_network(test_replay_file)
    # If rust core exists, frames is a NetworkFrames stub; otherwise None
    assert frames is None or hasattr(frames, "frame_count")

