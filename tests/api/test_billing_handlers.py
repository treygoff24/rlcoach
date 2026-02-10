"""Unit tests for billing webhook helper handlers."""

from __future__ import annotations

from datetime import datetime

import pytest

from rlcoach.api.routers.billing import (
    handle_checkout_completed,
    handle_payment_failed,
    handle_subscription_deleted,
    handle_subscription_updated,
)
from rlcoach.db.models import User
from rlcoach.db.session import create_session, init_db, reset_engine


@pytest.fixture
def db_session(tmp_path):
    init_db(tmp_path / "billing.db")
    session = create_session()
    yield session
    session.close()
    reset_engine()


@pytest.mark.asyncio
async def test_handle_checkout_completed_updates_user(db_session):
    user = User(id="u1", email="u@example.com", subscription_tier="free")
    db_session.add(user)
    db_session.commit()

    await handle_checkout_completed(
        db_session,
        {
            "metadata": {"user_id": "u1"},
            "subscription": "sub_123",
            "customer": "cus_123",
        },
    )

    db_session.refresh(user)
    assert user.subscription_tier == "pro"
    assert user.subscription_status == "active"
    assert user.stripe_subscription_id == "sub_123"
    assert user.stripe_customer_id == "cus_123"
    assert user.token_budget_used == 0
    assert isinstance(user.token_budget_reset_at, datetime)


@pytest.mark.asyncio
async def test_handle_checkout_completed_mismatch_customer_is_ignored(db_session):
    user = User(
        id="u2",
        email="u2@example.com",
        subscription_tier="free",
        stripe_customer_id="cus_expected",
    )
    db_session.add(user)
    db_session.commit()

    await handle_checkout_completed(
        db_session,
        {
            "metadata": {"user_id": "u2"},
            "subscription": "sub_999",
            "customer": "cus_other",
        },
    )
    db_session.refresh(user)
    assert user.subscription_tier == "free"
    assert user.stripe_subscription_id is None


@pytest.mark.asyncio
async def test_handle_subscription_updated_paths(db_session):
    user = User(
        id="u3",
        email="u3@example.com",
        subscription_tier="free",
        stripe_customer_id="cus_3",
    )
    db_session.add(user)
    db_session.commit()

    await handle_subscription_updated(
        db_session,
        {
            "metadata": {"user_id": "u3"},
            "customer": "cus_3",
            "status": "active",
            "id": "sub_1",
        },
    )
    db_session.refresh(user)
    assert user.subscription_tier == "pro"
    assert user.subscription_status == "active"

    await handle_subscription_updated(
        db_session,
        {
            "metadata": {"user_id": "u3"},
            "customer": "cus_3",
            "status": "past_due",
            "id": "sub_1",
        },
    )
    db_session.refresh(user)
    assert user.subscription_status == "past_due"

    await handle_subscription_updated(
        db_session,
        {
            "metadata": {"user_id": "u3"},
            "customer": "cus_3",
            "status": "canceled",
            "id": "sub_1",
        },
    )
    db_session.refresh(user)
    assert user.subscription_tier == "free"
    assert user.subscription_status == "canceled"

    await handle_subscription_updated(
        db_session,
        {
            "metadata": {"user_id": "u3"},
            "customer": "cus_3",
            "status": "unpaid",
            "id": "sub_2",
        },
    )
    db_session.refresh(user)
    assert user.subscription_status == "unpaid"
    assert user.stripe_subscription_id == "sub_2"


@pytest.mark.asyncio
async def test_handle_subscription_deleted_and_payment_failed(db_session):
    user = User(
        id="u4",
        email="u4@example.com",
        subscription_tier="pro",
        subscription_status="active",
        stripe_customer_id="cus_4",
        stripe_subscription_id="sub_4",
    )
    db_session.add(user)
    db_session.commit()

    await handle_payment_failed(db_session, {"customer": "cus_4"})
    db_session.refresh(user)
    assert user.subscription_status == "past_due"

    await handle_subscription_deleted(db_session, {"customer": "cus_4"})
    db_session.refresh(user)
    assert user.subscription_tier == "free"
    assert user.subscription_status == "canceled"
    assert user.stripe_subscription_id is None


@pytest.mark.asyncio
async def test_handle_helpers_ignore_missing_user(db_session):
    # Should not raise
    await handle_checkout_completed(
        db_session,
        {"metadata": {"user_id": "missing"}, "customer": "x", "subscription": "s"},
    )
    await handle_subscription_updated(
        db_session, {"metadata": {"user_id": "missing"}, "status": "active"}
    )
    await handle_subscription_deleted(db_session, {"customer": "missing"})
    await handle_payment_failed(db_session, {"customer": "missing"})
