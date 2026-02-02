# tests/api/test_coach_budget_reservations.py
"""Tests for coach token reservation helpers."""

from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture
def db_session(tmp_path):
    from rlcoach.db.session import create_session, init_db, reset_engine

    init_db(tmp_path / "rlcoach.db")
    session = create_session()
    yield session
    session.close()
    reset_engine()


def test_reservation_expires_and_releases_budget(db_session):
    from rlcoach.db.models import CoachSession, CoachTokenReservation, User
    from rlcoach.services.coach.budget import (
        release_expired_reservations,
        reserve_tokens,
    )

    user = User(
        id="user-1",
        email="test@example.com",
        subscription_tier="pro",
        token_budget_used=0,
        token_budget_reset_at=datetime.now(timezone.utc),
    )
    session = CoachSession(id="session-1", user_id="user-1")

    db_session.add_all([user, session])
    db_session.commit()

    reservation_id = reserve_tokens(
        user=user,
        session_id="session-1",
        estimated_tokens=500,
        db=db_session,
    )
    db_session.refresh(user)
    assert user.token_budget_used == 500

    reservation = (
        db_session.query(CoachTokenReservation)
        .filter(CoachTokenReservation.id == reservation_id)
        .one()
    )
    reservation.expires_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    db_session.commit()

    released = release_expired_reservations(user=user, db=db_session)
    db_session.refresh(user)

    assert released == 1
    assert user.token_budget_used == 0
    assert (
        db_session.query(CoachTokenReservation)
        .filter(CoachTokenReservation.id == reservation_id)
        .count()
        == 0
    )
