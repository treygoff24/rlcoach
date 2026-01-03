# tests/api/test_app.py
"""Tests for FastAPI app setup."""

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
    # Create directories
    config.paths.data_dir.mkdir(parents=True, exist_ok=True)
    return config


@pytest.fixture
def client(mock_config):
    """Create a test client with mocked config."""
    with patch("rlcoach.api.app.get_config", return_value=mock_config):
        from rlcoach.api.app import create_app
        app = create_app()
        yield TestClient(app)


class TestHealthEndpoint:
    """Tests for the health check endpoint."""

    def test_health_returns_ok(self, client):
        """Should return a valid health status (healthy or degraded)."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["healthy", "degraded"]
        assert "version" in data

    def test_health_includes_db_status(self, client):
        """Should include database status in checks."""
        response = client.get("/health")
        data = response.json()
        assert "checks" in data
        assert "database" in data["checks"]
        assert data["checks"]["database"] in [
            "connected",
            "disconnected",
            "not_initialized",
        ]

    def test_health_includes_service_info(self, client):
        """Should include service name and timestamp."""
        response = client.get("/health")
        data = response.json()
        assert data["service"] == "rlcoach-backend"
        assert "timestamp" in data


class TestCORS:
    """Tests for CORS configuration."""

    def test_cors_allows_localhost(self, client):
        """Should allow requests from localhost."""
        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            }
        )
        # CORS preflight should return 200
        assert response.status_code == 200


class TestErrorHandling:
    """Tests for error handling middleware."""

    def test_404_returns_json(self, client):
        """Should return JSON for 404 errors."""
        response = client.get("/nonexistent/endpoint")
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data


class TestRootEndpoint:
    """Tests for the root endpoint."""

    def test_root_returns_api_info(self, client):
        """Should return API information."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data
        assert "docs" in data
