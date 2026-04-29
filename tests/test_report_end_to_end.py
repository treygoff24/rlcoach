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


class _FakeNetworkAdapterWithoutHeaderPlayers(_FakeNetworkAdapter):
    def parse_header(self, path: Path) -> Header:
        return Header(
            playlist_id="13",
            map_name="DFH_Stadium",
            team_size=1,
            team0_score=1,
            team1_score=0,
            match_guid="fake-guid",
            players=[],
        )


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


def test_report_includes_network_diagnostics_when_degraded(tmp_path: Path, monkeypatch):
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
        "attempted_backends",
    }
    assert diagnostics["attempted_backends"] == []
    validate_report(report)


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
        "attempted_backends",
    }
    assert diagnostics["attempted_backends"] == []
    validate_report(report)


def test_report_includes_parser_scorecard(tmp_path: Path, monkeypatch):
    replay = tmp_path / "sample.replay"
    _make_dummy_replay(replay)
    monkeypatch.setattr(
        "rlcoach.report.ingest_replay",
        lambda _path: {
            "sha256": "abc123",
            "crc_check": {"message": "not yet implemented", "passed": False},
        },
    )

    frame_payload = {
        "timestamp": 0.0,
        "ball": {
            "position": {"x": 0.0, "y": 0.0, "z": 93.15},
            "velocity": {"x": 0.0, "y": 0.0, "z": 0.0},
            "angular_velocity": {"x": 0.0, "y": 0.0, "z": 0.0},
        },
        "players": [
            {
                "player_id": "player-blue",
                "team": 0,
                "position": {"x": 0.0, "y": -1000.0, "z": 17.0},
                "velocity": {"x": 0.0, "y": 0.0, "z": 0.0},
                "rotation": {"pitch": 0.0, "yaw": 0.0, "roll": 0.0},
                "boost_amount": 33,
                "is_on_ground": True,
            },
            {
                "player_id": "player-orange",
                "team": 1,
                "position": {"x": 0.0, "y": 1000.0, "z": 17.0},
                "velocity": {"x": 0.0, "y": 0.0, "z": 0.0},
                "rotation": {"pitch": 0.0, "yaw": 3.14, "roll": 0.0},
                "boost_amount": 33,
                "is_on_ground": True,
            },
        ],
        "boost_pad_events": [],
    }
    network = NetworkFrames(
        frame_count=1,
        sample_rate=30.0,
        frames=[frame_payload],
        diagnostics=NetworkDiagnostics(
            status="ok",
            error_code=None,
            error_detail=None,
            frames_emitted=1,
            attempted_backends=["boxcars"],
        ),
    )
    monkeypatch.setattr(
        "rlcoach.report.get_adapter", lambda _name: _FakeNetworkAdapter(network)
    )

    report = generate_report(replay, header_only=False, adapter_name="rust")
    scorecard = report["quality"]["parser"]["scorecard"]
    diagnostics = report["quality"]["parser"]["network_diagnostics"]

    assert scorecard["usable_network_parse"] is True
    assert scorecard["non_empty_player_frame_coverage"] == 1.0
    assert scorecard["player_identity_coverage"] == 1.0
    assert scorecard["network_frame_count"] == 1
    assert scorecard["non_empty_player_frames"] == 1
    assert scorecard["players_with_identity"] == 2
    assert scorecard["expected_players"] == 2
    assert diagnostics["attempted_backends"] == ["boxcars"]
    validate_report(report)


def test_report_surfaces_parser_event_provenance_without_duplicates(
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
    frames = [
        {
            "timestamp": 0.0,
            "ball": {
                "position": {"x": 0.0, "y": 0.0, "z": 93.15},
                "velocity": {"x": 0.0, "y": 0.0, "z": 0.0},
                "angular_velocity": {"x": 0.0, "y": 0.0, "z": 0.0},
            },
            "players": [
                {
                    "player_id": "player_0",
                    "team": 0,
                    "position": {"x": 0.0, "y": -1000.0, "z": 17.0},
                    "velocity": {"x": 0.0, "y": 0.0, "z": 0.0},
                    "rotation": {"pitch": 0.0, "yaw": 0.0, "roll": 0.0},
                    "boost_amount": 33,
                    "is_on_ground": True,
                },
                {
                    "player_id": "player_1",
                    "team": 1,
                    "position": {"x": 0.0, "y": 1000.0, "z": 17.0},
                    "velocity": {"x": 0.0, "y": 0.0, "z": 0.0},
                    "rotation": {"pitch": 0.0, "yaw": 3.14, "roll": 0.0},
                    "boost_amount": 33,
                    "is_on_ground": True,
                },
            ],
            "parser_kickoff_markers": [
                {"timestamp": 0.0, "phase": "INITIAL", "source": "parser"}
            ],
        },
        {
            "timestamp": 0.5,
            "ball": {
                "position": {"x": 0.0, "y": 0.0, "z": 93.15},
                "velocity": {"x": 0.0, "y": 1000.0, "z": 0.0},
                "angular_velocity": {"x": 0.0, "y": 0.0, "z": 0.0},
            },
            "players": [
                {
                    "player_id": "player_0",
                    "team": 0,
                    "position": {"x": 0.0, "y": -50.0, "z": 17.0},
                    "velocity": {"x": 0.0, "y": 0.0, "z": 0.0},
                    "rotation": {"pitch": 0.0, "yaw": 0.0, "roll": 0.0},
                    "boost_amount": 33,
                    "is_on_ground": True,
                },
                {
                    "player_id": "player_1",
                    "team": 1,
                    "position": {"x": 60.0, "y": 0.0, "z": 17.0},
                    "velocity": {"x": 0.0, "y": 0.0, "z": 0.0},
                    "rotation": {"pitch": 0.0, "yaw": 3.14, "roll": 0.0},
                    "boost_amount": 33,
                    "is_on_ground": True,
                },
            ],
            "parser_touch_events": [
                {
                    "timestamp": 0.5,
                    "player_id": "player_0",
                    "team": 0,
                    "frame_index": 1,
                    "source": "parser",
                }
            ],
            "parser_demo_events": [
                {
                    "timestamp": 0.5,
                    "victim_id": "player_1",
                    "attacker_id": "player_0",
                    "victim_team": 1,
                    "attacker_team": 0,
                    "frame_index": 1,
                    "source": "parser",
                }
            ],
        },
    ]
    network = NetworkFrames(
        frame_count=len(frames),
        sample_rate=30.0,
        frames=frames,
        diagnostics=NetworkDiagnostics(
            status="ok",
            frames_emitted=len(frames),
            attempted_backends=["boxcars"],
        ),
    )
    monkeypatch.setattr(
        "rlcoach.report.get_adapter", lambda _name: _FakeNetworkAdapter(network)
    )

    report = generate_report(replay, header_only=False, adapter_name="rust")
    repeated = generate_report(replay, header_only=False, adapter_name="rust")

    assert [touch["source"] for touch in report["events"]["touches"]] == ["parser"]
    assert [demo["source"] for demo in report["events"]["demos"]] == ["parser"]
    assert [kickoff["source"] for kickoff in report["events"]["kickoffs"]] == ["parser"]
    assert len(report["events"]["touches"]) == 1
    assert len(report["events"]["demos"]) == 1
    assert len(report["events"]["kickoffs"]) == 1
    timeline_sources = {
        event["type"]: event.get("data", {}).get("source")
        for event in report["events"]["timeline"]
        if event["type"] in {"TOUCH", "DEMO", "KICKOFF"}
    }
    assert timeline_sources == {
        "TOUCH": "parser",
        "DEMO": "parser",
        "KICKOFF": "parser",
    }
    assert repeated["events"] == report["events"]
    validate_report(report)


def test_report_marks_unusable_network_parse_when_player_coverage_is_empty(
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

    frame_payload = {
        "timestamp": 0.0,
        "ball": {
            "position": {"x": 0.0, "y": 0.0, "z": 93.15},
            "velocity": {"x": 0.0, "y": 0.0, "z": 0.0},
            "angular_velocity": {"x": 0.0, "y": 0.0, "z": 0.0},
        },
        "players": [],
        "boost_pad_events": [],
    }
    network = NetworkFrames(
        frame_count=1,
        sample_rate=30.0,
        frames=[frame_payload],
        diagnostics=NetworkDiagnostics(
            status="ok",
            error_code=None,
            error_detail=None,
            frames_emitted=1,
            attempted_backends=["boxcars"],
        ),
    )
    monkeypatch.setattr(
        "rlcoach.report.get_adapter", lambda _name: _FakeNetworkAdapter(network)
    )

    report = generate_report(replay, header_only=False, adapter_name="rust")
    scorecard = report["quality"]["parser"]["scorecard"]

    assert scorecard["usable_network_parse"] is False
    assert scorecard["non_empty_player_frame_coverage"] == 0.0
    assert scorecard["player_identity_coverage"] == 0.0
    assert scorecard["players_with_identity"] == 0
    assert scorecard["expected_players"] == 2


def test_report_marks_missing_expected_players_as_zero_identity_coverage(
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

    frame_payload = {
        "timestamp": 0.0,
        "ball": {
            "position": {"x": 0.0, "y": 0.0, "z": 93.15},
            "velocity": {"x": 0.0, "y": 0.0, "z": 0.0},
            "angular_velocity": {"x": 0.0, "y": 0.0, "z": 0.0},
        },
        "players": [
            {
                "team": 0,
                "position": {"x": 0.0, "y": -1000.0, "z": 17.0},
                "velocity": {"x": 0.0, "y": 0.0, "z": 0.0},
                "rotation": {"pitch": 0.0, "yaw": 0.0, "roll": 0.0},
                "boost_amount": 33,
                "is_on_ground": True,
            }
        ],
        "boost_pad_events": [],
    }
    network = NetworkFrames(
        frame_count=1,
        sample_rate=30.0,
        frames=[frame_payload],
        diagnostics=NetworkDiagnostics(
            status="ok",
            error_code=None,
            error_detail=None,
            frames_emitted=1,
            attempted_backends=["boxcars"],
        ),
    )
    monkeypatch.setattr(
        "rlcoach.report.get_adapter",
        lambda _name: _FakeNetworkAdapterWithoutHeaderPlayers(network),
    )

    report = generate_report(replay, header_only=False, adapter_name="rust")
    scorecard = report["quality"]["parser"]["scorecard"]

    assert scorecard["usable_network_parse"] is False
    assert scorecard["non_empty_player_frame_coverage"] == 1.0
    assert scorecard["player_identity_coverage"] == 0.0
    assert scorecard["players_with_identity"] == 0
    assert scorecard["expected_players"] == 0
    validate_report(report)


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


class _FakeAdapterWithHeaderGoalsButNoFrames:
    """Fake adapter that has goals in header but no actual network frames."""

    def __init__(self):
        self._name = "rust"

    @property
    def name(self) -> str:
        return self._name

    @property
    def supports_network_parsing(self) -> bool:
        return True

    def parse_header(self, path: Path):
        # Return header WITH goals metadata but no actual frame data
        from rlcoach.parser.types import GoalHeader, Highlight, PlayerInfo

        return Header(
            playlist_id="13",
            map_name="DFH_Stadium",
            team_size=2,
            team0_score=3,
            team1_score=2,
            match_guid="fake-guid",
            players=[
                PlayerInfo(name="Blue1", team=0),
                PlayerInfo(name="Blue2", team=0),
                PlayerInfo(name="Orange1", team=1),
                PlayerInfo(name="Orange2", team=1),
            ],
            # Goals and highlights parsed from header (network-derived content)
            goals=[
                GoalHeader(frame=527, player_name="Orange1", player_team=1),
                GoalHeader(frame=987, player_name="Orange2", player_team=1),
                GoalHeader(frame=1706, player_name="Blue1", player_team=0),
            ],
            highlights=[
                Highlight(frame=520),
                Highlight(frame=980),
                Highlight(frame=1700),
            ],
        )

    def parse_network(self, path: Path):
        # Return empty frames - no actual network data
        return NetworkFrames(
            frame_count=0,
            sample_rate=30.0,
            frames=[],
            diagnostics=NetworkDiagnostics(
                status="unavailable",
                error_code="network_data_unavailable",
                error_detail="header only mode",
                frames_emitted=0,
                attempted_backends=["boxcars"],
            ),
        )


def test_header_only_no_network_no_goal_leakage(tmp_path: Path, monkeypatch):
    """Regression: no goals/timeline when header-only or no frames parsed.

    When parsed_network_data=false and frames_emitted=0, goals and timeline
    events must NOT be emitted, even if header.goals exists. header.goals
    is network-derived content that must not leak into the output.
    """
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
        "rlcoach.report.get_adapter",
        lambda _name: _FakeAdapterWithHeaderGoalsButNoFrames(),
    )

    # Case 1: Explicit header_only=True
    report = generate_report(replay, header_only=True, adapter_name="rust")
    assert report["quality"]["parser"]["parsed_network_data"] is False
    assert report["quality"]["parser"]["network_diagnostics"]["frames_emitted"] == 0
    assert report["events"]["goals"] == []
    assert report["events"]["timeline"] == []
    validate_report(report)

    # Case 2: header_only=False but adapter returns no frames
    report2 = generate_report(replay, header_only=False, adapter_name="rust")
    assert report2["quality"]["parser"]["parsed_network_data"] is False
    assert report2["quality"]["parser"]["network_diagnostics"]["frames_emitted"] == 0
    assert report2["events"]["goals"] == []
    assert report2["events"]["timeline"] == []
    validate_report(report2)
