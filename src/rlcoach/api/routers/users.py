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
from ...data.benchmarks import (
    get_benchmark_for_rank,
    get_closest_rank_tier,
    compare_to_benchmark,
    RANK_DISPLAY_NAMES,
)
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
            func.avg(PlayerGameStats.boost_per_minute).label("avg_bcpm"),
            func.avg(PlayerGameStats.supersonic_pct).label("avg_supersonic"),
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
    avg_supersonic = float(stats_query.avg_supersonic) if stats_query.avg_supersonic else 0
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
            avg_goals * 100 +
            avg_assists * 80 +
            avg_saves * 60 +
            avg_bcpm * 0.3 +
            avg_supersonic * 2
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
    add_comparison("wavedashes_per_game", wavedash_per_game, benchmark.wavedashes_per_game)

    return BenchmarkComparisonResponse(
        rank_tier=rank_tier,
        rank_name=RANK_DISPLAY_NAMES.get(rank_tier, "Unknown"),
        comparisons=comparisons,
        has_data=True,
    )
