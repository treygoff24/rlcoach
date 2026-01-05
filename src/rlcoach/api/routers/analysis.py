# src/rlcoach/api/routers/analysis.py
"""Analysis API endpoints (trends, benchmarks, patterns, weaknesses)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session as DBSession

from ...analysis.patterns import compute_pattern_analysis
from ...analysis.weaknesses import detect_weaknesses
from ...db import create_session, get_session
from ...db.models import Benchmark, PlayerGameStats, Replay, UserReplay
from ..auth import OptionalUser

router = APIRouter(tags=["analysis"])

# Allowlist of metrics that can be trended (prevents schema enumeration)
ALLOWED_METRICS = {
    "bcpm",
    "avg_boost",
    "goals",
    "assists",
    "saves",
    "shots",
    "score",
    "avg_speed_kph",
    "time_supersonic_s",
    "behind_ball_pct",
    "demos_inflicted",
    "demos_taken",
}


@router.get("/trends")
async def get_trends(
    user: OptionalUser,
    db: Annotated[DBSession, Depends(get_session)],
    metric: str = Query(..., description="Metric to trend (e.g., bcpm, goals)"),
    period: str = Query(default="30d", description="Time period (7d, 30d, 90d, all)"),
    playlist: str | None = None,
) -> dict[str, Any]:
    """Get trend data for a metric over time.

    Args:
        metric: The metric to get trends for
        period: Time period to analyze
        playlist: Optional playlist filter
    """
    # Security: Validate metric against allowlist
    if metric not in ALLOWED_METRICS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid metric. Allowed: {sorted(ALLOWED_METRICS)}"
        )

    # Parse period
    if period == "all":
        date_from = None
    else:
        days = int(period.rstrip("d"))
        date_from = date.today() - timedelta(days=days)

    # Build query for user's replay stats
    # If authenticated, scope to user's data via UserReplay join
    # If not authenticated (CLI mode), fall back to is_me filter
    if user:
        query = (
            db.query(Replay.play_date, PlayerGameStats)
            .join(UserReplay, Replay.replay_id == UserReplay.replay_id)
            .join(PlayerGameStats, Replay.replay_id == PlayerGameStats.replay_id)
            .filter(UserReplay.user_id == user.id)
            .filter(PlayerGameStats.is_me == True)  # noqa: E712
        )
    else:
        query = (
            db.query(Replay.play_date, PlayerGameStats)
            .join(PlayerGameStats, Replay.replay_id == PlayerGameStats.replay_id)
            .filter(PlayerGameStats.is_me == True)  # noqa: E712
        )

    if date_from:
        query = query.filter(Replay.play_date >= date_from)
    if playlist:
        query = query.filter(Replay.playlist == playlist)

    query = query.order_by(Replay.play_date)
    results = query.all()

    # Extract values by date (metric already validated)
    values = []
    for play_date, stats in results:
        value = getattr(stats, metric, None)
        if value is not None:
            values.append(
                {
                    "date": play_date.isoformat() if play_date else None,
                    "value": value,
                }
            )

    return {
        "metric": metric,
        "period": period,
        "values": values,
    }


@router.get("/benchmarks")
async def list_benchmarks(
    metric: str | None = None,
    playlist: str | None = None,
    rank: str | None = None,
) -> dict[str, Any]:
    """List available benchmarks.

    Args:
        metric: Filter by metric name
        playlist: Filter by playlist
        rank: Filter by rank tier
    """
    session = create_session()
    try:
        query = session.query(Benchmark)

        if metric:
            query = query.filter(Benchmark.metric == metric)
        if playlist:
            query = query.filter(Benchmark.playlist == playlist)
        if rank:
            query = query.filter(Benchmark.rank_tier == rank)

        benchmarks = query.order_by(Benchmark.metric, Benchmark.rank_tier).all()

        items = []
        for b in benchmarks:
            items.append(
                {
                    "metric": b.metric,
                    "playlist": b.playlist,
                    "rank_tier": b.rank_tier,
                    "median_value": b.median_value,
                    "p25_value": b.p25_value,
                    "p75_value": b.p75_value,
                    "elite_threshold": b.elite_threshold,
                    "source": b.source,
                }
            )

        return {"items": items}

    finally:
        session.close()


@router.get("/compare")
async def get_comparison(
    rank: str = Query(..., description="Target rank to compare against"),
    playlist: str = Query(default="DOUBLES"),
    period: str = Query(default="30d"),
) -> dict[str, Any]:
    """Compare my stats to target rank benchmarks.

    Args:
        rank: Target rank tier (e.g., GC1, C3)
        playlist: Playlist to compare
        period: Time period for my averages
    """
    # Parse period
    if period == "all":
        date_from = None
    else:
        days = int(period.rstrip("d"))
        date_from = date.today() - timedelta(days=days)

    session = create_session()
    try:
        # Get my average stats
        query = (
            session.query(PlayerGameStats)
            .join(Replay, Replay.replay_id == PlayerGameStats.replay_id)
            .filter(PlayerGameStats.is_me)
            .filter(Replay.playlist == playlist)
        )

        if date_from:
            query = query.filter(Replay.play_date >= date_from)

        my_stats = query.all()

        if not my_stats:
            return {
                "target_rank": rank,
                "playlist": playlist,
                "comparisons": [],
                "game_count": 0,
            }

        # Get benchmarks for target rank
        benchmarks = (
            session.query(Benchmark)
            .filter(Benchmark.playlist == playlist)
            .filter(Benchmark.rank_tier == rank)
            .all()
        )

        benchmark_map = {b.metric: b for b in benchmarks}

        # Compute averages and compare
        metric_attrs = ["bcpm", "avg_boost", "goals", "assists", "saves", "shots"]
        comparisons = []

        for metric in metric_attrs:
            values = [
                getattr(s, metric) for s in my_stats if getattr(s, metric) is not None
            ]
            if not values:
                continue

            my_avg = sum(values) / len(values)

            benchmark = benchmark_map.get(metric)
            if benchmark:
                diff = my_avg - benchmark.median_value
                diff_pct = (
                    (diff / benchmark.median_value * 100)
                    if benchmark.median_value
                    else 0
                )

                comparisons.append(
                    {
                        "metric": metric,
                        "my_value": round(my_avg, 2),
                        "target_median": benchmark.median_value,
                        "difference": round(diff, 2),
                        "difference_pct": round(diff_pct, 1),
                    }
                )
            else:
                comparisons.append(
                    {
                        "metric": metric,
                        "my_value": round(my_avg, 2),
                        "target_median": None,
                        "difference": None,
                        "difference_pct": None,
                    }
                )

        return {
            "target_rank": rank,
            "playlist": playlist,
            "comparisons": comparisons,
            "game_count": len(my_stats),
        }

    finally:
        session.close()


@router.get("/patterns")
async def get_patterns(
    playlist: str = Query(default="DOUBLES"),
    period: str = Query(default="30d"),
    min_games: int = Query(default=5),
) -> dict[str, Any]:
    """Analyze patterns in wins vs losses.

    Uses Cohen's d effect size to identify statistically significant patterns.

    Args:
        playlist: Playlist to analyze
        period: Time period
        min_games: Minimum games per result type
    """
    # Parse period
    if period == "all":
        date_from = None
    else:
        days = int(period.rstrip("d"))
        date_from = date.today() - timedelta(days=days)

    session = create_session()
    try:
        # Get my stats with results
        query = (
            session.query(PlayerGameStats, Replay.result)
            .join(Replay, Replay.replay_id == PlayerGameStats.replay_id)
            .filter(PlayerGameStats.is_me)
            .filter(Replay.playlist == playlist)
        )

        if date_from:
            query = query.filter(Replay.play_date >= date_from)

        results = query.all()

        # Group by result
        wins = []
        losses = []

        for stats, result in results:
            stat_dict = {
                "bcpm": stats.bcpm,
                "avg_boost": stats.avg_boost,
                "goals": stats.goals,
                "assists": stats.assists,
                "saves": stats.saves,
                "shots": stats.shots,
            }
            if result == "WIN":
                wins.append(stat_dict)
            elif result == "LOSS":
                losses.append(stat_dict)

        # Compute patterns
        patterns = compute_pattern_analysis(wins, losses, min_games=min_games)

        pattern_list = []
        for p in patterns:
            pattern_list.append(
                {
                    "metric": p.metric,
                    "win_avg": round(p.win_avg, 2),
                    "loss_avg": round(p.loss_avg, 2),
                    "delta": round(p.delta, 2),
                    "effect_size": round(p.effect_size, 3),
                    "direction": p.direction,
                }
            )

        return {
            "patterns": pattern_list,
            "win_count": len(wins),
            "loss_count": len(losses),
        }

    finally:
        session.close()


@router.get("/weaknesses")
async def get_weaknesses(
    playlist: str = Query(default="DOUBLES"),
    rank: str = Query(default="GC1"),
    period: str = Query(default="30d"),
) -> dict[str, Any]:
    """Detect weaknesses and strengths compared to benchmarks.

    Uses z-scores to identify areas needing improvement.

    Args:
        playlist: Playlist to analyze
        rank: Target rank for comparison
        period: Time period for averages
    """
    # Parse period
    if period == "all":
        date_from = None
    else:
        days = int(period.rstrip("d"))
        date_from = date.today() - timedelta(days=days)

    session = create_session()
    try:
        # Get my average stats
        query = (
            session.query(PlayerGameStats)
            .join(Replay, Replay.replay_id == PlayerGameStats.replay_id)
            .filter(PlayerGameStats.is_me)
            .filter(Replay.playlist == playlist)
        )

        if date_from:
            query = query.filter(Replay.play_date >= date_from)

        my_stats = query.all()

        if not my_stats:
            return {
                "weaknesses": [],
                "strengths": [],
                "game_count": 0,
            }

        # Compute averages
        metric_attrs = ["bcpm", "avg_boost", "goals", "assists", "saves", "shots"]
        my_averages = {}

        for metric in metric_attrs:
            values = [
                getattr(s, metric) for s in my_stats if getattr(s, metric) is not None
            ]
            if values:
                my_averages[metric] = sum(values) / len(values)

        # Get benchmarks
        benchmarks = (
            session.query(Benchmark)
            .filter(Benchmark.playlist == playlist)
            .filter(Benchmark.rank_tier == rank)
            .all()
        )

        benchmark_map = {}
        for b in benchmarks:
            benchmark_map[b.metric] = {
                "p25": b.p25_value,
                "median": b.median_value,
                "p75": b.p75_value,
            }

        # Detect weaknesses and strengths
        weakness_results = detect_weaknesses(my_averages, benchmark_map)

        weaknesses = []
        strengths = []

        for w in weakness_results:
            item = {
                "metric": w.metric,
                "my_value": round(w.my_value, 2),
                "target_median": round(w.target_median, 2),
                "z_score": round(w.z_score, 2),
                "severity": w.severity.value,
            }

            if w.severity.value == "strength":
                strengths.append(item)
            elif w.severity.value != "neutral":
                weaknesses.append(item)

        # Sort by severity
        weaknesses.sort(key=lambda x: abs(x["z_score"]), reverse=True)
        strengths.sort(key=lambda x: x["z_score"], reverse=True)

        return {
            "weaknesses": weaknesses,
            "strengths": strengths,
            "game_count": len(my_stats),
        }

    finally:
        session.close()
