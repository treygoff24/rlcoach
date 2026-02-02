# tests/api/test_coach_history.py
"""Tests for coach session history endpoints."""

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
    """Create a test client with Pro user override."""
    from rlcoach.api.auth import CurrentUser, get_current_user, require_pro
    from rlcoach.db import CoachMessage, CoachSession, User
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
        app.dependency_overrides[require_pro] = _override_user

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
            session.add(
                CoachSession(
                    id="session-1",
                    user_id="user-1",
                    message_count=1,
                )
            )
            session.add(
                CoachMessage(
                    id="message-1",
                    session_id="session-1",
                    role="user",
                    content="Hello coach",
                )
            )
            session.commit()
            session.close()
            yield test_client


def test_session_messages_include_content_blocks(client: TestClient):
    response = client.get("/api/v1/coach/sessions/session-1/messages")
    assert response.status_code == 200
    data = response.json()
    assert data
    assert "content_blocks" in data[0]
    assert data[0]["content_blocks"] == [{"type": "text", "text": "Hello coach"}]
