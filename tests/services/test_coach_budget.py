"""Tests for coach token budget utilities."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from rlcoach.db.models import CoachSession, CoachTokenReservation, User
from rlcoach.db.session import create_session, init_db, reset_engine
from rlcoach.services.coach.budget import (
    MONTHLY_TOKEN_BUDGET,
    BudgetStatus,
    _maybe_reset_budget,
    abort_reservation,
    check_budget,
    estimate_request_tokens,
    finalize_reservation,
    get_budget_status,
    get_token_budget_remaining,
    release_expired_reservations,
    reserve_tokens,
    update_budget,
)


@pytest.fixture
def db_session(tmp_path):
    init_db(tmp_path / "budget.db")
    session = create_session()
    yield session
    session.close()
    reset_engine()


def _user(**kwargs) -> User:
    defaults = {
        "id": "user-1",
        "email": "u@example.com",
        "subscription_tier": "pro",
        "token_budget_used": 0,
        "token_budget_reset_at": datetime.now(timezone.utc),
    }
    defaults.update(kwargs)
    return User(**defaults)


def test_budget_remaining_and_status_warning_exhausted():
    user = _user(token_budget_used=MONTHLY_TOKEN_BUDGET - 10)
    assert get_token_budget_remaining(user) == 10

    status = get_budget_status(user)
    assert isinstance(status, BudgetStatus)
    assert status.warning is True
    assert status.exhausted is False
    assert status.to_dict()["remaining"] == 10

    exhausted = _user(token_budget_used=MONTHLY_TOKEN_BUDGET)
    exhausted_status = get_budget_status(exhausted)
    assert exhausted_status.exhausted is True


def test_check_budget_messages():
    exhausted = _user(token_budget_used=MONTHLY_TOKEN_BUDGET)
    ok, message = check_budget(exhausted, estimated_tokens=1)
    assert ok is False
    assert "exhausted" in (message or "").lower()

    limited = _user(token_budget_used=MONTHLY_TOKEN_BUDGET - 20)
    ok, message = check_budget(limited, estimated_tokens=50)
    assert ok is False
    assert "exceed budget" in (message or "").lower()

    ok, message = check_budget(limited, estimated_tokens=10)
    assert ok is True
    assert message is None


def test_update_budget_and_reset_logic(db_session):
    user = _user(
        token_budget_used=100,
        token_budget_reset_at=datetime.now(timezone.utc) - timedelta(days=40),
    )
    db_session.add(user)
    db_session.commit()

    status = update_budget(user, tokens_used=25, db=db_session)
    assert status.used == 25
    assert status.remaining == MONTHLY_TOKEN_BUDGET - 25

    # First-time setup path
    user2 = _user(
        id="user-2",
        email="u2@example.com",
        token_budget_used=999,
        token_budget_reset_at=datetime.now(timezone.utc),
    )
    db_session.add(user2)
    db_session.commit()
    user2.token_budget_reset_at = None
    user2.token_budget_used = 999
    assert _maybe_reset_budget(user2, db_session, commit=False) is True
    assert user2.token_budget_used == 0


def test_reservation_lifecycle(db_session):
    user = _user(id="user-3", token_budget_used=0)
    session = CoachSession(id="session-1", user_id="user-3")
    db_session.add_all([user, session])
    db_session.commit()

    reservation_id = reserve_tokens(
        user=user,
        session_id="session-1",
        estimated_tokens=300,
        db=db_session,
    )
    db_session.refresh(user)
    assert user.token_budget_used == 300

    finalize_reservation(user, reservation_id, tokens_used=250, db=db_session)
    db_session.refresh(user)
    assert user.token_budget_used == 250
    assert (
        db_session.query(CoachTokenReservation)
        .filter(CoachTokenReservation.id == reservation_id)
        .count()
        == 0
    )


def test_abort_and_release_expired_reservations(db_session):
    user = _user(id="user-4", token_budget_used=0)
    session = CoachSession(id="session-2", user_id="user-4")
    db_session.add_all([user, session])
    db_session.commit()

    reservation_id = reserve_tokens(
        user=user,
        session_id="session-2",
        estimated_tokens=500,
        db=db_session,
    )
    db_session.refresh(user)
    assert user.token_budget_used == 500

    abort_reservation(user=user, reservation_id=reservation_id, db=db_session)
    db_session.refresh(user)
    assert user.token_budget_used == 0

    reservation_id_2 = reserve_tokens(
        user=user,
        session_id="session-2",
        estimated_tokens=200,
        db=db_session,
    )
    reservation = (
        db_session.query(CoachTokenReservation)
        .filter(CoachTokenReservation.id == reservation_id_2)
        .one()
    )
    reservation.expires_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    db_session.commit()

    released = release_expired_reservations(user=user, db=db_session)
    assert released == 1
    db_session.refresh(user)
    assert user.token_budget_used == 0


def test_estimate_request_tokens():
    base = estimate_request_tokens(400, history_messages=0, include_tools=False)
    with_tools = estimate_request_tokens(
        400,
        history_messages=3,
        include_tools=True,
        tool_result_count=2,
    )
    assert base > 0
    assert with_tools > base
