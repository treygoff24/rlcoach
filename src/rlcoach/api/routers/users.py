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

from sqlalchemy import func

from ...db import User, get_session
from ...db.models import CoachNote, CoachSession, PlayerGameStats, Replay, UserReplay
from ...services.coach.budget import MONTHLY_TOKEN_BUDGET, get_token_budget_remaining
from ..auth import AuthenticatedUser
from ..security import sanitize_display_name

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
    db_user.display_name = f"Deleted User {db_user.id[:8]}"
    db_user.image = None
    db_user.email_verified = None
    db_user.stripe_customer_id = None
    db_user.stripe_subscription_id = None
    db_user.updated_at = datetime.now(timezone.utc)

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

    wins = sum(1 for r in recent_replays if r.result == "win")
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
        mechanics.append(MechanicStat(name="Wave Dashes", count=int(stats_query.total_wavedash)))
    if stats_query.total_aerial:
        mechanics.append(MechanicStat(name="Aerials", count=int(stats_query.total_aerial)))
    if stats_query.total_speedflip:
        mechanics.append(MechanicStat(name="Speedflips", count=int(stats_query.total_speedflip)))
    if stats_query.total_halfflip:
        mechanics.append(MechanicStat(name="Half Flips", count=int(stats_query.total_halfflip)))
    if stats_query.total_flip_cancel:
        mechanics.append(MechanicStat(name="Flip Cancels", count=int(stats_query.total_flip_cancel)))

    # Sort by count descending and take top 6
    mechanics.sort(key=lambda m: m.count, reverse=True)
    top_mechanics = mechanics[:6]

    # Determine trend (compare last 10 vs previous 10 win rate)
    recent_trend = "stable"
    if len(recent_replays) >= 10:
        last_10 = recent_replays[:10]
        prev_10 = recent_replays[10:20] if len(recent_replays) >= 20 else []

        if prev_10:
            last_10_wins = sum(1 for r in last_10 if r.result == "win")
            prev_10_wins = sum(1 for r in prev_10 if r.result == "win")
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

    return {
        "user": {
            "id": db_user.id,
            "email": db_user.email,
            "display_name": db_user.display_name,
            "image": db_user.image,
            "subscription_tier": db_user.subscription_tier,
            "subscription_status": db_user.subscription_status,
            "created_at": db_user.created_at.isoformat() if db_user.created_at else None,
            "updated_at": db_user.updated_at.isoformat() if db_user.updated_at else None,
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
                "message_count": s.message_count,
            }
            for s in coach_sessions
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
