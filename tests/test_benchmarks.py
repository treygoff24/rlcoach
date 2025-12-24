# tests/test_benchmarks.py
import pytest
import json
from pathlib import Path
from rlcoach.benchmarks import import_benchmarks, validate_benchmark_data, BenchmarkValidationError
from rlcoach.db.session import init_db, create_session, reset_engine
from rlcoach.db.models import Benchmark


@pytest.fixture(autouse=True)
def reset_db():
    yield
    reset_engine()


def test_validate_uses_metric_catalog():
    """Validation should use the metric catalog, not a hardcoded list."""
    from rlcoach.metrics import METRIC_CATALOG

    data = {
        "metadata": {"source": "test"},
        "benchmarks": [
            {
                "metric": "bcpm",  # Valid metric from catalog
                "playlist": "DOUBLES",
                "rank_tier": "GC1",
                "median": 380
            }
        ]
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
                "median": 100
            }
        ]
    }
    errors = validate_benchmark_data(data)
    assert any("metric" in e.lower() for e in errors)


def test_import_benchmarks_success(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)

    benchmark_file = tmp_path / "benchmarks.json"
    benchmark_file.write_text(json.dumps({
        "metadata": {
            "source": "Test Source",
            "collected_date": "2024-12-01",
            "notes": "Test data"
        },
        "benchmarks": [
            {
                "metric": "bcpm",
                "playlist": "DOUBLES",
                "rank_tier": "GC1",
                "median": 380,
                "p25": 330,
                "p75": 420,
                "elite": 420
            },
            {
                "metric": "avg_boost",
                "playlist": "DOUBLES",
                "rank_tier": "GC1",
                "median": 30,
                "p25": 25,
                "p75": 34,
                "elite": 20
            }
        ]
    }))

    count = import_benchmarks(benchmark_file)
    assert count == 2

    session = create_session()
    try:
        benchmark = session.query(Benchmark).filter_by(metric="bcpm", rank_tier="GC1").first()
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

    # First import
    benchmark_file.write_text(json.dumps({
        "metadata": {"source": "v1"},
        "benchmarks": [{"metric": "bcpm", "playlist": "DOUBLES", "rank_tier": "GC1", "median": 100}]
    }))
    import_benchmarks(benchmark_file)

    # Second import with updated value
    benchmark_file.write_text(json.dumps({
        "metadata": {"source": "v2"},
        "benchmarks": [{"metric": "bcpm", "playlist": "DOUBLES", "rank_tier": "GC1", "median": 200}]
    }))
    import_benchmarks(benchmark_file)

    session = create_session()
    try:
        benchmarks = session.query(Benchmark).filter_by(metric="bcpm", rank_tier="GC1").all()
        assert len(benchmarks) == 1
        assert benchmarks[0].median_value == 200
        assert benchmarks[0].source == "v2"
    finally:
        session.close()
