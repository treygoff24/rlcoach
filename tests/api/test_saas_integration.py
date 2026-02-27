# tests/api/test_saas_integration.py
"""SaaS integration tests for Phase 6 verification.

Covers critical production code paths:
- Auth edge cases (expired tokens, missing headers, ghost users)
- Replay upload validation (bad files, size limits, duplicates)
- Dashboard endpoint with real DB data
- GDPR data export completeness
- User bootstrap flow (new user, existing user, account linking)
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from unittest.mock import patch

import jwt
import pytest
from fastapi.testclient import TestClient

# ──────────────────────────────────────────────────────────
# Shared fixtures
# ──────────────────────────────────────────────────────────

TEST_USER_ID = "saas-test-user-001"
JWT_SECRET = "saas-test-jwt-secret-32bytes-long!"  # 32+ bytes for HS256


def _make_token(user_id: str = TEST_USER_ID, expired: bool = False) -> str:
    """Create a test JWT token."""
    if expired:
        exp = int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp())
    else:
        exp = int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())
    return jwt.encode(
        {"sub": user_id, "exp": exp},
        JWT_SECRET,
        algorithm="HS256",
    )


def _make_valid_replay_content(size: int = 5000) -> bytes:
    """Build minimal valid Rocket League replay bytes (TAGame marker present)."""
    # Ensure the TAGame marker is within the first 1000 bytes
    header = b"\x00" * 100 + b"TAGame" + b"\x00" * 894
    padding = b"\xab" * max(0, size - len(header))
    return header + padding


@pytest.fixture
def db_setup(tmp_path, monkeypatch):
    """Set up a fresh database with a test user and sample data."""
    from rlcoach.db.models import (
        CoachMessage,
        CoachNote,
        CoachSession,
        Player,
        PlayerGameStats,
        Replay,
        UploadedReplay,
        UserReplay,
    )
    from rlcoach.db.session import create_session, init_db, reset_engine

    monkeypatch.setenv("NEXTAUTH_SECRET", JWT_SECRET)

    db_path = tmp_path / "saas_test.db"
    init_db(db_path)
    session = create_session()

    from rlcoach.db import User

    # Create primary test user
    user = User(
        id=TEST_USER_ID,
        email="saas@example.com",
        display_name="SaasTestPlayer",
        subscription_tier="pro",
        token_budget_used=0,
        token_budget_reset_at=datetime.now(timezone.utc),
        tos_accepted_at=datetime.now(timezone.utc),
    )
    session.add(user)

    # Create a replay owned by the user
    replay_id = "replay-aabbcc-001"
    replay = Replay(
        replay_id=replay_id,
        source_file="/tmp/test_replays/replay_001.replay",
        file_hash="aaaa1111" * 8,
        played_at_utc=datetime.now(timezone.utc) - timedelta(hours=2),
        play_date=date.today(),
        playlist="DOUBLES",
        result="WIN",
        my_score=3,
        opponent_score=1,
        map="DFH Stadium",
        team_size=2,
        duration_seconds=300.0,
        overtime=False,
    )
    session.add(replay)

    # User replay link
    session.add(UserReplay(user_id=TEST_USER_ID, replay_id=replay_id))

    # Player record (for is_me stats)
    player = Player(
        player_id="steam:saas-player-1",
        display_name="SaasTestPlayer",
    )
    session.add(player)

    # Player game stats for this replay (is_me=True)
    pgs = PlayerGameStats(
        replay_id=replay_id,
        player_id="steam:saas-player-1",
        team="blue",
        is_me=True,
        goals=2,
        assists=1,
        saves=3,
        shots=5,
        score=450,
        demos_inflicted=0,
        demos_taken=0,
        avg_boost=55.0,
        wavedash_count=4,
        halfflip_count=2,
        speedflip_count=1,
        aerial_count=3,
    )
    session.add(pgs)

    # A second replay for trend data
    replay2_id = "replay-aabbcc-002"
    replay2 = Replay(
        replay_id=replay2_id,
        source_file="/tmp/test_replays/replay_002.replay",
        file_hash="bbbb2222" * 8,
        played_at_utc=datetime.now(timezone.utc) - timedelta(days=1),
        play_date=date.today() - timedelta(days=1),
        playlist="DOUBLES",
        result="LOSS",
        my_score=0,
        opponent_score=2,
        map="Mannfield",
        team_size=2,
        duration_seconds=280.0,
        overtime=False,
    )
    session.add(replay2)
    session.add(UserReplay(user_id=TEST_USER_ID, replay_id=replay2_id))
    pgs2 = PlayerGameStats(
        replay_id=replay2_id,
        player_id="steam:saas-player-1",
        team="orange",
        is_me=True,
        goals=0,
        assists=0,
        saves=1,
        shots=2,
        score=100,
        demos_inflicted=0,
        demos_taken=1,
        avg_boost=40.0,
    )
    session.add(pgs2)

    # Coach session + messages for GDPR export
    coach_sess = CoachSession(
        id="coach-sess-1",
        user_id=TEST_USER_ID,
        message_count=2,
        total_input_tokens=100,
        total_output_tokens=200,
    )
    session.add(coach_sess)
    session.add(
        CoachMessage(
            id="msg-1",
            session_id="coach-sess-1",
            role="user",
            content="How do I improve my boost management?",
        )
    )
    session.add(
        CoachMessage(
            id="msg-2",
            session_id="coach-sess-1",
            role="assistant",
            content="Focus on collecting big pads...",
        )
    )

    # Coach note for GDPR export
    session.add(
        CoachNote(
            id="note-1",
            user_id=TEST_USER_ID,
            content="Work on boost management",
            category="boost",
            source="coach",
        )
    )

    # An uploaded replay for duplicate-detection tests
    session.add(
        UploadedReplay(
            id="upload-existing-001",
            user_id=TEST_USER_ID,
            filename="existing.replay",
            storage_path="/tmp/rlcoach-test/existing.replay",
            file_size_bytes=5000,
            file_hash="a" * 64,  # known hash for duplicate test
            status="pending",
        )
    )

    session.commit()
    session.close()
    yield db_path
    reset_engine()


@pytest.fixture
def app_no_auth(db_setup, monkeypatch):
    """Test client WITHOUT auth override (real JWT validation runs)."""
    monkeypatch.setenv("NEXTAUTH_SECRET", JWT_SECRET)
    with patch("rlcoach.api.app.get_config", return_value=None):
        from rlcoach.api.app import create_app

        app = create_app()
        yield TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def app_authed(db_setup, monkeypatch):
    """Test client WITH auth override for TEST_USER_ID."""
    monkeypatch.setenv("NEXTAUTH_SECRET", JWT_SECRET)
    from rlcoach.api.auth import CurrentUser, get_current_user

    def _user():
        return CurrentUser(
            id=TEST_USER_ID,
            email="saas@example.com",
            subscription_tier="pro",
            is_pro=True,
        )

    with patch("rlcoach.api.app.get_config", return_value=None):
        from rlcoach.api.app import create_app

        app = create_app()
        app.dependency_overrides[get_current_user] = _user
        yield TestClient(app)


# ══════════════════════════════════════════════════════════
# 1. AUTH EDGE CASES
# ══════════════════════════════════════════════════════════


class TestAuthEdgeCases:
    """HTTP-level authentication edge cases."""

    def test_no_auth_header_returns_401(self, app_no_auth):
        """Missing Authorization header must return 401."""
        resp = app_no_auth.get("/api/v1/users/me")
        assert resp.status_code == 401

    def test_wrong_scheme_returns_401(self, app_no_auth):
        """Basic auth scheme must be rejected."""
        resp = app_no_auth.get(
            "/api/v1/users/me", headers={"Authorization": "Basic abc123"}
        )
        assert resp.status_code == 401

    def test_invalid_token_returns_401(self, app_no_auth):
        """Malformed / garbage JWT must return 401."""
        resp = app_no_auth.get(
            "/api/v1/users/me",
            headers={"Authorization": "Bearer this.is.notjwt"},
        )
        assert resp.status_code == 401

    def test_expired_token_returns_401(self, app_no_auth, monkeypatch):
        """Expired JWT must be rejected with 401 (not 500)."""
        monkeypatch.setenv("NEXTAUTH_SECRET", JWT_SECRET)
        token = _make_token(expired=True)
        resp = app_no_auth.get(
            "/api/v1/users/me", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 401
        # Should mention expiry or credentials, not be a 500
        body = resp.json()
        assert "detail" in body

    def test_valid_token_unknown_user_returns_401(self, app_no_auth, monkeypatch):
        """Token valid but user not in DB must be rejected with 401."""
        monkeypatch.setenv("NEXTAUTH_SECRET", JWT_SECRET)
        token = _make_token(user_id="ghost-user-does-not-exist")
        resp = app_no_auth.get(
            "/api/v1/users/me", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 401

    def test_bearer_empty_string_returns_401(self, app_no_auth):
        """'Bearer ' with no token must be rejected."""
        resp = app_no_auth.get("/api/v1/users/me", headers={"Authorization": "Bearer "})
        assert resp.status_code == 401

    def test_authenticated_user_can_access_profile(self, app_authed):
        """Sanity: authenticated user gets 200 on /me."""
        resp = app_authed.get("/api/v1/users/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == TEST_USER_ID
        assert data["email"] == "saas@example.com"
        assert data["subscription_tier"] == "pro"


# ══════════════════════════════════════════════════════════
# 2. REPLAY UPLOAD VALIDATION
# ══════════════════════════════════════════════════════════


class TestReplayUploadValidation:
    """HTTP-level replay upload edge cases."""

    def test_upload_requires_auth(self, app_no_auth):
        """Upload endpoint must reject unauthenticated requests."""
        content = _make_valid_replay_content()
        resp = app_no_auth.post(
            "/api/v1/replays/upload",
            files={
                "file": ("test.replay", BytesIO(content), "application/octet-stream")
            },
        )
        assert resp.status_code == 401

    def test_upload_wrong_extension_rejected(self, app_authed):
        """Non-.replay extensions must be rejected with 400."""
        content = _make_valid_replay_content()
        resp = app_authed.post(
            "/api/v1/replays/upload",
            files={"file": ("game.zip", BytesIO(content), "application/zip")},
        )
        assert resp.status_code == 400
        assert "invalid file type" in resp.json()["detail"].lower()

    def test_upload_txt_file_rejected(self, app_authed):
        """.txt extension must be rejected."""
        resp = app_authed.post(
            "/api/v1/replays/upload",
            files={"file": ("notes.txt", BytesIO(b"hello world"), "text/plain")},
        )
        assert resp.status_code == 400

    def test_upload_too_small_rejected(self, app_authed):
        """Files under MIN_REPLAY_SIZE (1000 bytes) must be rejected with 400."""
        tiny = b"A" * 500
        resp = app_authed.post(
            "/api/v1/replays/upload",
            files={"file": ("small.replay", BytesIO(tiny), "application/octet-stream")},
        )
        assert resp.status_code == 400
        assert "small" in resp.json()["detail"].lower()

    def test_upload_invalid_content_rejected(self, app_authed):
        """File that is big enough but lacks TAGame marker must be rejected."""
        # 5000 bytes of random data with no TAGame marker
        bad_content = b"\xab\xcd" * 2500
        assert b"TAGame" not in bad_content

        resp = app_authed.post(
            "/api/v1/replays/upload",
            files={
                "file": (
                    "bad.replay",
                    BytesIO(bad_content),
                    "application/octet-stream",
                )
            },
        )
        assert resp.status_code == 400
        detail = resp.json()["detail"].lower()
        assert "invalid" in detail or "format" in detail

    def test_upload_valid_replay_accepted(self, app_authed, tmp_path, monkeypatch):
        """A valid replay file should be accepted (201/200) and return upload_id."""
        monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
        content = _make_valid_replay_content(5000)

        with patch("rlcoach.worker.tasks.process_replay") as mock_task:
            mock_task.delay = lambda *a, **k: None

            resp = app_authed.post(
                "/api/v1/replays/upload",
                files={
                    "file": (
                        "game.replay",
                        BytesIO(content),
                        "application/octet-stream",
                    )
                },
            )

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "upload_id" in data
        assert data["filename"] == "game.replay"
        assert data["size"] == len(content)
        assert "sha256" in data

    def test_upload_duplicate_returns_existing(self, app_authed, tmp_path, monkeypatch):
        """Uploading the same content twice returns the existing upload record."""
        monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
        content = _make_valid_replay_content(5000)

        with patch("rlcoach.worker.tasks.process_replay") as mock_task:
            mock_task.delay = lambda *a, **k: None
            # First upload
            resp1 = app_authed.post(
                "/api/v1/replays/upload",
                files={
                    "file": (
                        "first.replay",
                        BytesIO(content),
                        "application/octet-stream",
                    )
                },
            )
            assert resp1.status_code == 200
            upload_id_1 = resp1.json()["upload_id"]

            # Second upload with identical bytes
            resp2 = app_authed.post(
                "/api/v1/replays/upload",
                files={
                    "file": (
                        "second.replay",
                        BytesIO(content),
                        "application/octet-stream",
                    )
                },
            )
            assert resp2.status_code == 200
            upload_id_2 = resp2.json()["upload_id"]

        # Both calls should return the same upload record
        assert upload_id_1 == upload_id_2

    def test_upload_list_requires_auth(self, app_no_auth):
        """Listing uploads must require authentication."""
        resp = app_no_auth.get("/api/v1/replays/uploads")
        assert resp.status_code == 401

    def test_upload_list_returns_paginated(self, app_authed):
        """List endpoint returns paginated structure."""
        resp = app_authed.get("/api/v1/replays/uploads")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data

    def test_upload_list_filters_by_status(self, app_authed):
        """Status filter returns only matching records."""
        resp = app_authed.get("/api/v1/replays/uploads?status_filter=pending")
        assert resp.status_code == 200
        data = resp.json()
        for item in data["items"]:
            assert item["status"] == "pending"

    def test_get_nonexistent_upload_returns_404(self, app_authed):
        """Fetching a non-existent upload ID returns 404."""
        resp = app_authed.get(
            "/api/v1/replays/uploads/00000000-0000-0000-0000-000000000000"
        )
        assert resp.status_code == 404

    def test_delete_upload_invalid_uuid_returns_400(self, app_authed):
        """Delete with non-UUID upload_id must return 400."""
        resp = app_authed.delete("/api/v1/replays/uploads/not-a-uuid-at-all")
        assert resp.status_code == 400


# ══════════════════════════════════════════════════════════
# 3. DASHBOARD ENDPOINT WITH REAL DB DATA
# ══════════════════════════════════════════════════════════


class TestDashboardWithData:
    """Dashboard /api/v1/users/me/dashboard returns correct aggregated data."""

    def test_dashboard_no_replays_returns_empty(self, db_setup, monkeypatch):
        """User with zero replays gets empty dashboard (has_data=False)."""
        from rlcoach.api.auth import CurrentUser, get_current_user
        from rlcoach.db.session import create_session
        from rlcoach.db import User

        # Create a brand-new user with no replays
        session = create_session()
        empty_user = User(
            id="empty-user-9999",
            email="empty@example.com",
            subscription_tier="free",
        )
        session.add(empty_user)
        session.commit()
        session.close()

        def _empty_user():
            return CurrentUser(id="empty-user-9999", subscription_tier="free")

        with patch("rlcoach.api.app.get_config", return_value=None):
            from rlcoach.api.app import create_app

            app = create_app()
            app.dependency_overrides[get_current_user] = _empty_user
            client = TestClient(app)
            resp = client.get("/api/v1/users/me/dashboard")

        assert resp.status_code == 200
        data = resp.json()
        assert data["has_data"] is False
        assert data["total_replays"] == 0
        assert data["recent_win_rate"] is None

    def test_dashboard_with_replays_returns_stats(self, app_authed):
        """User with replays gets populated dashboard stats."""
        resp = app_authed.get("/api/v1/users/me/dashboard")
        assert resp.status_code == 200
        data = resp.json()

        assert data["has_data"] is True
        assert data["total_replays"] >= 2
        # Win rate must be a number between 0 and 100
        assert data["recent_win_rate"] is not None
        assert 0.0 <= data["recent_win_rate"] <= 100.0

    def test_dashboard_mechanics_aggregated(self, app_authed):
        """Dashboard includes mechanics data when stats exist."""
        resp = app_authed.get("/api/v1/users/me/dashboard")
        assert resp.status_code == 200
        data = resp.json()

        # We seeded wavedash=4, aerial=3, speedflip=1, halfflip=2
        assert "top_mechanics" in data
        if data["has_data"] and data["top_mechanics"]:
            mechanic_names = [m["name"] for m in data["top_mechanics"]]
            # At least one mechanic should appear
            assert len(mechanic_names) >= 1
            # Each mechanic has a count
            for m in data["top_mechanics"]:
                assert "name" in m
                assert "count" in m
                assert m["count"] >= 0

    def test_dashboard_avg_stats_are_reasonable(self, app_authed):
        """Average goals/assists/saves are non-negative numbers."""
        resp = app_authed.get("/api/v1/users/me/dashboard")
        data = resp.json()
        if data["has_data"]:
            for key in ("avg_goals", "avg_assists", "avg_saves"):
                if data[key] is not None:
                    assert data[key] >= 0.0

    def test_dashboard_trend_is_valid_value(self, app_authed):
        """recent_trend must be one of 'up', 'down', 'stable'."""
        resp = app_authed.get("/api/v1/users/me/dashboard")
        assert resp.json()["recent_trend"] in ("up", "down", "stable")

    def test_dashboard_requires_auth(self, app_no_auth):
        """Dashboard endpoint must reject unauthenticated requests."""
        resp = app_no_auth.get("/api/v1/users/me/dashboard")
        assert resp.status_code == 401


# ══════════════════════════════════════════════════════════
# 4. GDPR DATA EXPORT COMPLETENESS
# ══════════════════════════════════════════════════════════


class TestGDPRExportCompleteness:
    """GDPR Article 20 data portability export."""

    def test_export_returns_all_top_level_keys(self, app_authed):
        """Export must include user, replays, coach_sessions, messages, notes."""
        resp = app_authed.get("/api/v1/users/me/export")
        assert resp.status_code == 200
        data = resp.json()

        required_keys = {
            "user",
            "replays",
            "coach_sessions",
            "coach_messages",
            "coach_notes",
            "exported_at",
        }
        assert required_keys.issubset(set(data.keys()))

    def test_export_user_profile_complete(self, app_authed):
        """User object must have the expected personal data fields."""
        resp = app_authed.get("/api/v1/users/me/export")
        user_data = resp.json()["user"]

        required_user_fields = {
            "id",
            "email",
            "display_name",
            "subscription_tier",
            "created_at",
        }
        assert required_user_fields.issubset(set(user_data.keys()))
        assert user_data["id"] == TEST_USER_ID
        assert user_data["email"] == "saas@example.com"

    def test_export_includes_replays(self, app_authed):
        """Export must include the user's replay references."""
        resp = app_authed.get("/api/v1/users/me/export")
        replays = resp.json()["replays"]

        assert isinstance(replays, list)
        assert len(replays) >= 2  # We seeded 2 replays
        for r in replays:
            assert "replay_id" in r
            assert "ownership_type" in r

    def test_export_includes_coach_messages(self, app_authed):
        """Export must include coach conversation messages."""
        resp = app_authed.get("/api/v1/users/me/export")
        messages = resp.json()["coach_messages"]

        assert isinstance(messages, list)
        assert len(messages) == 2  # We seeded exactly 2 messages
        roles = {m["role"] for m in messages}
        assert "user" in roles
        assert "assistant" in roles

        for msg in messages:
            assert "id" in msg
            assert "session_id" in msg
            assert "role" in msg
            assert "content" in msg

    def test_export_includes_coach_notes(self, app_authed):
        """Export must include coach notes."""
        resp = app_authed.get("/api/v1/users/me/export")
        notes = resp.json()["coach_notes"]

        assert isinstance(notes, list)
        assert len(notes) >= 1
        note = notes[0]
        assert "id" in note
        assert "content" in note
        assert note["content"] == "Work on boost management"

    def test_export_exported_at_is_iso8601(self, app_authed):
        """exported_at timestamp must be a valid ISO 8601 string."""
        resp = app_authed.get("/api/v1/users/me/export")
        ts = resp.json()["exported_at"]
        # Should parse without error
        parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        # Must be recent (within last minute)
        diff = abs((datetime.now(timezone.utc) - parsed).total_seconds())
        assert diff < 60

    def test_export_tos_acceptance_included(self, app_authed):
        """tos_accepted_at is part of the user export."""
        resp = app_authed.get("/api/v1/users/me/export")
        user_data = resp.json()["user"]
        assert "tos_accepted_at" in user_data
        assert user_data["tos_accepted_at"] is not None

    def test_export_requires_auth(self, app_no_auth):
        """Export endpoint must reject unauthenticated requests."""
        resp = app_no_auth.get("/api/v1/users/me/export")
        assert resp.status_code == 401


# ══════════════════════════════════════════════════════════
# 5. USER BOOTSTRAP FLOW
# ══════════════════════════════════════════════════════════


@pytest.fixture
def bootstrap_client(tmp_path, monkeypatch):
    """Test client for bootstrap endpoint (no auth override needed)."""
    monkeypatch.setenv("NEXTAUTH_SECRET", JWT_SECRET)
    monkeypatch.delenv("BOOTSTRAP_SECRET", raising=False)

    from rlcoach.db.session import init_db, reset_engine

    init_db(tmp_path / "bootstrap.db")

    with patch("rlcoach.api.app.get_config", return_value=None):
        from rlcoach.api.app import create_app

        app = create_app()
        client = TestClient(app)
        yield client

    reset_engine()


class TestBootstrapFlow:
    """User bootstrap endpoint integration tests."""

    def _post_bootstrap(self, client, provider, account_id, email=None):
        return client.post(
            "/api/v1/users/bootstrap",
            json={
                "provider": provider,
                "provider_account_id": account_id,
                "email": email,
            },
        )

    def test_bootstrap_creates_new_user(self, bootstrap_client):
        """First-time OAuth sign-in creates a new user in the DB."""
        resp = self._post_bootstrap(
            bootstrap_client, "discord", "discord-new-99", "newbie@example.com"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_new_user"] is True
        assert "id" in data
        assert data["subscription_tier"] == "free"

    def test_bootstrap_returns_existing_user(self, bootstrap_client):
        """Second sign-in with same OAuth account returns existing user."""
        # First sign-in
        resp1 = self._post_bootstrap(
            bootstrap_client, "google", "google-existing-01", "ret@example.com"
        )
        assert resp1.status_code == 200
        user_id_1 = resp1.json()["id"]

        # Second sign-in
        resp2 = self._post_bootstrap(
            bootstrap_client, "google", "google-existing-01", "ret@example.com"
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["is_new_user"] is False
        assert data2["id"] == user_id_1

    def test_bootstrap_invalid_provider_rejected(self, bootstrap_client):
        """Providers not in the allowlist must return 400."""
        resp = self._post_bootstrap(
            bootstrap_client, "twitter", "tw-123", "user@example.com"
        )
        assert resp.status_code == 400
        assert "provider" in resp.json()["detail"].lower()

    def test_bootstrap_with_wrong_signature_rejected(self, tmp_path, monkeypatch):
        """When BOOTSTRAP_SECRET is set, wrong signature must return 401."""
        monkeypatch.setenv("BOOTSTRAP_SECRET", "my-secret-key")
        monkeypatch.setenv("NEXTAUTH_SECRET", JWT_SECRET)

        from rlcoach.db.session import init_db, reset_engine

        init_db(tmp_path / "sig_test.db")

        with patch("rlcoach.api.app.get_config", return_value=None):
            from rlcoach.api.app import create_app

            app = create_app()
            client = TestClient(app)
            resp = client.post(
                "/api/v1/users/bootstrap",
                json={
                    "provider": "discord",
                    "provider_account_id": "disc-sig-1",
                    "email": "sig@example.com",
                },
                headers={"X-Bootstrap-Signature": "wrong-signature"},
            )

        reset_engine()
        assert resp.status_code == 401
        assert "signature" in resp.json()["detail"].lower()

    def test_bootstrap_with_correct_signature_accepted(self, tmp_path, monkeypatch):
        """When BOOTSTRAP_SECRET is set, valid signature must succeed."""
        secret = "my-correct-secret"
        monkeypatch.setenv("BOOTSTRAP_SECRET", secret)
        monkeypatch.setenv("NEXTAUTH_SECRET", JWT_SECRET)

        provider = "google"
        account_id = "google-sig-correct"
        email = "correct@example.com"
        payload = f"{provider}:{account_id}:{email}"
        valid_sig = hmac.new(
            secret.encode(), payload.encode(), hashlib.sha256
        ).hexdigest()

        from rlcoach.db.session import init_db, reset_engine

        init_db(tmp_path / "sig_ok.db")

        with patch("rlcoach.api.app.get_config", return_value=None):
            from rlcoach.api.app import create_app

            app = create_app()
            client = TestClient(app)
            resp = client.post(
                "/api/v1/users/bootstrap",
                json={
                    "provider": provider,
                    "provider_account_id": account_id,
                    "email": email,
                },
                headers={"X-Bootstrap-Signature": valid_sig},
            )

        reset_engine()
        assert resp.status_code == 200
        assert resp.json()["is_new_user"] is True

    def test_bootstrap_links_existing_email(self, bootstrap_client):
        """New OAuth provider with same email links to existing user account."""
        # First, create user via google
        resp1 = self._post_bootstrap(
            bootstrap_client, "google", "g-link-01", "link@example.com"
        )
        assert resp1.status_code == 200
        original_id = resp1.json()["id"]

        # Now sign in via discord with same email
        resp2 = self._post_bootstrap(
            bootstrap_client, "discord", "d-link-01", "link@example.com"
        )
        assert resp2.status_code == 200
        data2 = resp2.json()

        # Should be linked to the same user account
        assert data2["id"] == original_id
        assert data2["is_new_user"] is False

    def test_bootstrap_dev_login_gets_pro(self, bootstrap_client):
        """dev-login provider grants pro subscription for local development."""
        resp = self._post_bootstrap(
            bootstrap_client, "dev-login", "dev-user-local", "dev@localhost"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["subscription_tier"] == "pro"

    def test_bootstrap_missing_provider_account_id_rejected(self, bootstrap_client):
        """Bootstrap request without required fields must fail validation."""
        resp = bootstrap_client.post(
            "/api/v1/users/bootstrap",
            json={"provider": "google"},  # missing provider_account_id
        )
        assert resp.status_code == 422  # Unprocessable Entity


# ══════════════════════════════════════════════════════════
# 6. USER PROFILE & ACCOUNT MANAGEMENT EDGE CASES
# ══════════════════════════════════════════════════════════


class TestUserProfileEdgeCases:
    """Edge cases in user profile and account lifecycle."""

    def test_accept_tos_is_idempotent(self, app_authed):
        """Accepting ToS twice should not overwrite the original timestamp."""
        ts1 = datetime.now(timezone.utc).isoformat()
        resp1 = app_authed.post(
            "/api/v1/users/me/accept-tos", json={"accepted_at": ts1}
        )
        assert resp1.status_code == 200
        accepted_at_1 = resp1.json()["accepted_at"]

        # Accept again with a different timestamp
        import time

        time.sleep(0.01)
        ts2 = datetime.now(timezone.utc).isoformat()
        resp2 = app_authed.post(
            "/api/v1/users/me/accept-tos", json={"accepted_at": ts2}
        )
        assert resp2.status_code == 200
        accepted_at_2 = resp2.json()["accepted_at"]

        # Timestamp must NOT change on second call
        assert accepted_at_1 == accepted_at_2

    def test_delete_request_schedule_and_cancel(self, app_authed):
        """Deletion request can be scheduled and then cancelled."""
        # Schedule deletion
        resp1 = app_authed.post("/api/v1/users/me/delete-request")
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert data1["status"] == "scheduled"
        assert data1["deletion_scheduled_at"] is not None

        # Calling again returns 'already_requested' (idempotent)
        resp2 = app_authed.post("/api/v1/users/me/delete-request")
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "already_requested"

        # Cancel the request
        resp3 = app_authed.delete("/api/v1/users/me/delete-request")
        assert resp3.status_code == 200
        assert resp3.json()["status"] == "cancelled"

    def test_subscription_endpoint_blocks_other_users(self, app_authed):
        """Users must not be able to view other users' subscription info."""
        resp = app_authed.get("/api/v1/users/other-user-999/subscription")
        assert resp.status_code == 403

    def test_trends_invalid_metric_rejected(self, app_authed):
        """Requesting an unknown metric for trends should return 400."""
        resp = app_authed.get("/api/v1/users/me/trends?metric=evil_injection")
        assert resp.status_code == 400

    def test_trends_invalid_period_rejected(self, app_authed):
        """Requesting an invalid period should return 400."""
        resp = app_authed.get("/api/v1/users/me/trends?metric=goals&period=999y")
        assert resp.status_code == 400

    def test_trends_returns_data_for_valid_request(self, app_authed):
        """Trends endpoint returns data structure for a valid request."""
        resp = app_authed.get(
            "/api/v1/users/me/trends?metric=goals&period=30d&axis=time"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "metric" in data
        assert "values" in data
        assert "has_data" in data
        assert data["metric"] == "goals"
