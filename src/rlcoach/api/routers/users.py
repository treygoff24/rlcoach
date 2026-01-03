# src/rlcoach/api/routers/users.py
"""User API endpoints.

Provides endpoints for user profile, subscription management,
and user-specific data.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from ...db import User, get_session
from ..auth import AuthenticatedUser

router = APIRouter(prefix="/api/v1/users", tags=["users"])


class UserProfile(BaseModel):
    """User profile response."""

    id: str
    email: str | None
    name: str | None
    image: str | None
    subscription_tier: str
    subscription_status: str | None
    token_budget_remaining: int
    created_at: str
    last_login_at: str | None


class SubscriptionInfo(BaseModel):
    """Subscription status response."""

    tier: str
    status: str | None
    current_period_end: str | None
    token_budget_remaining: int
    cancel_at_period_end: bool


class UpdateProfileRequest(BaseModel):
    """Update profile request."""

    name: str | None = None


@router.get("/me", response_model=UserProfile)
async def get_current_profile(
    user: AuthenticatedUser,
    db: Annotated[DBSession, Depends(get_session)],
) -> UserProfile:
    """Get the current user's profile.

    Requires authentication.
    """
    db_user = db.query(User).filter(User.id == user.id).first()
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return UserProfile(
        id=db_user.id,
        email=db_user.email,
        name=db_user.name,
        image=db_user.image,
        subscription_tier=db_user.subscription_tier.value,
        subscription_status=(
            db_user.subscription_status.value if db_user.subscription_status else None
        ),
        token_budget_remaining=db_user.token_budget_remaining,
        created_at=db_user.created_at.isoformat(),
        last_login_at=(
            db_user.last_login_at.isoformat() if db_user.last_login_at else None
        ),
    )


@router.patch("/me", response_model=UserProfile)
async def update_profile(
    user: AuthenticatedUser,
    update: UpdateProfileRequest,
    db: Annotated[DBSession, Depends(get_session)],
) -> UserProfile:
    """Update the current user's profile.

    Requires authentication.
    """
    db_user = db.query(User).filter(User.id == user.id).first()
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if update.name is not None:
        db_user.name = update.name

    db_user.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(db_user)

    return UserProfile(
        id=db_user.id,
        email=db_user.email,
        name=db_user.name,
        image=db_user.image,
        subscription_tier=db_user.subscription_tier.value,
        subscription_status=(
            db_user.subscription_status.value if db_user.subscription_status else None
        ),
        token_budget_remaining=db_user.token_budget_remaining,
        created_at=db_user.created_at.isoformat(),
        last_login_at=(
            db_user.last_login_at.isoformat() if db_user.last_login_at else None
        ),
    )


@router.get("/{user_id}/subscription", response_model=SubscriptionInfo)
async def get_subscription(
    user_id: str,
    user: AuthenticatedUser,
    db: Annotated[DBSession, Depends(get_session)],
) -> SubscriptionInfo:
    """Get subscription info for a user.

    Users can only access their own subscription info.
    """
    if user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot access other user's subscription",
        )

    db_user = db.query(User).filter(User.id == user_id).first()
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    sub_status = None
    if db_user.subscription_status:
        sub_status = db_user.subscription_status.value

    return SubscriptionInfo(
        tier=db_user.subscription_tier.value,
        status=sub_status,
        current_period_end=(
            db_user.stripe_current_period_end.isoformat()
            if db_user.stripe_current_period_end
            else None
        ),
        token_budget_remaining=db_user.token_budget_remaining,
        cancel_at_period_end=False,  # Would be set by Stripe webhook
    )


@router.delete("/me")
async def delete_account(
    user: AuthenticatedUser,
    db: Annotated[DBSession, Depends(get_session)],
) -> dict:
    """Delete the current user's account.

    This anonymizes user data as per GDPR requirements.
    Replay data is preserved for aggregate statistics.
    """
    db_user = db.query(User).filter(User.id == user.id).first()
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Anonymize user data (GDPR-compliant deletion)
    db_user.email = None
    db_user.name = f"Deleted User {db_user.id[:8]}"
    db_user.image = None
    db_user.email_verified = None
    db_user.stripe_customer_id = None
    db_user.stripe_subscription_id = None
    db_user.updated_at = datetime.now(timezone.utc)

    db.commit()

    return {"status": "deleted", "message": "Account data has been anonymized"}
