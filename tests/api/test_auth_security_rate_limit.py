"""Unit tests for auth/security/rate-limit helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt
import pytest
from fastapi import HTTPException

from rlcoach.api.auth import (
    CurrentUser,
    decode_token,
    get_current_user,
    get_current_user_optional,
    get_jwt_secret,
    get_token_from_header,
    require_pro,
)
from rlcoach.api.rate_limit import (
    RATE_LIMITS,
    InMemoryRateLimiter,
    RateLimitResult,
    RedisRateLimiter,
    check_rate_limit,
    get_rate_limiter,
    rate_limit_response,
    require_rate_limit,
)
from rlcoach.api.security import (
    sanitize_display_name,
    sanitize_filename,
    sanitize_note_content,
    sanitize_string,
)
from rlcoach.db.models import User
from rlcoach.db.session import create_session, init_db, reset_engine


@pytest.fixture
def db_session(tmp_path):
    init_db(tmp_path / "auth.db")
    session = create_session()
    yield session
    session.close()
    reset_engine()


def test_sanitize_string_and_helpers():
    assert (
        sanitize_string("<b>x</b>\n\t", allow_newlines=False) == "&lt;b&gt;x&lt;/b&gt;"
    )
    assert sanitize_string("a\nb", allow_newlines=True) == "a\nb"
    assert sanitize_string("x  y", preserve_formatting=False) == "x y"
    assert sanitize_display_name("  Alice  ") == "Alice"
    assert sanitize_note_content("line1\nline2") == "line1\nline2"


def test_sanitize_filename_blocks_traversal_and_enforces_extension():
    cleaned = sanitize_filename("../../evil<script>.txt")
    assert cleaned.endswith(".replay")
    assert ".." not in cleaned
    assert "/" not in cleaned

    assert sanitize_filename("") == "unnamed.replay"


def test_get_jwt_secret_missing(monkeypatch):
    monkeypatch.delenv("NEXTAUTH_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="NEXTAUTH_SECRET"):
        get_jwt_secret()


def test_decode_token_success_and_failure(monkeypatch):
    monkeypatch.setenv("NEXTAUTH_SECRET", "test-secret")
    token = jwt.encode(
        {
            "sub": "user-1",
            "email": "u@example.com",
            "subscriptionTier": "pro",
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        },
        "test-secret",
        algorithm="HS256",
    )
    data = decode_token(token)
    assert data.user_id == "user-1"
    assert data.subscription_tier == "pro"

    with pytest.raises(HTTPException) as exc:
        decode_token("not-a-token")
    assert exc.value.status_code == 401


def test_decode_token_expired(monkeypatch):
    monkeypatch.setenv("NEXTAUTH_SECRET", "test-secret")
    token = jwt.encode(
        {
            "sub": "user-1",
            "exp": int((datetime.now(timezone.utc) - timedelta(seconds=1)).timestamp()),
        },
        "test-secret",
        algorithm="HS256",
    )
    with pytest.raises(HTTPException) as exc:
        decode_token(token)
    assert exc.value.status_code == 401
    assert "expired" in exc.value.detail.lower()


def test_get_token_from_header_validation():
    assert get_token_from_header("Bearer abc") == "abc"
    with pytest.raises(HTTPException):
        get_token_from_header(None)
    with pytest.raises(HTTPException):
        get_token_from_header("Basic nope")


@pytest.mark.asyncio
async def test_get_current_user_and_optional(monkeypatch, db_session):
    monkeypatch.setenv("NEXTAUTH_SECRET", "test-secret")
    user = User(id="user-123", email="u@example.com", subscription_tier="pro")
    db_session.add(user)
    db_session.commit()

    token = jwt.encode(
        {
            "sub": "user-123",
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        },
        "test-secret",
        algorithm="HS256",
    )

    current = await get_current_user(token=token, db=db_session)
    assert current.id == "user-123"
    assert current.is_pro is True

    optional = await get_current_user_optional(
        authorization=f"Bearer {token}",
        db=db_session,
    )
    assert optional is not None
    assert optional.id == "user-123"

    assert await get_current_user_optional(authorization=None, db=db_session) is None


@pytest.mark.asyncio
async def test_require_pro_blocks_free_user():
    with pytest.raises(HTTPException) as exc:
        await require_pro(CurrentUser(id="u1", subscription_tier="free", is_pro=False))
    assert exc.value.status_code == 403


def test_in_memory_rate_limiter_enforces_limit():
    limiter = InMemoryRateLimiter()
    endpoint_cfg = RATE_LIMITS["default"]
    for _ in range(endpoint_cfg["requests"]):
        result = limiter.check("u1", "default", endpoint_cfg["requests"], 60)
        assert result.allowed is True
    denied = limiter.check("u1", "default", endpoint_cfg["requests"], 60)
    assert denied.allowed is False
    assert denied.remaining == 0


def test_redis_rate_limiter_fail_open():
    class BrokenRedis:
        def pipeline(self):
            raise RuntimeError("redis down")

    limiter = RedisRateLimiter(BrokenRedis())
    result = limiter.check("u1", "upload", limit=10, window_seconds=60)
    assert result.allowed is True
    assert result.remaining == 10


def test_get_rate_limiter_and_check_rate_limit(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setattr("rlcoach.api.rate_limit._rate_limiter", None)
    limiter = get_rate_limiter()
    assert isinstance(limiter, InMemoryRateLimiter)
    result = check_rate_limit("u2", "default")
    assert result.allowed is True


def test_rate_limit_http_response_headers():
    result = RateLimitResult(
        allowed=False, remaining=0, reset_at=9999999999.0, limit=10
    )
    exc = rate_limit_response(result)
    assert isinstance(exc, HTTPException)
    assert exc.status_code == 429
    assert "Retry-After" in exc.headers


@pytest.mark.asyncio
async def test_require_rate_limit_decorator(monkeypatch):
    @require_rate_limit("upload")
    async def handler(*, user):
        return {"ok": True}

    monkeypatch.setattr(
        "rlcoach.api.rate_limit.check_rate_limit",
        lambda _uid, _ep: RateLimitResult(True, remaining=1, reset_at=0, limit=10),
    )
    assert await handler(user=SimpleNamespace(id="u1")) == {"ok": True}

    monkeypatch.setattr(
        "rlcoach.api.rate_limit.check_rate_limit",
        lambda _uid, _ep: RateLimitResult(False, remaining=0, reset_at=10, limit=10),
    )
    with pytest.raises(HTTPException):
        await handler(user=SimpleNamespace(id="u1"))
