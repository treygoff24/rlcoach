# src/rlcoach/api/routers/users.py
"""User API endpoints.

Provides endpoints for user profile, subscription management,
and user-specific data.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session as DBSession

from ...data.benchmarks import (
    RANK_DISPLAY_NAMES,
    compare_to_benchmark,
    get_benchmark_for_rank,
)
from ...db import User, get_session
from ...db.models import (
    CoachMessage,
    CoachNote,
    CoachSession,
    OAuthAccount,
    PlayerGameStats,
    Replay,
    UserReplay,
)
from ...services.coach.budget import get_token_budget_remaining
from ..auth import AuthenticatedUser
from ..rate_limit import check_rate_limit, rate_limit_response
from ..security import sanitize_display_name

logger = logging.getLogger(__name__)

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


class AcceptTosRequest(BaseModel):
    """ToS acceptance request."""

    accepted_at: str  # ISO 8601 timestamp from client


class AcceptTosResponse(BaseModel):
    """ToS acceptance response."""

    accepted: bool
    accepted_at: str


class BootstrapRequest(BaseModel):
    """User bootstrap request from NextAuth signIn callback."""

    provider: str  # discord, google, steam
    provider_account_id: str  # OAuth provider's user ID
    email: str | None = None
    name: str | None = None
    image: str | None = None


class BootstrapResponse(BaseModel):
    """User bootstrap response."""

    id: str  # Our database UUID
    subscription_tier: str
    is_new_user: bool


ALLOWED_PROVIDERS = {"discord", "google", "steam", "epic", "dev-login"}


def _verify_bootstrap_signature(
    request: BootstrapRequest, signature: str | None
) -> bool:
    """Verify HMAC signature for bootstrap request.

    Prevents abuse of the unauthenticated bootstrap endpoint.
    The signature is computed by the frontend using a shared secret.
    """
    secret = os.getenv("BOOTSTRAP_SECRET")
    if not secret:
        # In development without secret, allow but log warning
        logger.warning("BOOTSTRAP_SECRET not set - bootstrap requests unverified")
        return True

    if not signature:
        return False

    # Compute expected signature
    payload = f"{request.provider}:{request.provider_account_id}:{request.email or ''}"
    expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()

    return hmac.compare_digest(expected, signature)


@router.post("/bootstrap", response_model=BootstrapResponse)
async def bootstrap_user(
    request: BootstrapRequest,
    db: Annotated[DBSession, Depends(get_session)],
    x_bootstrap_signature: Annotated[str | None, Header()] = None,
) -> BootstrapResponse:
    """Bootstrap a user on OAuth sign-in.

    Called by NextAuth signIn callback to ensure user exists in our database.
    Creates user and OAuth account if this is a new sign-up.
    Returns existing user if they've signed in before.

    Security: Requires HMAC signature verification via X-Bootstrap-Signature header.
    """
    # Validate provider is in allowlist
    if request.provider not in ALLOWED_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid provider. Allowed: {', '.join(ALLOWED_PROVIDERS)}",
        )

    # Verify signature (prevents abuse of unauthenticated endpoint)
    if not _verify_bootstrap_signature(request, x_bootstrap_signature):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing bootstrap signature",
        )
    # Check if this OAuth account already exists
    existing_account = (
        db.query(OAuthAccount)
        .filter(
            OAuthAccount.provider == request.provider,
            OAuthAccount.provider_account_id == request.provider_account_id,
        )
        .first()
    )

    if existing_account:
        # User exists - return their info
        user = db.query(User).filter(User.id == existing_account.user_id).first()
        if user:
            return BootstrapResponse(
                id=user.id,
                subscription_tier=user.subscription_tier or "free",
                is_new_user=False,
            )

    # Check if email already belongs to another user (account linking scenario)
    existing_user = None
    if request.email:
        existing_user = db.query(User).filter(User.email == request.email).first()

    if existing_user:
        # Link this OAuth account to existing user
        oauth_account = OAuthAccount(
            user_id=existing_user.id,
            type="oauth",
            provider=request.provider,
            provider_account_id=request.provider_account_id,
        )
        db.add(oauth_account)
        db.commit()

        return BootstrapResponse(
            id=existing_user.id,
            subscription_tier=existing_user.subscription_tier or "free",
            is_new_user=False,
        )

    # Create new user
    new_user = User(
        email=request.email,
        display_name=sanitize_display_name(request.name) if request.name else None,
        image=request.image,
        subscription_tier="free",
        token_budget_used=0,
        token_budget_reset_at=datetime.now(timezone.utc),
    )
    db.add(new_user)
    db.flush()  # Get the generated ID

    # Create OAuth account link
    oauth_account = OAuthAccount(
        user_id=new_user.id,
        type="oauth",
        provider=request.provider,
        provider_account_id=request.provider_account_id,
    )
    db.add(oauth_account)
    db.commit()
    db.refresh(new_user)

    return BootstrapResponse(
        id=new_user.id,
        subscription_tier=new_user.subscription_tier or "free",
        is_new_user=True,
    )


@router.post("/me/accept-tos", response_model=AcceptTosResponse)
async def accept_terms_of_service(
    request: AcceptTosRequest,
    user: AuthenticatedUser,
    db: Annotated[DBSession, Depends(get_session)],
) -> AcceptTosResponse:
    """Record Terms of Service acceptance.

    Called after OAuth sign-in to record ToS acceptance timestamp.
    Requires authentication.
    """
    db_user = db.query(User).filter(User.id == user.id).first()
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Don't overwrite existing acceptance (idempotent, but don't backdate)
    if db_user.tos_accepted_at is None:
        # Parse the client-provided timestamp
        try:
            accepted_at = datetime.fromisoformat(
                request.accepted_at.replace("Z", "+00:00")
            )
        except ValueError:
            accepted_at = datetime.now(timezone.utc)

        db_user.tos_accepted_at = accepted_at
        db_user.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(db_user)

    return AcceptTosResponse(
        accepted=True,
        accepted_at=(
            db_user.tos_accepted_at.isoformat() if db_user.tos_accepted_at else ""
        ),
    )


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
        name=db_user.display_name,
        image=db_user.image,
        subscription_tier=db_user.subscription_tier,
        subscription_status=db_user.subscription_status,
        token_budget_remaining=get_token_budget_remaining(db_user),
        created_at=db_user.created_at.isoformat(),
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
        db_user.display_name = sanitize_display_name(update.name)

    db_user.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(db_user)

    return UserProfile(
        id=db_user.id,
        email=db_user.email,
        name=db_user.display_name,
        image=db_user.image,
        subscription_tier=db_user.subscription_tier,
        subscription_status=db_user.subscription_status,
        token_budget_remaining=get_token_budget_remaining(db_user),
        created_at=db_user.created_at.isoformat(),
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

    return SubscriptionInfo(
        tier=db_user.subscription_tier,
        status=db_user.subscription_status,
        current_period_end=(
            db_user.subscription_period_end.isoformat()
            if db_user.subscription_period_end
            else None
        ),
        token_budget_remaining=get_token_budget_remaining(db_user),
        cancel_at_period_end=False,  # Would be set by Stripe webhook
    )


class DeletionRequestResponse(BaseModel):
    """Account deletion request response."""

    status: str
    deletion_scheduled_at: str | None
    message: str


@router.post("/me/delete-request", response_model=DeletionRequestResponse)
async def request_account_deletion(
    user: AuthenticatedUser,
    db: Annotated[DBSession, Depends(get_session)],
) -> DeletionRequestResponse:
    """Request account deletion with 30-day grace period.

    Sets deletion_requested_at timestamp. Account will be deleted
    30 days from now unless cancelled.
    """
    db_user = db.query(User).filter(User.id == user.id).first()
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Check if already requested
    if db_user.deletion_requested_at:
        from datetime import timedelta

        scheduled_at = db_user.deletion_requested_at + timedelta(days=30)
        return DeletionRequestResponse(
            status="already_requested",
            deletion_scheduled_at=scheduled_at.isoformat(),
            message="Account deletion already scheduled",
        )

    # Set deletion request timestamp
    db_user.deletion_requested_at = datetime.now(timezone.utc)
    db_user.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(db_user)

    from datetime import timedelta

    scheduled_at = db_user.deletion_requested_at + timedelta(days=30)

    return DeletionRequestResponse(
        status="scheduled",
        deletion_scheduled_at=scheduled_at.isoformat(),
        message="Account deletion scheduled. You can cancel within 30 days.",
    )


@router.delete("/me/delete-request", response_model=DeletionRequestResponse)
async def cancel_account_deletion(
    user: AuthenticatedUser,
    db: Annotated[DBSession, Depends(get_session)],
) -> DeletionRequestResponse:
    """Cancel a pending account deletion request.

    Clears deletion_requested_at if within grace period.
    """
    db_user = db.query(User).filter(User.id == user.id).first()
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if not db_user.deletion_requested_at:
        return DeletionRequestResponse(
            status="no_request",
            deletion_scheduled_at=None,
            message="No deletion request to cancel",
        )

    # Clear deletion request
    db_user.deletion_requested_at = None
    db_user.updated_at = datetime.now(timezone.utc)
    db.commit()

    return DeletionRequestResponse(
        status="cancelled",
        deletion_scheduled_at=None,
        message="Account deletion cancelled",
    )


@router.delete("/me")
async def delete_account(
    user: AuthenticatedUser,
    db: Annotated[DBSession, Depends(get_session)],
) -> dict:
    """Immediately delete the current user's account.

    This anonymizes user data as per GDPR requirements.
    Replay data is preserved for aggregate statistics.
    Note: Prefer POST /me/delete-request for 30-day grace period.
    """
    db_user = db.query(User).filter(User.id == user.id).first()
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Anonymize user data (GDPR-compliant deletion)
    db_user.email = None
    db_user.display_name = f"Deleted User {db_user.id[:8]}"
    db_user.image = None
    db_user.email_verified = None
    db_user.stripe_customer_id = None
    db_user.stripe_subscription_id = None
    db_user.deletion_requested_at = None  # Clear since we're deleting now
    db_user.updated_at = datetime.now(timezone.utc)

    # Also delete coach sessions and messages
    coach_sessions = (
        db.query(CoachSession).filter(CoachSession.user_id == user.id).all()
    )
    session_ids = [s.id for s in coach_sessions]
    if session_ids:
        db.query(CoachMessage).filter(CoachMessage.session_id.in_(session_ids)).delete(
            synchronize_session=False
        )
    db.query(CoachSession).filter(CoachSession.user_id == user.id).delete()
    db.query(CoachNote).filter(CoachNote.user_id == user.id).delete()

    db.commit()

    return {"status": "deleted", "message": "Account data has been anonymized"}


class MechanicStat(BaseModel):
    """Individual mechanic statistic."""

    name: str
    count: int


class DashboardStatsResponse(BaseModel):
    """Dashboard statistics response."""

    total_replays: int
    recent_win_rate: float | None
    avg_goals: float | None
    avg_assists: float | None
    avg_saves: float | None
    avg_shots: float | None
    top_mechanics: list[MechanicStat]
    recent_trend: str  # "up", "down", "stable"
    has_data: bool


@router.get("/me/dashboard", response_model=DashboardStatsResponse)
async def get_dashboard_stats(
    user: AuthenticatedUser,
    db: Annotated[DBSession, Depends(get_session)],
) -> DashboardStatsResponse:
    """Get dashboard statistics for the authenticated user.

    Returns aggregated stats from the user's replays.
    """
    # Get user's replay IDs
    user_replay_ids = (
        db.query(UserReplay.replay_id).filter(UserReplay.user_id == user.id).subquery()
    )

    # Count total replays
    total_replays = (
        db.query(func.count(Replay.replay_id))
        .filter(Replay.replay_id.in_(user_replay_ids))
        .scalar()
        or 0
    )

    if total_replays == 0:
        return DashboardStatsResponse(
            total_replays=0,
            recent_win_rate=None,
            avg_goals=None,
            avg_assists=None,
            avg_saves=None,
            avg_shots=None,
            top_mechanics=[],
            recent_trend="stable",
            has_data=False,
        )

    # Get recent replays for win rate (last 20)
    recent_replays = (
        db.query(Replay.result)
        .filter(Replay.replay_id.in_(user_replay_ids))
        .order_by(Replay.played_at_utc.desc())
        .limit(20)
        .all()
    )

    wins = sum(1 for r in recent_replays if r.result == "WIN")
    recent_win_rate = (wins / len(recent_replays) * 100) if recent_replays else None

    # Get player stats for user's games (where is_me = True)
    stats_query = (
        db.query(
            func.avg(PlayerGameStats.goals).label("avg_goals"),
            func.avg(PlayerGameStats.assists).label("avg_assists"),
            func.avg(PlayerGameStats.saves).label("avg_saves"),
            func.avg(PlayerGameStats.shots).label("avg_shots"),
            func.sum(PlayerGameStats.wavedash_count).label("total_wavedash"),
            func.sum(PlayerGameStats.halfflip_count).label("total_halfflip"),
            func.sum(PlayerGameStats.speedflip_count).label("total_speedflip"),
            func.sum(PlayerGameStats.aerial_count).label("total_aerial"),
            func.sum(PlayerGameStats.flip_cancel_count).label("total_flip_cancel"),
        )
        .filter(
            PlayerGameStats.replay_id.in_(user_replay_ids),
            PlayerGameStats.is_me == True,  # noqa: E712
        )
        .first()
    )

    avg_goals = float(stats_query.avg_goals) if stats_query.avg_goals else None
    avg_assists = float(stats_query.avg_assists) if stats_query.avg_assists else None
    avg_saves = float(stats_query.avg_saves) if stats_query.avg_saves else None
    avg_shots = float(stats_query.avg_shots) if stats_query.avg_shots else None

    # Build mechanics list
    mechanics = []
    if stats_query.total_wavedash:
        mechanics.append(
            MechanicStat(name="Wave Dashes", count=int(stats_query.total_wavedash))
        )
    if stats_query.total_aerial:
        mechanics.append(
            MechanicStat(name="Aerials", count=int(stats_query.total_aerial))
        )
    if stats_query.total_speedflip:
        mechanics.append(
            MechanicStat(name="Speedflips", count=int(stats_query.total_speedflip))
        )
    if stats_query.total_halfflip:
        mechanics.append(
            MechanicStat(name="Half Flips", count=int(stats_query.total_halfflip))
        )
    if stats_query.total_flip_cancel:
        mechanics.append(
            MechanicStat(name="Flip Cancels", count=int(stats_query.total_flip_cancel))
        )

    # Sort by count descending and take top 6
    mechanics.sort(key=lambda m: m.count, reverse=True)
    top_mechanics = mechanics[:6]

    # Determine trend (compare last 10 vs previous 10 win rate)
    recent_trend = "stable"
    if len(recent_replays) >= 10:
        last_10 = recent_replays[:10]
        prev_10 = recent_replays[10:20] if len(recent_replays) >= 20 else []

        if prev_10:
            last_10_wins = sum(1 for r in last_10 if r.result == "WIN")
            prev_10_wins = sum(1 for r in prev_10 if r.result == "WIN")
            last_10_rate = last_10_wins / len(last_10)
            prev_10_rate = prev_10_wins / len(prev_10)

            if last_10_rate > prev_10_rate + 0.1:
                recent_trend = "up"
            elif last_10_rate < prev_10_rate - 0.1:
                recent_trend = "down"

    return DashboardStatsResponse(
        total_replays=total_replays,
        recent_win_rate=round(recent_win_rate, 1) if recent_win_rate else None,
        avg_goals=round(avg_goals, 1) if avg_goals else None,
        avg_assists=round(avg_assists, 1) if avg_assists else None,
        avg_saves=round(avg_saves, 1) if avg_saves else None,
        avg_shots=round(avg_shots, 1) if avg_shots else None,
        top_mechanics=top_mechanics,
        recent_trend=recent_trend,
        has_data=True,
    )


@router.get("/me/export")
async def export_user_data(
    user: AuthenticatedUser,
    db: Annotated[DBSession, Depends(get_session)],
) -> dict:
    """Export all user data per GDPR Article 20 (right to data portability).

    Returns all personal data associated with the user's account.
    """
    db_user = db.query(User).filter(User.id == user.id).first()
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Collect all user data
    user_replays = db.query(UserReplay).filter(UserReplay.user_id == user.id).all()
    coach_sessions = (
        db.query(CoachSession).filter(CoachSession.user_id == user.id).all()
    )
    coach_notes = db.query(CoachNote).filter(CoachNote.user_id == user.id).all()

    # Get session IDs for message lookup
    session_ids = [s.id for s in coach_sessions]
    coach_messages = (
        db.query(CoachMessage)
        .filter(CoachMessage.session_id.in_(session_ids))
        .order_by(CoachMessage.created_at)
        .all()
        if session_ids
        else []
    )

    return {
        "user": {
            "id": db_user.id,
            "email": db_user.email,
            "display_name": db_user.display_name,
            "image": db_user.image,
            "subscription_tier": db_user.subscription_tier,
            "subscription_status": db_user.subscription_status,
            "tos_accepted_at": (
                db_user.tos_accepted_at.isoformat() if db_user.tos_accepted_at else None
            ),
            "created_at": (
                db_user.created_at.isoformat() if db_user.created_at else None
            ),
            "updated_at": (
                db_user.updated_at.isoformat() if db_user.updated_at else None
            ),
        },
        "replays": [
            {
                "replay_id": r.replay_id,
                "ownership_type": r.ownership_type,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in user_replays
        ],
        "coach_sessions": [
            {
                "id": s.id,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "ended_at": s.ended_at.isoformat() if s.ended_at else None,
                "message_count": s.message_count,
                "total_input_tokens": s.total_input_tokens,
                "total_output_tokens": s.total_output_tokens,
            }
            for s in coach_sessions
        ],
        "coach_messages": [
            {
                "id": m.id,
                "session_id": m.session_id,
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in coach_messages
        ],
        "coach_notes": [
            {
                "id": n.id,
                "content": n.content,
                "category": n.category,
                "source": n.source,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in coach_notes
        ],
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }


class StatComparison(BaseModel):
    """Single stat comparison against benchmark."""

    value: float
    benchmark: float
    rank_name: str
    difference: float
    percentage: float
    comparison: str  # "above", "below", "on_par"


class BenchmarkComparisonResponse(BaseModel):
    """Benchmark comparison response."""

    rank_tier: int
    rank_name: str
    comparisons: dict[str, StatComparison]
    has_data: bool


@router.get("/me/benchmarks", response_model=BenchmarkComparisonResponse)
async def get_benchmark_comparison(
    user: AuthenticatedUser,
    db: Annotated[DBSession, Depends(get_session)],
    rank_tier: int | None = None,
) -> BenchmarkComparisonResponse:
    """Compare user stats against rank benchmarks.

    If rank_tier is not provided, estimates rank from user's performance.
    """
    # Rate limit this endpoint (aggregation queries are expensive)
    rate_result = check_rate_limit(user.id, "benchmarks")
    if not rate_result.allowed:
        raise rate_limit_response(rate_result)

    # Get user's replay IDs
    user_replay_ids = (
        db.query(UserReplay.replay_id).filter(UserReplay.user_id == user.id).subquery()
    )

    # Get user's aggregated stats (where is_me = True)
    stats_query = (
        db.query(
            func.count(PlayerGameStats.id).label("game_count"),
            func.avg(PlayerGameStats.goals).label("avg_goals"),
            func.avg(PlayerGameStats.assists).label("avg_assists"),
            func.avg(PlayerGameStats.saves).label("avg_saves"),
            func.avg(PlayerGameStats.shots).label("avg_shots"),
            func.avg(PlayerGameStats.bcpm).label("avg_bcpm"),
            func.avg(PlayerGameStats.time_supersonic_s).label("avg_supersonic_s"),
            func.sum(PlayerGameStats.aerial_count).label("total_aerials"),
            func.sum(PlayerGameStats.wavedash_count).label("total_wavedash"),
        )
        .filter(
            PlayerGameStats.replay_id.in_(user_replay_ids),
            PlayerGameStats.is_me == True,  # noqa: E712
        )
        .first()
    )

    game_count = stats_query.game_count if stats_query else 0

    if game_count == 0:
        return BenchmarkComparisonResponse(
            rank_tier=10,  # Default to Platinum I
            rank_name=RANK_DISPLAY_NAMES.get(10, "Platinum I"),
            comparisons={},
            has_data=False,
        )

    # Extract user stats
    avg_goals = float(stats_query.avg_goals) if stats_query.avg_goals else 0
    avg_assists = float(stats_query.avg_assists) if stats_query.avg_assists else 0
    avg_saves = float(stats_query.avg_saves) if stats_query.avg_saves else 0
    avg_shots = float(stats_query.avg_shots) if stats_query.avg_shots else 0
    avg_bcpm = float(stats_query.avg_bcpm) if stats_query.avg_bcpm else 0
    # avg_supersonic_s is in seconds - convert to rough percentage
    # assuming 5 min avg game
    avg_supersonic_s = (
        float(stats_query.avg_supersonic_s) if stats_query.avg_supersonic_s else 0
    )
    # Estimate supersonic percentage (time_supersonic / ~300s game duration * 100)
    avg_supersonic = (avg_supersonic_s / 300.0) * 100 if avg_supersonic_s > 0 else 0
    aerials_per_game = (
        float(stats_query.total_aerials) / game_count
        if stats_query.total_aerials
        else 0
    )
    wavedash_per_game = (
        float(stats_query.total_wavedash) / game_count
        if stats_query.total_wavedash
        else 0
    )

    # Calculate shooting percentage
    total_shots = avg_shots * game_count
    total_goals = avg_goals * game_count
    shooting_pct = (total_goals / total_shots * 100) if total_shots > 0 else 0

    # If no rank_tier provided, estimate based on performance
    if rank_tier is None:
        # Simple estimation based on goals + assists + boost
        # This is a rough heuristic; real implementation could use ML model
        performance_score = (
            avg_goals * 100
            + avg_assists * 80
            + avg_saves * 60
            + avg_bcpm * 0.3
            + avg_supersonic * 2
        )

        # Map performance score to rank tier (rough estimates)
        if performance_score < 180:
            rank_tier = 7  # Gold
        elif performance_score < 230:
            rank_tier = 10  # Platinum
        elif performance_score < 280:
            rank_tier = 13  # Diamond
        elif performance_score < 330:
            rank_tier = 16  # Champion
        elif performance_score < 380:
            rank_tier = 19  # GC
        else:
            rank_tier = 22  # SSL

    # Get benchmarks for this rank
    benchmark = get_benchmark_for_rank(rank_tier)
    if not benchmark:
        benchmark = get_benchmark_for_rank(10)  # Default to Platinum I

    # Build comparisons
    comparisons = {}

    def add_comparison(
        key: str,
        user_value: float,
        bench_value: float,
        higher_is_better: bool = True,
    ) -> None:
        result = compare_to_benchmark(user_value, bench_value, higher_is_better)
        comparisons[key] = StatComparison(
            value=round(user_value, 2),
            benchmark=round(bench_value, 2),
            rank_name=benchmark.rank_name,
            difference=result["difference"],
            percentage=result["percentage"],
            comparison=result["comparison"],
        )

    add_comparison("goals_per_game", avg_goals, benchmark.goals_per_game)
    add_comparison("assists_per_game", avg_assists, benchmark.assists_per_game)
    add_comparison("saves_per_game", avg_saves, benchmark.saves_per_game)
    add_comparison("shots_per_game", avg_shots, benchmark.shots_per_game)
    add_comparison("shooting_pct", shooting_pct, benchmark.shooting_pct)
    add_comparison("boost_per_minute", avg_bcpm, benchmark.boost_per_minute)
    add_comparison("supersonic_pct", avg_supersonic, benchmark.supersonic_pct)
    add_comparison("aerials_per_game", aerials_per_game, benchmark.aerials_per_game)
    add_comparison(
        "wavedashes_per_game", wavedash_per_game, benchmark.wavedashes_per_game
    )

    return BenchmarkComparisonResponse(
        rank_tier=rank_tier,
        rank_name=RANK_DISPLAY_NAMES.get(rank_tier, "Unknown"),
        comparisons=comparisons,
        has_data=True,
    )


# Trends endpoint - for the trends page
ALLOWED_TREND_METRICS = {
    "bcpm",
    "avg_boost",
    "goals",
    "assists",
    "saves",
    "shots",
    "score",
    "avg_speed_kph",
    "time_supersonic_s",
}


class TrendDataPoint(BaseModel):
    """Single data point for trends."""

    date: str
    value: float


class TrendsResponse(BaseModel):
    """Trends API response."""

    metric: str
    period: str
    values: list[TrendDataPoint]
    has_data: bool


@router.get("/me/trends", response_model=TrendsResponse)
async def get_user_trends(
    user: AuthenticatedUser,
    db: Annotated[DBSession, Depends(get_session)],
    metric: str = Query(default="goals", description="Metric to trend"),
    period: str = Query(default="30d", description="Time period (7d, 30d, 90d, all)"),
) -> TrendsResponse:
    """Get trend data for a metric over time for the authenticated user."""
    # Validate metric
    if metric not in ALLOWED_TREND_METRICS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid metric. Allowed: {sorted(ALLOWED_TREND_METRICS)}",
        )

    # Parse period
    allowed_periods = {"7d", "30d", "90d", "all"}
    if period not in allowed_periods:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid period. Allowed: {sorted(allowed_periods)}",
        )

    if period == "all":
        date_from = None
    else:
        days = int(period.rstrip("d"))
        date_from = datetime.now(timezone.utc).date() - timedelta(days=days)

    # Get user's replay IDs
    user_replay_ids = (
        db.query(UserReplay.replay_id).filter(UserReplay.user_id == user.id).subquery()
    )

    # Query stats scoped to user's replays
    query = (
        db.query(Replay.play_date, PlayerGameStats)
        .filter(Replay.replay_id.in_(user_replay_ids))
        .join(PlayerGameStats, Replay.replay_id == PlayerGameStats.replay_id)
        .filter(PlayerGameStats.is_me == True)  # noqa: E712
    )

    if date_from:
        query = query.filter(Replay.play_date >= date_from)

    query = query.order_by(Replay.play_date)
    results = query.all()

    if not results:
        return TrendsResponse(metric=metric, period=period, values=[], has_data=False)

    # Extract values by date
    values = []
    for play_date, stats in results:
        value = getattr(stats, metric, None)
        if value is not None and play_date is not None:
            values.append(
                TrendDataPoint(date=play_date.isoformat(), value=round(float(value), 2))
            )

    return TrendsResponse(metric=metric, period=period, values=values, has_data=len(values) > 0)


# Self-comparison endpoint - compare current period vs previous period
class PeriodStats(BaseModel):
    """Stats for a time period."""

    period_label: str
    game_count: int
    win_rate: float | None
    avg_goals: float | None
    avg_assists: float | None
    avg_saves: float | None
    avg_shots: float | None
    avg_bcpm: float | None


class SelfComparisonMetric(BaseModel):
    """Comparison of a single metric between periods."""

    name: str
    current: float | None
    previous: float | None
    change: float
    change_pct: float


class SelfComparisonResponse(BaseModel):
    """Self-comparison API response."""

    current_period: str
    previous_period: str
    current_games: int
    previous_games: int
    metrics: list[SelfComparisonMetric]
    has_data: bool


@router.get("/me/compare/self", response_model=SelfComparisonResponse)
async def get_self_comparison(
    user: AuthenticatedUser,
    db: Annotated[DBSession, Depends(get_session)],
    period: str = Query(default="7d", description="Period to compare (7d, 30d)"),
) -> SelfComparisonResponse:
    """Compare user stats from current period vs previous period."""
    # Parse period
    if period == "7d":
        days = 7
        current_label = "This Week"
        previous_label = "Last Week"
    elif period == "30d":
        days = 30
        current_label = "This Month"
        previous_label = "Last Month"
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid period. Use '7d' or '30d'.",
        )

    now = datetime.now(timezone.utc).date()
    current_start = now - timedelta(days=days)
    previous_start = now - timedelta(days=days * 2)
    previous_end = current_start - timedelta(days=1)

    # Get user's replay IDs
    user_replay_ids = (
        db.query(UserReplay.replay_id).filter(UserReplay.user_id == user.id).subquery()
    )

    def get_period_stats(start_date, end_date):
        """Get aggregated stats for a date range."""
        query = (
            db.query(
                func.count(PlayerGameStats.id).label("game_count"),
                func.avg(PlayerGameStats.goals).label("avg_goals"),
                func.avg(PlayerGameStats.assists).label("avg_assists"),
                func.avg(PlayerGameStats.saves).label("avg_saves"),
                func.avg(PlayerGameStats.shots).label("avg_shots"),
                func.avg(PlayerGameStats.bcpm).label("avg_bcpm"),
            )
            .join(Replay, PlayerGameStats.replay_id == Replay.replay_id)
            .filter(
                PlayerGameStats.replay_id.in_(user_replay_ids),
                PlayerGameStats.is_me == True,  # noqa: E712
                Replay.play_date >= start_date,
                Replay.play_date <= end_date,
            )
            .first()
        )

        if not query or query.game_count == 0:
            return None, 0

        # Calculate win rate
        wins = (
            db.query(func.count(Replay.replay_id))
            .filter(
                Replay.replay_id.in_(user_replay_ids),
                Replay.play_date >= start_date,
                Replay.play_date <= end_date,
                Replay.result == "WIN",
            )
            .scalar()
            or 0
        )
        win_rate = (wins / query.game_count * 100) if query.game_count > 0 else None

        return {
            "game_count": query.game_count,
            "win_rate": win_rate,
            "avg_goals": float(query.avg_goals) if query.avg_goals else None,
            "avg_assists": float(query.avg_assists) if query.avg_assists else None,
            "avg_saves": float(query.avg_saves) if query.avg_saves else None,
            "avg_shots": float(query.avg_shots) if query.avg_shots else None,
            "avg_bcpm": float(query.avg_bcpm) if query.avg_bcpm else None,
        }, query.game_count

    current_stats, current_games = get_period_stats(current_start, now)
    previous_stats, previous_games = get_period_stats(previous_start, previous_end)

    if not current_stats and not previous_stats:
        return SelfComparisonResponse(
            current_period=current_label,
            previous_period=previous_label,
            current_games=0,
            previous_games=0,
            metrics=[],
            has_data=False,
        )

    # Build comparison metrics
    metrics = []

    def add_metric(name: str, key: str):
        current_val = current_stats.get(key) if current_stats else None
        previous_val = previous_stats.get(key) if previous_stats else None

        if current_val is None and previous_val is None:
            return

        # Use 0.0 for missing values, but preserve None distinction for display
        curr = current_val if current_val is not None else 0.0
        prev = previous_val if previous_val is not None else 0.0

        change = curr - prev
        # Show None for change_pct when no previous data to compare against
        change_pct = (change / prev * 100) if prev != 0 else None

        metrics.append(
            SelfComparisonMetric(
                name=name,
                current=round(curr, 2) if current_val is not None else None,
                previous=round(prev, 2) if previous_val is not None else None,
                change=round(change, 2) if current_val is not None or previous_val is not None else None,
                change_pct=round(change_pct, 1) if change_pct is not None else None,
            )
        )

    add_metric("Win Rate", "win_rate")
    add_metric("Goals/Game", "avg_goals")
    add_metric("Assists/Game", "avg_assists")
    add_metric("Saves/Game", "avg_saves")
    add_metric("Shots/Game", "avg_shots")
    add_metric("Boost/Min", "avg_bcpm")

    return SelfComparisonResponse(
        current_period=current_label,
        previous_period=previous_label,
        current_games=current_games,
        previous_games=previous_games,
        metrics=metrics,
        has_data=True,
    )
