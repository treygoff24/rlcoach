"""Behavioral coverage for security-sensitive SaaS boundaries."""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def database(tmp_path):
    from rlcoach.db.session import create_session, init_db, reset_engine

    init_db(tmp_path / "saas-boundaries.db")
    session = create_session()
    yield session
    session.close()
    reset_engine()


def test_stripe_webhook_verifies_raw_body_and_closes_failed_dispatch(monkeypatch):
    from rlcoach.api.routers import billing

    app = FastAPI()
    app.include_router(billing.webhook_router)
    client = TestClient(app)
    raw_body = b'{"type":"checkout.session.completed"}'
    seen = {}

    def reject_signature(payload, signature, secret):
        seen.update(payload=payload, signature=signature, secret=secret)
        raise ValueError("bad payload")

    monkeypatch.setattr(billing, "STRIPE_WEBHOOK_SECRET", "webhook-secret")
    monkeypatch.setattr(billing.stripe.Webhook, "construct_event", reject_signature)

    response = client.post(
        "/stripe/webhook",
        content=raw_body,
        headers={"stripe-signature": "bad-signature"},
    )
    assert response.status_code == 400
    assert seen == {
        "payload": raw_body,
        "signature": "bad-signature",
        "secret": "webhook-secret",
    }

    fake_session = SimpleNamespace(closed=False)
    fake_session.close = lambda: setattr(fake_session, "closed", True)
    monkeypatch.setattr(billing, "create_session", lambda: fake_session)
    monkeypatch.setattr(
        billing.stripe.Webhook,
        "construct_event",
        lambda *_args: {
            "type": "checkout.session.completed",
            "data": {"object": {"id": "cs_test"}},
        },
    )
    monkeypatch.setattr(
        billing,
        "handle_checkout_completed",
        AsyncMock(side_effect=RuntimeError("handler failed")),
    )

    with pytest.raises(RuntimeError, match="handler failed"):
        client.post(
            "/stripe/webhook",
            content=raw_body,
            headers={"stripe-signature": "valid-signature"},
        )
    assert fake_session.closed is True


def test_oauth_bootstrap_creates_once_and_links_matching_email(database, monkeypatch):
    from rlcoach.api.routers import users
    from rlcoach.db.models import OAuthAccount, User

    monkeypatch.setenv("BOOTSTRAP_SECRET", "bootstrap-secret")
    app = FastAPI()
    app.include_router(users.router)
    client = TestClient(app)

    def signed_post(provider, provider_id):
        payload = {
            "provider": provider,
            "provider_account_id": provider_id,
            "email": "same@example.com",
            "name": "Same Person",
        }
        signed = f"{provider}:{provider_id}:same@example.com"
        signature = hmac.new(
            b"bootstrap-secret", signed.encode(), hashlib.sha256
        ).hexdigest()
        return client.post(
            "/api/v1/users/bootstrap",
            json=payload,
            headers={"x-bootstrap-signature": signature},
        )

    first = signed_post("discord", "discord-1")
    retry = signed_post("discord", "discord-1")
    linked = signed_post("google", "google-1")

    assert first.status_code == retry.status_code == linked.status_code == 200
    assert first.json()["is_new_user"] is True
    assert retry.json() == {**first.json(), "is_new_user": False}
    assert linked.json()["id"] == first.json()["id"]
    assert database.query(User).count() == 1
    assert database.query(OAuthAccount).count() == 2

    jwt_secret = "nextauth-test-secret-at-least-32-bytes"
    monkeypatch.setenv("NEXTAUTH_SECRET", jwt_secret)
    access_token = jwt.encode(
        {"userId": first.json()["id"], "email": "same@example.com"},
        jwt_secret,
        algorithm="HS256",
    )
    profile = client.get(
        "/api/v1/users/me", headers={"authorization": f"Bearer {access_token}"}
    )
    assert profile.status_code == 200
    assert profile.json()["id"] == first.json()["id"]


def test_gdpr_submit_and_status_use_real_affected_record_lookup(database, monkeypatch):
    from rlcoach.api.routers import gdpr
    from rlcoach.db.models import Player, PlayerGameStats, Replay

    gdpr._removal_requests.clear()
    monkeypatch.setattr(
        gdpr, "check_rate_limit", lambda *_args: SimpleNamespace(allowed=True)
    )
    player_id = "steam:76561198012345678"
    database.add(Player(player_id=player_id, display_name="Affected"))
    database.add(
        Replay(
            replay_id="replay-1",
            source_file="one.replay",
            file_hash="hash-1",
            played_at_utc=datetime.now(timezone.utc),
            play_date=datetime.now(timezone.utc).date(),
            map="DFH",
            playlist="DOUBLES",
            team_size=2,
            duration_seconds=300,
        )
    )
    database.add(
        PlayerGameStats(replay_id="replay-1", player_id=player_id, team="BLUE")
    )
    database.commit()

    app = FastAPI()
    app.include_router(gdpr.router)
    client = TestClient(app)
    submitted = client.post(
        "/api/v1/gdpr/removal-request",
        json={
            "player_identifier": "76561198012345678",
            "identifier_type": "steam_id",
            "email": "owner@example.com",
        },
    )

    assert submitted.status_code == 200
    request_id = submitted.json()["request_id"]
    assert gdpr._removal_requests[request_id]["affected_count"] == 1
    status = client.get(f"/api/v1/gdpr/removal-request/{request_id}")
    assert status.status_code == 200
    assert status.json()["status"] == "pending"


def test_cross_user_replay_delete_is_404_and_preserves_file(
    database, monkeypatch, tmp_path
):
    from rlcoach.api.auth import CurrentUser, get_current_user
    from rlcoach.api.routers import replays
    from rlcoach.db.models import UploadedReplay, User

    owner_id = "00000000-0000-0000-0000-000000000001"
    other_id = "00000000-0000-0000-0000-000000000002"
    upload_id = "00000000-0000-0000-0000-000000000003"
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    replay_file = upload_dir / "private.replay"
    replay_file.write_bytes(b"private replay")
    database.add_all(
        [
            User(id=owner_id, email="owner@example.com"),
            User(id=other_id, email="other@example.com"),
            UploadedReplay(
                id=upload_id,
                user_id=owner_id,
                filename=replay_file.name,
                file_hash="private-hash",
                file_size_bytes=replay_file.stat().st_size,
                storage_path=str(replay_file),
            ),
        ]
    )
    database.commit()
    monkeypatch.setenv("UPLOAD_DIR", str(upload_dir))

    app = FastAPI()
    app.include_router(replays.router)
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=other_id, email="other@example.com"
    )
    response = TestClient(app).delete(f"/api/v1/replays/uploads/{upload_id}")

    assert response.status_code == 404
    assert replay_file.read_bytes() == b"private replay"
    assert database.get(UploadedReplay, upload_id) is not None


def test_coach_abort_is_idempotent_and_cannot_release_another_users_reservation(
    database,
):
    from rlcoach.api.auth import CurrentUser, get_current_user
    from rlcoach.api.routers import coach
    from rlcoach.db.models import CoachSession, CoachTokenReservation, User
    from rlcoach.services.coach.budget import reserve_tokens

    now = datetime.now(timezone.utc)
    user = User(id="user-1", token_budget_used=0, token_budget_reset_at=now)
    other = User(id="user-2", token_budget_used=0, token_budget_reset_at=now)
    own_session = CoachSession(id="session-1", user_id=user.id)
    other_session = CoachSession(id="session-2", user_id=other.id)
    database.add_all([user, other, own_session, other_session])
    database.commit()
    own_reservation = reserve_tokens(user, own_session.id, 500, database)
    other_reservation = reserve_tokens(other, other_session.id, 700, database)

    app = FastAPI()
    app.include_router(coach.router)
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=user.id, subscription_tier="pro", is_pro=True
    )
    client = TestClient(app)
    payload = {"session_id": own_session.id, "reservation_id": own_reservation}

    assert client.post("/api/v1/coach/chat/abort", json=payload).status_code == 200
    assert client.post("/api/v1/coach/chat/abort", json=payload).status_code == 200
    database.refresh(user)
    assert user.token_budget_used == 0

    wrong_owner = {
        "session_id": own_session.id,
        "reservation_id": other_reservation,
    }
    assert client.post("/api/v1/coach/chat/abort", json=wrong_owner).status_code == 200
    database.refresh(other)
    assert other.token_budget_used == 700
    assert database.get(CoachTokenReservation, other_reservation) is not None


@pytest.mark.parametrize(
    ("saas_mode", "environment"),
    [("true", "development"), ("false", "production")],
)
def test_unauthenticated_local_routers_are_excluded_from_saas_and_production(
    monkeypatch, saas_mode, environment
):
    from rlcoach.api.app import create_app

    monkeypatch.setenv("SAAS_MODE", saas_mode)
    monkeypatch.setenv("ENVIRONMENT", environment)
    paths = {route.path for route in create_app().routes}

    assert paths.isdisjoint({"/dashboard", "/games", "/players", "/trends"})
