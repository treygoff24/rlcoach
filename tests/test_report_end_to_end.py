"""End-to-end tests for report generation and CLI."""

from pathlib import Path

import pytest

from rlcoach.cli import main as cli_main
from rlcoach.parser.types import Header, NetworkDiagnostics, NetworkFrames, PlayerInfo
from rlcoach.report import generate_report
from rlcoach.schema import validate_report, validate_report_file

REPO_ROOT = Path(__file__).parent.parent
SAMPLE_REPLAY = REPO_ROOT / "Replay_files" / "0925.replay"


def _make_dummy_replay(path: Path) -> None:
    """Create a small binary file that passes ingest format checks."""
    magic = b"TAGame.Replay_Soccar_TA\x00"
    # Ensure > 10KB as per MIN_REPLAY_SIZE
    payload = magic + b"\x00" * (11_000 - len(magic))
    path.write_bytes(payload)


class _FakeNetworkAdapter:
    def __init__(self, network_frames):
        self._network_frames = network_frames

    @property
    def name(self) -> str:
        return "rust"

    @property
    def supports_network_parsing(self) -> bool:
        return True

    def parse_header(self, path: Path) -> Header:
        return Header(
            playlist_id="13",
            map_name="DFH_Stadium",
            team_size=1,
            team0_score=1,
            team1_score=0,
            match_guid="fake-guid",
            players=[
                PlayerInfo(name="Blue", team=0),
                PlayerInfo(name="Orange", team=1),
            ],
        )

    def parse_network(self, path: Path):
        return self._network_frames


def test_cli_analyze_header_only_success(tmp_path: Path, monkeypatch):
    # Create dummy replay file
    replay = tmp_path / "sample.replay"
    _make_dummy_replay(replay)

    # Output directory
    out_dir = tmp_path / "out"

    # Run CLI: rlcoach analyze <file> --header-only --out <dir>
    import sys

    orig_argv = sys.argv
    try:
        sys.argv = [
            "rlcoach",
            "analyze",
            str(replay),
            "--header-only",
            "--out",
            str(out_dir),
        ]
        exit_code = cli_main()
        assert exit_code in (0, 1)  # Allow non-zero if error, we validate below
    finally:
        sys.argv = orig_argv

    # Locate output JSON
    out_file = out_dir / "sample.json"
    assert out_file.exists(), "Report file should be written"

    # Validate JSON file against schema (should pass)
    validate_report_file(str(out_file))


def test_generate_report_error_contract(tmp_path: Path):
    # Non-existent replay path triggers error
    bad_path = tmp_path / "missing.replay"
    report = generate_report(bad_path, header_only=True)
    assert report.get("error") == "unreadable_replay_file"
    assert isinstance(report.get("details"), str)
    # Error report must validate as well
    validate_report(report)


def test_report_includes_network_diagnostics_when_degraded(
    tmp_path: Path, monkeypatch
):
    replay = tmp_path / "sample.replay"
    _make_dummy_replay(replay)
    monkeypatch.setattr(
        "rlcoach.report.ingest_replay",
        lambda _path: {
            "sha256": "abc123",
            "crc_check": {"message": "not yet implemented", "passed": False},
        },
    )
    degraded = NetworkFrames(
        frame_count=0,
        sample_rate=30.0,
        frames=[],
        diagnostics=NetworkDiagnostics(
            status="degraded",
            error_code="boxcars_network_error",
            error_detail="unknown attributes for object",
            frames_emitted=0,
        ),
    )
    monkeypatch.setattr(
        "rlcoach.report.get_adapter", lambda _name: _FakeNetworkAdapter(degraded)
    )

    report = generate_report(replay, header_only=False, adapter_name="rust")
    diagnostics = report["quality"]["parser"]["network_diagnostics"]

    assert diagnostics["status"] == "degraded"
    assert diagnostics["error_code"] == "boxcars_network_error"
    assert diagnostics["frames_emitted"] == 0
    assert set(diagnostics.keys()) == {
        "status",
        "error_code",
        "error_detail",
        "frames_emitted",
    }


def test_report_includes_network_diagnostics_when_unavailable(
    tmp_path: Path, monkeypatch
):
    replay = tmp_path / "sample.replay"
    _make_dummy_replay(replay)
    monkeypatch.setattr(
        "rlcoach.report.ingest_replay",
        lambda _path: {
            "sha256": "abc123",
            "crc_check": {"message": "not yet implemented", "passed": False},
        },
    )
    monkeypatch.setattr(
        "rlcoach.report.get_adapter", lambda _name: _FakeNetworkAdapter(None)
    )

    report = generate_report(replay, header_only=False, adapter_name="rust")
    diagnostics = report["quality"]["parser"]["network_diagnostics"]

    assert diagnostics["status"] == "unavailable"
    assert diagnostics["error_code"] == "network_data_unavailable"
    assert diagnostics["frames_emitted"] == 0
    assert set(diagnostics.keys()) == {
        "status",
        "error_code",
        "error_detail",
        "frames_emitted",
    }


@pytest.mark.skipif(not SAMPLE_REPLAY.exists(), reason="Sample replay not found")
def test_generate_report_with_identity_config():
    """Test that is_me is set when identity_config is provided."""
    from rlcoach.config import IdentityConfig

    # Create identity config that won't match any player
    identity_config = IdentityConfig(
        platform_ids=["steam:12345"],
        display_names=["TestPlayer"],
    )

    report = generate_report(
        SAMPLE_REPLAY,
        header_only=True,
        identity_config=identity_config,
    )

    # When identity_config is provided, is_me should be present on all players
    players = report.get("players", [])
    assert len(players) > 0, "Report should have at least one player"
    for player in players:
        assert (
            "is_me" in player
        ), "is_me field should be present when identity_config provided"
        assert isinstance(player["is_me"], bool), "is_me should be a boolean"
        # None of these players should match our fake identity
        assert player["is_me"] is False, "No players should match fake identity"

    # Validate report still passes schema
    validate_report(report)


@pytest.mark.skipif(not SAMPLE_REPLAY.exists(), reason="Sample replay not found")
def test_generate_report_without_identity_config():
    """Test that is_me is NOT set when no identity_config provided."""
    report = generate_report(SAMPLE_REPLAY, header_only=True)

    # Without identity_config, is_me should NOT be present
    players = report.get("players", [])
    assert len(players) > 0, "Report should have at least one player"
    for player in players:
        assert (
            "is_me" not in player
        ), "is_me field should NOT be present without identity_config"

    # Validate report still passes schema
    validate_report(report)
