# tests/api/test_coach_tools_api.py
"""Tests for coach tool schema and execution endpoints."""

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
def client(mock_config, monkeypatch):
    """Create a test client with authenticated user override."""
    from rlcoach.api.auth import CurrentUser, get_current_user
    from rlcoach.db import User
    from rlcoach.db.session import create_session

    def _override_user():
        return CurrentUser(
            id="user-1",
            email="test@example.com",
            subscription_tier="pro",
            is_pro=True,
        )

    monkeypatch.delenv("DATABASE_URL", raising=False)

    with patch("rlcoach.api.app.load_config", return_value=mock_config), patch(
        "rlcoach.api.app.get_config", return_value=mock_config
    ):
        from rlcoach.api.app import create_app

        app = create_app()
        app.dependency_overrides[get_current_user] = _override_user

        with TestClient(app) as test_client:
            session = create_session()
            session.add(
                User(
                    id="user-1",
                    email="test@example.com",
                    subscription_tier="pro",
                    token_budget_used=0,
                )
            )
            session.commit()
            session.close()
            yield test_client


def test_tools_schema_returns_tools(client: TestClient):
    response = client.get("/api/v1/coach/tools/schema")
    assert response.status_code == 200
    data = response.json()
    assert "tools" in data
    assert any(tool["name"] == "get_rank_benchmarks" for tool in data["tools"])
