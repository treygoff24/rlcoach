# tests/api/test_coach_recap.py
"""Tests for the session recap endpoint.

Covers:
- AI-powered recap (mocked Anthropic call)
- Keyword fallback when ANTHROPIC_API_KEY is absent
- Keyword fallback when the Anthropic call raises an exception
- 404 for unknown session
- 400 when the session has fewer than 3 messages
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_config(tmp_path):
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


@pytest.fixture()
def client_with_messages(mock_config, monkeypatch):
    """Test client with a session that has 3 messages (enough for a recap)."""
    from rlcoach.api.auth import CurrentUser, get_current_user
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

        with TestClient(app) as test_client:
            db = create_session()
            db.add(
                User(
                    id="user-1",
                    email="test@example.com",
                    subscription_tier="pro",
                    token_budget_used=0,
                )
            )
            db.add(CoachSession(id="session-1", user_id="user-1", message_count=3))
            db.add(
                CoachMessage(
                    id="msg-1",
                    session_id="session-1",
                    role="user",
                    content="My aerial game feels weak.",
                )
            )
            db.add(
                CoachMessage(
                    id="msg-2",
                    session_id="session-1",
                    role="assistant",
                    content=(
                        "Your strength is your positioning. "
                        "Your weakness is aerial control. "
                        "You should practice freeplay aerials daily."
                    ),
                )
            )
            db.add(
                CoachMessage(
                    id="msg-3",
                    session_id="session-1",
                    role="user",
                    content="Thanks, I'll try that.",
                )
            )
            db.commit()
            db.close()
            yield test_client


@pytest.fixture()
def client_insufficient_messages(mock_config, monkeypatch):
    """Test client with a session that has only 2 messages."""
    from rlcoach.api.auth import CurrentUser, get_current_user
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

        with TestClient(app) as test_client:
            db = create_session()
            db.add(
                User(
                    id="user-1",
                    email="test@example.com",
                    subscription_tier="pro",
                    token_budget_used=0,
                )
            )
            db.add(CoachSession(id="session-short", user_id="user-1", message_count=2))
            db.add(
                CoachMessage(
                    id="msg-a",
                    session_id="session-short",
                    role="user",
                    content="Hi",
                )
            )
            db.add(
                CoachMessage(
                    id="msg-b",
                    session_id="session-short",
                    role="assistant",
                    content="Hello",
                )
            )
            db.commit()
            db.close()
            yield test_client


# ---------------------------------------------------------------------------
# Helper: build a fake Anthropic response and mock module
# ---------------------------------------------------------------------------


def _fake_anthropic_response(payload: dict) -> MagicMock:
    text_block = SimpleNamespace(text=json.dumps(payload))
    response = MagicMock()
    response.content = [text_block]
    return response


def _make_anthropic_module(fake_client: MagicMock) -> MagicMock:
    """Return a mock that acts as the anthropic module with Anthropic() -> fake_client."""
    mock_module = MagicMock()
    mock_module.Anthropic.return_value = fake_client
    return mock_module


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_recap_uses_ai_when_api_key_set(client_with_messages: TestClient, monkeypatch):
    """AI recap is returned when ANTHROPIC_API_KEY is present and the call succeeds."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    ai_payload = {
        "strengths": ["Great positioning"],
        "weaknesses": ["Aerial control needs work"],
        "action_items": ["Practice freeplay aerials"],
        "summary": "Session focused on aerial improvement.",
    }

    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_anthropic_response(ai_payload)

    with patch(
        "rlcoach.api.routers.coach.anthropic",
        new=_make_anthropic_module(fake_client),
    ):
        response = client_with_messages.get("/api/v1/coach/sessions/session-1/recap")

    assert response.status_code == 200
    data = response.json()
    assert data["strengths"] == ["Great positioning"]
    assert data["weaknesses"] == ["Aerial control needs work"]
    assert data["action_items"] == ["Practice freeplay aerials"]
    assert data["summary"] == "Session focused on aerial improvement."
    assert data["message_count"] == 3
    assert data["session_id"] == "session-1"


def test_recap_falls_back_to_keywords_without_api_key(
    client_with_messages: TestClient, monkeypatch
):
    """Keyword fallback is used when ANTHROPIC_API_KEY is not set."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    response = client_with_messages.get("/api/v1/coach/sessions/session-1/recap")

    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "session-1"
    assert data["message_count"] == 3
    assert isinstance(data["strengths"], list)
    assert isinstance(data["weaknesses"], list)
    assert isinstance(data["action_items"], list)
    assert isinstance(data["summary"], str)
    assert len(data["summary"]) > 0


def test_recap_falls_back_to_keywords_on_api_error(
    client_with_messages: TestClient, monkeypatch
):
    """Keyword fallback is used when the Anthropic API call raises an exception."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    fake_client = MagicMock()
    fake_client.messages.create.side_effect = RuntimeError("API unavailable")

    with patch(
        "rlcoach.api.routers.coach.anthropic",
        new=_make_anthropic_module(fake_client),
    ):
        response = client_with_messages.get("/api/v1/coach/sessions/session-1/recap")

    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "session-1"
    assert isinstance(data["strengths"], list)


def test_recap_falls_back_to_keywords_on_json_parse_error(
    client_with_messages: TestClient, monkeypatch
):
    """Keyword fallback is used when the AI returns invalid JSON."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    bad_response = MagicMock()
    bad_response.content = [SimpleNamespace(text="not valid json!!!")]
    fake_client = MagicMock()
    fake_client.messages.create.return_value = bad_response

    with patch(
        "rlcoach.api.routers.coach.anthropic",
        new=_make_anthropic_module(fake_client),
    ):
        response = client_with_messages.get("/api/v1/coach/sessions/session-1/recap")

    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "session-1"


def test_recap_404_for_unknown_session(client_with_messages: TestClient, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    response = client_with_messages.get("/api/v1/coach/sessions/nonexistent/recap")
    assert response.status_code == 404


def test_recap_400_insufficient_messages(
    client_insufficient_messages: TestClient, monkeypatch
):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    response = client_insufficient_messages.get(
        "/api/v1/coach/sessions/session-short/recap"
    )
    assert response.status_code == 400
    assert "3 messages" in response.json()["detail"]


def test_recap_ai_response_strips_markdown_fences(
    client_with_messages: TestClient, monkeypatch
):
    """AI response wrapped in markdown code fences is handled correctly."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    payload = {
        "strengths": ["Rotation"],
        "weaknesses": ["Boost management"],
        "action_items": ["Drill boost pads"],
        "summary": "Good session overall.",
    }
    fenced_text = f"```json\n{json.dumps(payload)}\n```"

    fenced_response = MagicMock()
    fenced_response.content = [SimpleNamespace(text=fenced_text)]
    fake_client = MagicMock()
    fake_client.messages.create.return_value = fenced_response

    with patch(
        "rlcoach.api.routers.coach.anthropic",
        new=_make_anthropic_module(fake_client),
    ):
        response = client_with_messages.get("/api/v1/coach/sessions/session-1/recap")

    assert response.status_code == 200
    data = response.json()
    assert data["strengths"] == ["Rotation"]
    assert data["summary"] == "Good session overall."
