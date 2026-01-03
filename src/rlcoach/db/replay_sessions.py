# src/rlcoach/db/replay_sessions.py
"""Session detection for grouping replays.

Replays within a configurable time gap are considered part of the same
play session. Default gap is 30 minutes.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Replay

# Default session gap in minutes
DEFAULT_SESSION_GAP_MINUTES = 30


def generate_session_id(user_id: str, first_replay_time: datetime) -> str:
    """Generate a deterministic session ID.

    Args:
        user_id: The user who owns the replays
        first_replay_time: Timestamp of the first replay in the session

    Returns:
        A short hash-based session ID
    """
    # Round to the minute for stability
    rounded = first_replay_time.replace(second=0, microsecond=0)
    key = f"{user_id}:{rounded.isoformat()}"
    return hashlib.sha256(key.encode()).hexdigest()[:12]


def detect_session_for_replay(
    db: Session,
    played_at_utc: datetime,
    user_id: str,
    playlist: str | None = None,
    session_gap_minutes: int = DEFAULT_SESSION_GAP_MINUTES,
) -> str:
    """Detect or create a session ID for a new replay.

    Finds existing replays within the session gap and assigns the same
    session ID, or creates a new session if none found.

    Args:
        db: Database session
        played_at_utc: When the replay was played
        user_id: User who uploaded the replay
        playlist: Optional playlist filter (sessions per playlist)
        session_gap_minutes: Gap threshold for session grouping

    Returns:
        Session ID to assign to the replay
    """
    gap = timedelta(minutes=session_gap_minutes)
    window_start = played_at_utc - gap
    window_end = played_at_utc + gap

    # Query for nearby replays in the same user's collection
    # Join through user_replays to filter by user
    from .models import UserReplay

    query = (
        select(Replay)
        .join(UserReplay, Replay.replay_id == UserReplay.replay_id)
        .where(
            UserReplay.user_id == user_id,
            Replay.played_at_utc >= window_start,
            Replay.played_at_utc <= window_end,
            Replay.session_id.isnot(None),
        )
    )

    if playlist:
        query = query.where(Replay.playlist == playlist)

    query = query.order_by(Replay.played_at_utc).limit(1)

    result = db.execute(query).scalar_one_or_none()

    if result and result.session_id:
        return result.session_id

    # No existing session found, create new one
    return generate_session_id(user_id, played_at_utc)


def assign_sessions_to_replays(
    db: Session,
    replays: Sequence[Replay],
    user_id: str,
    session_gap_minutes: int = DEFAULT_SESSION_GAP_MINUTES,
) -> dict[str, list[str]]:
    """Assign session IDs to a batch of replays.

    More efficient than calling detect_session_for_replay individually
    when processing a batch of uploads.

    Args:
        db: Database session
        replays: List of Replay objects (must have played_at_utc set)
        user_id: User who owns these replays
        session_gap_minutes: Gap threshold for session grouping

    Returns:
        Dict mapping session_id -> list of replay_ids in that session
    """
    if not replays:
        return {}

    # Sort by played_at
    sorted_replays = sorted(replays, key=lambda r: r.played_at_utc)
    gap = timedelta(minutes=session_gap_minutes)

    sessions: dict[str, list[str]] = {}
    current_session_id: str | None = None
    last_played_at: datetime | None = None

    for replay in sorted_replays:
        # Check if this replay starts a new session
        if last_played_at is None or (replay.played_at_utc - last_played_at) > gap:
            # New session
            current_session_id = generate_session_id(user_id, replay.played_at_utc)
            sessions[current_session_id] = []

        # Assign to current session
        replay.session_id = current_session_id
        sessions[current_session_id].append(replay.replay_id)
        last_played_at = replay.played_at_utc

    return sessions


def get_sessions_for_user(
    db: Session,
    user_id: str,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """Get play sessions for a user with aggregated stats.

    Args:
        db: Database session
        user_id: User ID
        limit: Max sessions to return
        offset: Pagination offset

    Returns:
        List of session summaries with replay counts and date ranges
    """
    from sqlalchemy import func

    from .models import UserReplay

    query = (
        select(
            Replay.session_id,
            func.min(Replay.played_at_utc).label("started_at"),
            func.max(Replay.played_at_utc).label("ended_at"),
            func.count(Replay.replay_id).label("replay_count"),
            func.array_agg(Replay.playlist.distinct()).label("playlists"),
        )
        .join(UserReplay, Replay.replay_id == UserReplay.replay_id)
        .where(
            UserReplay.user_id == user_id,
            Replay.session_id.isnot(None),
        )
        .group_by(Replay.session_id)
        .order_by(func.max(Replay.played_at_utc).desc())
        .limit(limit)
        .offset(offset)
    )

    results = db.execute(query).fetchall()

    return [
        {
            "session_id": row.session_id,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "ended_at": row.ended_at.isoformat() if row.ended_at else None,
            "replay_count": row.replay_count,
            "playlists": list(row.playlists) if row.playlists else [],
        }
        for row in results
    ]
