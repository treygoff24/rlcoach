# tests/api/test_analysis.py
"""Tests for analysis API endpoints."""

from datetime import date, datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def mock_config(tmp_path):
    """Create a mock config for testing."""
    from rlcoach.config import (
        IdentityConfig,
        PathsConfig,
        PreferencesConfig,
        RLCoachConfig,
    )

    config = RLCoachConfig(
        identity=IdentityConfig(
            platform_ids=["steam:me123"],
            display_names=["TestPlayer"],
        ),
        paths=PathsConfig(
            watch_folder=tmp_path / "replays",
            data_dir=tmp_path / "data",
            reports_dir=tmp_path / "reports",
        ),
        preferences=PreferencesConfig(
            primary_playlist="DOUBLES",
            target_rank="GC1",
        ),
    )
    config.paths.data_dir.mkdir(parents=True, exist_ok=True)
    return config


@pytest.fixture
def db_with_analysis_data(mock_config):
    """Initialize database with analysis test data."""
    from rlcoach.db.models import Benchmark, Player, PlayerGameStats, Replay
    from rlcoach.db.session import create_session, init_db, reset_engine

    init_db(mock_config.db_path)
    session = create_session()

    # Add player
    session.add(Player(player_id="steam:me123", display_name="TestPlayer", is_me=True))

    # Add replays with varying stats for pattern analysis
    for i in range(10):
        result = "WIN" if i % 2 == 0 else "LOSS"
        bcpm = 400.0 if result == "WIN" else 320.0  # Clear pattern
        session.add(
            Replay(
                replay_id=f"replay_{i}",
                source_file=f"/path/replay_{i}.replay",
                file_hash=f"hash_{i}",
                played_at_utc=datetime(2024, 12, 23, 10 + i, 0, 0, tzinfo=timezone.utc),
                play_date=date(2024, 12, 20 + (i // 3)),
                map="DFH Stadium",
                playlist="DOUBLES",
                team_size=2,
                duration_seconds=300.0,
                my_player_id="steam:me123",
                my_team="BLUE",
                my_score=2 if result == "WIN" else 1,
                opponent_score=1 if result == "WIN" else 2,
                result=result,
                json_report_path=f"/path/replay_{i}.json",
            )
        )
        session.add(
            PlayerGameStats(
                replay_id=f"replay_{i}",
                player_id="steam:me123",
                team="BLUE",
                is_me=True,
                goals=2 if result == "WIN" else 0,
                assists=1,
                saves=2,
                shots=4,
                bcpm=bcpm,
                avg_boost=35.0,
            )
        )

    # Add benchmarks
    session.add(
        Benchmark(
            metric="bcpm",
            playlist="DOUBLES",
            rank_tier="GC1",
            p25_value=320.0,
            median_value=360.0,
            p75_value=400.0,
            elite_threshold=450.0,
            source="test",
        )
    )
    session.add(
        Benchmark(
            metric="avg_boost",
            playlist="DOUBLES",
            rank_tier="GC1",
            p25_value=30.0,
            median_value=35.0,
            p75_value=40.0,
            elite_threshold=48.0,
            source="test",
        )
    )

    session.commit()
    session.close()

    yield mock_config

    reset_engine()


@pytest.fixture
def client(db_with_analysis_data):
    """Create a test client with analysis data."""
    with patch("rlcoach.api.app.get_config", return_value=db_with_analysis_data):
        from rlcoach.api.app import create_app

        app = create_app()
        yield TestClient(app)


class TestTrendsEndpoint:
    """Tests for GET /trends."""

    def test_trends_returns_data(self, client):
        """Should return trend data."""
        response = client.get("/trends?metric=bcpm")
        assert response.status_code == 200
        data = response.json()

        assert "metric" in data
        assert "values" in data
        assert data["metric"] == "bcpm"

    def test_trends_filter_by_period(self, client):
        """Should filter by time period."""
        response = client.get("/trends?metric=bcpm&period=7d")
        assert response.status_code == 200
        data = response.json()

        assert "period" in data


class TestBenchmarksEndpoint:
    """Tests for GET /benchmarks."""

    def test_benchmarks_returns_list(self, client):
        """Should return list of benchmarks."""
        response = client.get("/benchmarks")
        assert response.status_code == 200
        data = response.json()

        assert "items" in data
        assert len(data["items"]) > 0

    def test_benchmarks_filter_by_metric(self, client):
        """Should filter by metric."""
        response = client.get("/benchmarks?metric=bcpm")
        assert response.status_code == 200
        data = response.json()

        for item in data["items"]:
            assert item["metric"] == "bcpm"

    def test_benchmarks_filter_by_rank(self, client):
        """Should filter by rank."""
        response = client.get("/benchmarks?rank=GC1")
        assert response.status_code == 200
        data = response.json()

        for item in data["items"]:
            assert item["rank_tier"] == "GC1"


class TestCompareEndpoint:
    """Tests for GET /compare."""

    def test_compare_returns_comparison(self, client):
        """Should return comparison data."""
        response = client.get("/compare?rank=GC1")
        assert response.status_code == 200
        data = response.json()

        assert "comparisons" in data
        assert "target_rank" in data

    def test_compare_requires_rank(self, client):
        """Should require rank parameter."""
        response = client.get("/compare")
        assert response.status_code == 422  # Validation error


class TestPatternsEndpoint:
    """Tests for GET /patterns."""

    def test_patterns_returns_analysis(self, client):
        """Should return pattern analysis."""
        response = client.get("/patterns")
        assert response.status_code == 200
        data = response.json()

        assert "patterns" in data

    def test_patterns_includes_effect_size(self, client):
        """Should include effect size for significant patterns."""
        response = client.get("/patterns")
        data = response.json()

        if data["patterns"]:
            assert "effect_size" in data["patterns"][0]
            assert "direction" in data["patterns"][0]


class TestWeaknessesEndpoint:
    """Tests for GET /weaknesses."""

    def test_weaknesses_returns_analysis(self, client):
        """Should return weakness analysis."""
        response = client.get("/weaknesses")
        assert response.status_code == 200
        data = response.json()

        assert "weaknesses" in data
        assert "strengths" in data

    def test_weaknesses_includes_severity(self, client):
        """Should include severity for each weakness."""
        response = client.get("/weaknesses")
        data = response.json()

        for weakness in data["weaknesses"]:
            assert "severity" in weakness
            assert "z_score" in weakness
