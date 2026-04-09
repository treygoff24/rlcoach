# tests/test_benchmarks.py
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from rlcoach.benchmarks import import_benchmarks, validate_benchmark_data
from rlcoach.db.models import Benchmark
from rlcoach.db.session import create_session, init_db, reset_engine
from rlcoach.parser.types import Header, NetworkDiagnostics, NetworkFrames, PlayerInfo


@pytest.fixture(autouse=True)
def reset_db():
    yield
    reset_engine()


def test_validate_uses_metric_catalog():
    """Validation should use the metric catalog, not a hardcoded list."""

    data = {
        "metadata": {"source": "test"},
        "benchmarks": [
            {
                "metric": "bcpm",
                "playlist": "DOUBLES",
                "rank_tier": "GC1",
                "median": 380,
            }
        ],
    }
    errors = validate_benchmark_data(data)
    assert errors == []


def test_validate_rejects_invalid_metric():
    """Should reject metrics not in the catalog."""
    data = {
        "metadata": {"source": "test"},
        "benchmarks": [
            {
                "metric": "made_up_metric",
                "playlist": "DOUBLES",
                "rank_tier": "GC1",
                "median": 100,
            }
        ],
    }
    errors = validate_benchmark_data(data)
    assert any("metric" in e.lower() for e in errors)


def test_import_benchmarks_success(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)

    benchmark_file = tmp_path / "benchmarks.json"
    benchmark_file.write_text(
        json.dumps(
            {
                "metadata": {
                    "source": "Test Source",
                    "collected_date": "2024-12-01",
                    "notes": "Test data",
                },
                "benchmarks": [
                    {
                        "metric": "bcpm",
                        "playlist": "DOUBLES",
                        "rank_tier": "GC1",
                        "median": 380,
                        "p25": 330,
                        "p75": 420,
                        "elite": 420,
                    },
                    {
                        "metric": "avg_boost",
                        "playlist": "DOUBLES",
                        "rank_tier": "GC1",
                        "median": 30,
                        "p25": 25,
                        "p75": 34,
                        "elite": 20,
                    },
                ],
            }
        )
    )

    count = import_benchmarks(benchmark_file)
    assert count == 2

    session = create_session()
    try:
        benchmark = (
            session.query(Benchmark).filter_by(metric="bcpm", rank_tier="GC1").first()
        )
        assert benchmark is not None
        assert benchmark.median_value == 380
        assert benchmark.source == "Test Source"
    finally:
        session.close()


def test_import_benchmarks_upserts(tmp_path):
    """Re-importing should update existing records."""
    db_path = tmp_path / "test.db"
    init_db(db_path)

    benchmark_file = tmp_path / "benchmarks.json"

    benchmark_file.write_text(
        json.dumps(
            {
                "metadata": {"source": "v1"},
                "benchmarks": [
                    {
                        "metric": "bcpm",
                        "playlist": "DOUBLES",
                        "rank_tier": "GC1",
                        "median": 100,
                    }
                ],
            }
        )
    )
    import_benchmarks(benchmark_file)

    benchmark_file.write_text(
        json.dumps(
            {
                "metadata": {"source": "v2"},
                "benchmarks": [
                    {
                        "metric": "bcpm",
                        "playlist": "DOUBLES",
                        "rank_tier": "GC1",
                        "median": 200,
                    }
                ],
            }
        )
    )
    import_benchmarks(benchmark_file)

    session = create_session()
    try:
        benchmarks = (
            session.query(Benchmark).filter_by(metric="bcpm", rank_tier="GC1").all()
        )
        assert len(benchmarks) == 1
        assert benchmarks[0].median_value == 200
        assert benchmarks[0].source == "v2"
    finally:
        session.close()


def _corpus_health_script_path() -> Path:
    return Path(__file__).resolve().parents[1] / "scripts" / "parser_corpus_health.py"


def _load_corpus_health_module():
    spec = importlib.util.spec_from_file_location(
        "parser_corpus_health", _corpus_health_script_path()
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parser_corpus_health_output_schema(tmp_path):
    result = subprocess.run(
        [sys.executable, str(_corpus_health_script_path()), "--dry", "--json"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)

    assert payload["total"] == 0
    assert isinstance(payload["header_success_rate"], float)
    assert isinstance(payload["network_success_rate"], float)
    assert isinstance(payload["usable_network_parse_rate"], float)
    assert isinstance(payload["degraded_count"], int)
    assert isinstance(payload["avg_non_empty_player_frame_coverage"], float)
    assert isinstance(payload["avg_player_identity_coverage"], float)
    assert isinstance(payload["avg_parser_event_frame_coverage"], float)
    assert isinstance(payload["parser_event_totals"], dict)
    assert isinstance(payload["parser_event_source_counts"], dict)
    assert isinstance(payload["parser_event_coverage"], dict)
    assert isinstance(payload["event_provenance"], dict)
    assert isinstance(payload["scorecard_coverage"], dict)
    assert isinstance(payload["top_error_codes"], list)

    metadata = payload["corpus_metadata"]
    assert isinstance(metadata, dict)
    assert isinstance(metadata["playlist_buckets"], dict)
    assert isinstance(metadata["match_type_buckets"], dict)
    assert isinstance(metadata["engine_build_buckets"], dict)


def test_parser_corpus_health_reports_invalid_roots(tmp_path):
    missing_root = tmp_path / "missing"

    result = subprocess.run(
        [
            sys.executable,
            str(_corpus_health_script_path()),
            "--roots",
            str(missing_root),
            "--json",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["error"] == "invalid_roots"
    assert payload["error_code"] == "invalid_replay_root"
    assert payload["invalid_roots"] == [str(missing_root)]


def test_parser_corpus_health_reports_no_replays_found(tmp_path):
    empty_root = tmp_path / "replays"
    empty_root.mkdir()

    result = subprocess.run(
        [
            sys.executable,
            str(_corpus_health_script_path()),
            "--roots",
            str(empty_root),
            "--json",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 3
    payload = json.loads(result.stdout)
    assert payload["error"] == "no_replays_found"
    assert payload["searched_roots"] == [str(empty_root)]


def test_parser_corpus_health_treats_missing_expected_players_as_zero_coverage(
    monkeypatch,
):
    module = _load_corpus_health_module()

    class _FakeAdapter:
        supports_network_parsing = True

        def parse_header(self, _path):
            return Header(
                playlist_id="13",
                map_name="DFH_Stadium",
                team_size=1,
                team0_score=1,
                team1_score=0,
                match_guid="fake-guid",
                players=[],
            )

        def parse_network(self, _path):
            return NetworkFrames(
                frame_count=1,
                sample_rate=30.0,
                frames=[
                    {
                        "timestamp": 0.0,
                        "ball": {"position": {"x": 0.0, "y": 0.0, "z": 93.15}},
                        "players": [{"team": 0}],
                        "boost_pad_events": [],
                    }
                ],
                diagnostics=NetworkDiagnostics(
                    status="ok",
                    error_code=None,
                    error_detail=None,
                    frames_emitted=1,
                ),
            )

    monkeypatch.setattr(module, "get_adapter", lambda _name: _FakeAdapter())

    record = module._evaluate_replay(Path("sample.replay"), "rust")

    assert record["usable_network_parse"] is False
    assert record["non_empty_player_frame_coverage"] == 1.0
    assert record["player_identity_coverage"] == 0.0
    assert record["players_with_identity"] == 0
    assert record["expected_players"] == 0


def test_parser_corpus_health_tracks_parser_event_and_provenance_metrics(monkeypatch):
    module = _load_corpus_health_module()

    class _FakeAdapter:
        supports_network_parsing = True

        def parse_header(self, _path):
            return Header(
                playlist_id="13",
                map_name="DFH_Stadium",
                team_size=1,
                team0_score=1,
                team1_score=0,
                match_guid="fake-guid",
                players=[
                    PlayerInfo(name="Blue", platform_id="player_a", team=0),
                    PlayerInfo(name="Orange", platform_id="player_b", team=1),
                ],
            )

        def parse_network(self, _path):
            diagnostics = NetworkDiagnostics(
                status="ok",
                error_code=None,
                error_detail=None,
                frames_emitted=2,
                attempted_backends=["boxcars"],
            )
            return NetworkFrames(
                frame_count=2,
                sample_rate=30.0,
                diagnostics=diagnostics,
                frames=[
                    {
                        "timestamp": 0.0,
                        "players": [{"player_id": "player_a", "team": 0}],
                        "boost_pad_events": [],
                        "parser_touch_events": [
                            {
                                "timestamp": 0.0,
                                "player_id": "player_a",
                                "source": "parser",
                            }
                        ],
                        "parser_demo_events": [],
                        "parser_tickmarks": [
                            {
                                "timestamp": 0.0,
                                "kind": "kickoff",
                                "source": "parser",
                            }
                        ],
                        "parser_kickoff_markers": [
                            {
                                "timestamp": 0.0,
                                "phase": "INITIAL",
                                "source": "parser",
                            }
                        ],
                    },
                    {
                        "timestamp": 0.1,
                        "players": [{"player_id": "player_b", "team": 1}],
                        "boost_pad_events": [],
                        "parser_touch_events": [],
                        "parser_demo_events": [
                            {
                                "timestamp": 0.1,
                                "victim_id": "player_b",
                                "attacker_id": "player_a",
                                "victim_team": 1,
                                "attacker_team": 0,
                                "source": "parser",
                            }
                        ],
                        "parser_tickmarks": [],
                        "parser_kickoff_markers": [],
                    },
                ],
            )

    monkeypatch.setattr(module, "get_adapter", lambda _name: _FakeAdapter())

    record = module._evaluate_replay(Path("sample.replay"), "rust")
    summary = module._build_summary([record])

    assert record["parser_event_frame_coverage"] == 1.0
    assert record["parser_event_totals"] == {
        "touches": 1,
        "demos": 1,
        "tickmarks": 1,
        "kickoff_markers": 1,
    }
    assert record["parser_event_source_counts"] == {
        "parser": 4,
        "inferred": 0,
        "missing": 0,
        "other": 0,
    }
    assert summary["parser_event_coverage"] == {
        "touch_event_rate": 1.0,
        "demo_event_rate": 1.0,
        "tickmark_event_rate": 1.0,
        "kickoff_marker_rate": 1.0,
        "avg_touch_frame_coverage": 0.5,
        "avg_demo_frame_coverage": 0.5,
        "avg_tickmark_frame_coverage": 0.5,
        "avg_kickoff_frame_coverage": 0.5,
    }
    assert summary["event_provenance"] == {
        "touch_parser_rate": 1.0,
        "demo_parser_rate": 1.0,
        "kickoff_parser_rate": 1.0,
    }
    assert (
        summary["scorecard_coverage"]["usable_network_parse_rate"]
        == summary["usable_network_parse_rate"]
    )
    assert (
        summary["scorecard_coverage"]["avg_non_empty_player_frame_coverage"]
        == summary["avg_non_empty_player_frame_coverage"]
    )
    assert (
        summary["scorecard_coverage"]["avg_player_identity_coverage"]
        == summary["avg_player_identity_coverage"]
    )
