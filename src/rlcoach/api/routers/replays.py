# src/rlcoach/api/routers/replays.py
"""Replay upload and management API endpoints.

Handles replay file uploads, processing status, and retrieval.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from ...db import Replay, UploadedReplay, UserReplay, get_session
from ..auth import AuthenticatedUser
from ..rate_limit import check_rate_limit, rate_limit_response
from ..security import sanitize_filename

router = APIRouter(prefix="/api/v1/replays", tags=["replays"])

# Upload limits
MAX_REPLAY_SIZE = 50 * 1024 * 1024  # 50MB
MIN_REPLAY_SIZE = 1000  # Minimum valid replay size
ALLOWED_EXTENSIONS = {".replay"}

# Rocket League replay magic bytes validation
# Valid replays start with a 4-byte header size followed by CRC
# The header contains "TAGame.Replay_Soccar_TA" class name
REPLAY_HEADER_MARKER = b"TAGame"

logger = logging.getLogger(__name__)

# UUID validation pattern
UUID_PATTERN = re.compile(
    r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$", re.IGNORECASE
)


def _is_valid_uuid(value: str) -> bool:
    """Check if a string is a valid UUID format."""
    return bool(UUID_PATTERN.match(value))


def _is_path_within_directory(file_path: Path, directory: Path) -> bool:
    """Check if a file path is safely within a directory (no traversal)."""
    try:
        file_resolved = file_path.resolve()
        dir_resolved = directory.resolve()
        return str(file_resolved).startswith(str(dir_resolved) + os.sep)
    except (OSError, ValueError):
        return False


def _validate_replay_content(content: bytes) -> bool:
    """Validate that content appears to be a valid Rocket League replay.

    Args:
        content: Raw file bytes

    Returns:
        True if content appears to be a valid replay
    """
    if len(content) < 100:
        return False

    # Check for TAGame marker within first 1000 bytes
    # This appears in all valid Rocket League replays
    header_section = content[:1000]
    return REPLAY_HEADER_MARKER in header_section


class ReplayUploadResponse(BaseModel):
    """Response after successful upload."""

    upload_id: str
    status: str
    filename: str
    size: int
    sha256: str


class ReplayListItem(BaseModel):
    """Replay list item."""

    id: str
    replay_id: str | None = None
    filename: str
    status: str
    played_at: str | None
    map_name: str | None
    playlist: str | None
    team_size: int | None
    result: str | None  # WIN, LOSS, DRAW
    my_score: int | None
    opponent_score: int | None
    created_at: str


class PaginatedReplayList(BaseModel):
    """Paginated list of replays."""

    items: list[ReplayListItem]
    total: int
    limit: int
    offset: int


class ReplayDetail(BaseModel):
    """Full replay details."""

    id: str
    replay_id: str | None
    filename: str
    status: str
    error_message: str | None
    played_at: str | None
    map_name: str | None
    playlist: str | None
    team_size: int | None
    duration_seconds: float | None
    created_at: str
    processed_at: str | None


@router.post("/upload", response_model=ReplayUploadResponse)
async def upload_replay(
    file: Annotated[UploadFile, File(...)],
    user: AuthenticatedUser,
    db: Annotated[DBSession, Depends(get_session)],
) -> ReplayUploadResponse:
    """Upload a replay file for processing.

    Requires authentication. Files are queued for background processing.
    """
    # Rate limit check (10 uploads per minute per user)
    rate_result = check_rate_limit(user.id, "upload")
    if not rate_result.allowed:
        raise rate_limit_response(rate_result)

    # Check if system can accept uploads (backpressure)
    try:
        from ...worker.tasks import can_accept_upload

        can_accept, reason = can_accept_upload()
        if not can_accept:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=reason or "System temporarily unavailable. Please try again.",
            )
    except ImportError:
        # Worker not available - continue without backpressure check
        pass

    # Validate and sanitize filename
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename required")

    # Sanitize filename to prevent XSS and path traversal
    safe_filename = sanitize_filename(file.filename)

    ext = Path(safe_filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # Early size check using part Content-Length header (if provided)
    # This rejects obviously oversized files before reading any data
    content_length = None
    if file.headers is not None:
        content_length = file.headers.get("content-length")
    if content_length:
        try:
            reported_size = int(content_length)
        except ValueError:
            reported_size = None
        if reported_size is not None and reported_size > MAX_REPLAY_SIZE:
            raise HTTPException(
                status_code=413,
                detail=(
                    "File too large. Maximum size: "
                    f"{MAX_REPLAY_SIZE // (1024*1024)}MB"
                ),
            )

    # Read file in streaming mode to check size and compute hash
    # without duplicating memory (write to temp file as we read)
    import tempfile

    total_size = 0
    chunk_size = 64 * 1024  # 64KB chunks
    hasher = hashlib.sha256()

    # Create temp file for streaming
    # Use run_in_executor for file blocking I/O in async endpoint
    import asyncio
    loop = asyncio.get_running_loop()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".replay") as temp_file:
        temp_path = Path(temp_file.name)
        try:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > MAX_REPLAY_SIZE:
                    max_mb = MAX_REPLAY_SIZE // (1024 * 1024)
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large. Maximum size: {max_mb}MB",
                    )
                # Write to file in thread pool to avoid blocking event loop
                await loop.run_in_executor(None, temp_file.write, chunk)
                hasher.update(chunk)

            # Now read header for validation (only first 1000 bytes)
            # Use thread pool for file operations
            await loop.run_in_executor(None, temp_file.flush)

            def read_header():
                with open(temp_path, "rb") as f:
                    return f.read(1000)

            header_content = await loop.run_in_executor(None, read_header)
        except Exception:
            # Clean up temp file on error
            await loop.run_in_executor(None, lambda: temp_path.unlink(missing_ok=True))
            raise

    if total_size < MIN_REPLAY_SIZE:
        await loop.run_in_executor(None, lambda: temp_path.unlink(missing_ok=True))
        raise HTTPException(
            status_code=400, detail="File too small to be a valid replay"
        )

    # Validate replay file content (magic bytes check)
    if not _validate_replay_content(header_content):
        await loop.run_in_executor(None, lambda: temp_path.unlink(missing_ok=True))
        raise HTTPException(
            status_code=400,
            detail="Invalid replay file format. "
            "File does not appear to be a Rocket League replay.",
        )

    # SHA256 already computed during streaming
    file_hash = hasher.hexdigest()

    # Check for duplicate
    existing = (
        db.query(UploadedReplay)
        .filter(
            UploadedReplay.user_id == user.id,
            UploadedReplay.file_hash == file_hash,
        )
        .first()
    )
    if existing:
        await loop.run_in_executor(None, lambda: temp_path.unlink(missing_ok=True))
        return ReplayUploadResponse(
            upload_id=existing.id,
            status=existing.status,
            filename=existing.filename,
            size=existing.file_size_bytes,
            sha256=existing.file_hash,
        )

    # Save file to upload directory - SECURITY FIX: use secure temp dir
    upload_dir = Path(os.getenv("UPLOAD_DIR", ""))
    if not upload_dir or not upload_dir.is_absolute():
        # Fallback to secure temp directory instead of /tmp
        import tempfile

        upload_dir = Path(tempfile.gettempdir()) / f"rlcoach-{os.getuid()}" / "uploads"

    # Create directory if needed (blocking I/O)
    def _create_upload_dir():
        upload_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

    await loop.run_in_executor(None, _create_upload_dir)

    upload_id = str(uuid.uuid4())
    file_path = upload_dir / f"{upload_id}.replay"
    # Move temp file to final location instead of re-reading/writing
    import shutil

    await loop.run_in_executor(None, shutil.move, str(temp_path), str(file_path))

    # Create upload record
    upload = UploadedReplay(
        id=upload_id,
        user_id=user.id,
        filename=safe_filename,
        storage_path=str(file_path),
        file_size_bytes=total_size,
        file_hash=file_hash,
        status="pending",
    )
    db.add(upload)
    db.commit()

    # Queue for processing (Celery task)
    try:
        from ...worker.tasks import process_replay

        process_replay.delay(upload_id)
    except Exception:
        # Worker not available - mark for manual processing
        upload.status = "queued"
        db.commit()

    return ReplayUploadResponse(
        upload_id=upload_id,
        status=upload.status,
        filename=safe_filename,  # Return sanitized filename, not raw user input
        size=total_size,
        sha256=file_hash,
    )


@router.get("/uploads", response_model=PaginatedReplayList)
def list_uploads(
    user: AuthenticatedUser,
    db: Annotated[DBSession, Depends(get_session)],
    status_filter: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaginatedReplayList:
    """List the user's uploaded replays.

    Requires authentication.
    """
    query = db.query(UploadedReplay).filter(UploadedReplay.user_id == user.id)

    if status_filter:
        query = query.filter(UploadedReplay.status == status_filter)

    # Get total count before pagination
    total = query.count()

    uploads = (
        query.order_by(UploadedReplay.uploaded_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )

    items = []
    for upload in uploads:
        # Try to get linked replay data
        replay = None
        if upload.replay_id:
            replay = (
                db.query(Replay).filter(Replay.replay_id == upload.replay_id).first()
            )

        played_at = None
        if replay and replay.played_at_utc:
            played_at = replay.played_at_utc.isoformat()

        items.append(
            ReplayListItem(
                id=upload.id,
                replay_id=upload.replay_id,
                filename=upload.filename,
                status=upload.status,
                played_at=played_at,
                map_name=replay.map if replay else None,
                playlist=replay.playlist if replay else None,
                team_size=replay.team_size if replay else None,
                result=replay.result if replay else None,
                my_score=replay.my_score if replay else None,
                opponent_score=replay.opponent_score if replay else None,
                created_at=upload.uploaded_at.isoformat(),
            )
        )

    return PaginatedReplayList(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/uploads/{upload_id}", response_model=ReplayDetail)
def get_upload(
    upload_id: str,
    user: AuthenticatedUser,
    db: Annotated[DBSession, Depends(get_session)],
) -> ReplayDetail:
    """Get details of an uploaded replay.

    Requires authentication.
    """
    upload = (
        db.query(UploadedReplay)
        .filter(
            UploadedReplay.id == upload_id,
            UploadedReplay.user_id == user.id,
        )
        .first()
    )
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")

    # Get linked replay data
    replay = None
    if upload.replay_id:
        replay = db.query(Replay).filter(Replay.replay_id == upload.replay_id).first()

    played_at = None
    if replay and replay.played_at_utc:
        played_at = replay.played_at_utc.isoformat()
    processed_at = None
    if upload.processed_at:
        processed_at = upload.processed_at.isoformat()

    return ReplayDetail(
        id=upload.id,
        replay_id=upload.replay_id,
        filename=upload.filename,
        status=upload.status,
        error_message=upload.error_message,
        played_at=played_at,
        map_name=replay.map if replay else None,
        playlist=replay.playlist if replay else None,
        team_size=replay.team_size if replay else None,
        duration_seconds=replay.duration_seconds if replay else None,
        created_at=upload.uploaded_at.isoformat(),
        processed_at=processed_at,
    )


@router.delete("/uploads/{upload_id}")
def delete_upload(
    upload_id: str,
    user: AuthenticatedUser,
    db: Annotated[DBSession, Depends(get_session)],
) -> dict:
    """Delete an uploaded replay.

    Removes the file and database records. Requires authentication.
    """
    # Validate upload_id is a valid UUID
    if not _is_valid_uuid(upload_id):
        raise HTTPException(status_code=400, detail="Invalid upload ID format")

    upload = (
        db.query(UploadedReplay)
        .filter(
            UploadedReplay.id == upload_id,
            UploadedReplay.user_id == user.id,
        )
        .first()
    )
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")

    # Store file path before deleting DB record
    file_path_to_delete = upload.storage_path

    # Delete database records first (within transaction)
    try:
        # Remove user-replay association if exists
        if upload.replay_id:
            db.query(UserReplay).filter(
                UserReplay.replay_id == upload.replay_id,
                UserReplay.user_id == user.id,
            ).delete()

        # Delete upload record
        db.delete(upload)
        db.commit()
    except Exception:
        db.rollback()
        raise

    # Only delete file after successful DB commit - with path validation
    if file_path_to_delete:
        file_path = Path(file_path_to_delete)
        upload_dir = Path(os.getenv("UPLOAD_DIR", ""))
        if not upload_dir or not upload_dir.is_absolute():
            # Use same secure directory as upload
            import tempfile

            upload_dir = (
                Path(tempfile.gettempdir()) / f"rlcoach-{os.getuid()}" / "uploads"
            )

        # Security: Validate path is within upload directory
        if _is_path_within_directory(file_path, upload_dir):
            file_path.unlink(missing_ok=True)
        else:
            # Log attempted path traversal but don't fail the request
            logger.warning(
                f"Blocked file deletion outside upload dir: {file_path} "
                f"(user: {user.id}, upload: {upload_id})"
            )

    return {"status": "deleted"}


@router.get("/library", response_model=PaginatedReplayList)
def list_library(
    user: AuthenticatedUser,
    db: Annotated[DBSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaginatedReplayList:
    """List all replays in the user's library.

    Includes both uploaded and shared replays.
    Requires authentication.
    """
    # Get replay IDs from user_replays
    user_replay_ids = (
        db.query(UserReplay.replay_id).filter(UserReplay.user_id == user.id).subquery()
    )

    base_query = db.query(Replay).filter(Replay.replay_id.in_(user_replay_ids))

    # Get total count before pagination
    total = base_query.count()

    replays = (
        base_query.order_by(Replay.played_at_utc.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )

    # Get upload info for each replay - SECURITY FIX: filter by user_id
    items = []
    for replay in replays:
        upload = (
            db.query(UploadedReplay)
            .filter(
                UploadedReplay.replay_id == replay.replay_id,
                UploadedReplay.user_id == user.id,
            )
            .first()
        )

        # Build field values with proper null handling
        filename = f"{replay.replay_id}.replay"
        if upload:
            filename = upload.filename
        replay_status = upload.status if upload else "processed"
        played_at = None
        if replay.played_at_utc:
            played_at = replay.played_at_utc.isoformat()
        created_at = replay.ingested_at.isoformat() if replay.ingested_at else ""
        if upload:
            created_at = upload.uploaded_at.isoformat()

        items.append(
            ReplayListItem(
                id=replay.replay_id,
                replay_id=replay.replay_id,
                filename=filename,
                status=replay_status,
                played_at=played_at,
                map_name=replay.map,
                playlist=replay.playlist,
                team_size=replay.team_size,
                result=replay.result,
                my_score=replay.my_score,
                opponent_score=replay.opponent_score,
                created_at=created_at,
            )
        )

    return PaginatedReplayList(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


class PlayerStatsResponse(BaseModel):
    """Player stats for a replay."""

    player_id: str
    display_name: str
    team: str
    is_me: bool
    # Fundamentals
    goals: int
    assists: int
    saves: int
    shots: int
    score: int
    demos_inflicted: int
    demos_taken: int
    # Boost
    avg_boost: float | None
    big_pads: int | None
    small_pads: int | None
    boost_stolen: float | None
    time_zero_boost_pct: float | None
    time_full_boost_pct: float | None
    # Movement
    avg_speed_kph: float | None
    time_supersonic_pct: float | None
    # Positioning
    time_offensive_third_pct: float | None
    time_middle_third_pct: float | None
    time_defensive_third_pct: float | None
    behind_ball_pct: float | None
    avg_distance_to_ball_m: float | None
    # Mechanics
    wavedash_count: int | None
    halfflip_count: int | None
    speedflip_count: int | None
    aerial_count: int | None


class ReplayFullDetail(BaseModel):
    """Full replay analysis data."""

    id: str
    filename: str
    status: str
    map_name: str | None
    playlist: str | None
    team_size: int | None
    duration_seconds: float | None
    played_at: str | None
    result: str | None
    my_score: int | None
    opponent_score: int | None
    overtime: bool
    players: list[PlayerStatsResponse]


@router.get("/{replay_id}/analysis", response_model=ReplayFullDetail)
def get_replay_analysis(
    replay_id: str,
    user: AuthenticatedUser,
    db: Annotated[DBSession, Depends(get_session)],
) -> ReplayFullDetail:
    """Get full replay analysis with player stats.

    Returns detailed analysis data including all player stats.
    Requires authentication and ownership of the replay.
    """
    from ...db import Player, PlayerGameStats

    # Check user owns this replay
    ownership = (
        db.query(UserReplay)
        .filter(
            UserReplay.replay_id == replay_id,
            UserReplay.user_id == user.id,
        )
        .first()
    )
    if not ownership:
        raise HTTPException(status_code=404, detail="Replay not found")

    replay = db.query(Replay).filter(Replay.replay_id == replay_id).first()
    if not replay:
        raise HTTPException(status_code=404, detail="Replay not found")

    # Get upload info for filename - SECURITY FIX: filter by user_id
    upload = (
        db.query(UploadedReplay)
        .filter(
            UploadedReplay.replay_id == replay_id,
            UploadedReplay.user_id == user.id,
        )
        .first()
    )
    filename = upload.filename if upload else f"{replay_id}.replay"
    upload_status = upload.status if upload else "processed"

    # Get all player stats for this replay
    player_stats_rows = (
        db.query(PlayerGameStats, Player)
        .join(Player, PlayerGameStats.player_id == Player.player_id)
        .filter(PlayerGameStats.replay_id == replay_id)
        .all()
    )

    players = []
    for pgs, player in player_stats_rows:
        # Calculate percentages from seconds if we have duration
        duration = replay.duration_seconds or 300  # default 5 min
        time_zero_pct = None
        time_full_pct = None
        time_off_pct = None
        time_mid_pct = None
        time_def_pct = None
        time_supersonic_pct = None

        if duration > 0:
            if pgs.time_zero_boost_s is not None:
                time_zero_pct = round(pgs.time_zero_boost_s / duration * 100, 1)
            if pgs.time_full_boost_s is not None:
                time_full_pct = round(pgs.time_full_boost_s / duration * 100, 1)
            if pgs.time_offensive_third_s is not None:
                time_off_pct = round(pgs.time_offensive_third_s / duration * 100, 1)
            if pgs.time_middle_third_s is not None:
                time_mid_pct = round(pgs.time_middle_third_s / duration * 100, 1)
            if pgs.time_defensive_third_s is not None:
                time_def_pct = round(pgs.time_defensive_third_s / duration * 100, 1)
            if pgs.time_supersonic_s is not None:
                time_supersonic_pct = round(pgs.time_supersonic_s / duration * 100, 1)

        players.append(
            PlayerStatsResponse(
                player_id=pgs.player_id,
                display_name=player.display_name,
                team=pgs.team,
                is_me=pgs.is_me or False,
                goals=pgs.goals or 0,
                assists=pgs.assists or 0,
                saves=pgs.saves or 0,
                shots=pgs.shots or 0,
                score=pgs.score or 0,
                demos_inflicted=pgs.demos_inflicted or 0,
                demos_taken=pgs.demos_taken or 0,
                avg_boost=pgs.avg_boost,
                big_pads=pgs.big_pads,
                small_pads=pgs.small_pads,
                boost_stolen=pgs.boost_stolen,
                time_zero_boost_pct=time_zero_pct,
                time_full_boost_pct=time_full_pct,
                avg_speed_kph=pgs.avg_speed_kph,
                time_supersonic_pct=time_supersonic_pct,
                time_offensive_third_pct=time_off_pct,
                time_middle_third_pct=time_mid_pct,
                time_defensive_third_pct=time_def_pct,
                behind_ball_pct=pgs.behind_ball_pct,
                avg_distance_to_ball_m=pgs.avg_distance_to_ball_m,
                wavedash_count=pgs.wavedash_count,
                halfflip_count=pgs.halfflip_count,
                speedflip_count=pgs.speedflip_count,
                aerial_count=pgs.aerial_count,
            )
        )

    played_at = None
    if replay.played_at_utc:
        played_at = replay.played_at_utc.isoformat()

    return ReplayFullDetail(
        id=replay.replay_id,
        filename=filename,
        status=upload_status,
        map_name=replay.map,
        playlist=replay.playlist,
        team_size=replay.team_size,
        duration_seconds=replay.duration_seconds,
        played_at=played_at,
        result=replay.result,
        my_score=replay.my_score,
        opponent_score=replay.opponent_score,
        overtime=replay.overtime or False,
        players=players,
    )


class PlaySessionItem(BaseModel):
    """A play session (group of replays played together)."""

    id: str
    date: str
    duration_minutes: int
    replay_count: int
    wins: int
    losses: int
    avg_goals: float
    avg_saves: float


class PlaySessionList(BaseModel):
    """List of play sessions."""

    sessions: list[PlaySessionItem]
    total: int


@router.get("/sessions", response_model=PlaySessionList)
def list_play_sessions(
    user: AuthenticatedUser,
    db: Annotated[DBSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> PlaySessionList:
    """List the user's play sessions (groups of replays by date).

    Aggregates replays by date to show daily play sessions.
    Requires authentication.
    """
    from sqlalchemy import Integer, func, select

    from ...db import PlayerGameStats

    # Get replay IDs from user_replays (as subquery for efficiency)
    user_replay_ids = select(UserReplay.replay_id).where(UserReplay.user_id == user.id)

    # Use SQL GROUP BY to aggregate data efficiently at the database level
    # instead of loading all replays into memory
    # Use func.date() for SQLite compatibility (returns string) instead of cast(Date)
    play_date = func.date(Replay.played_at_utc).label("play_date")

    session_aggregates = (
        db.query(
            play_date,
            func.count(Replay.replay_id).label("replay_count"),
            func.sum(
                func.cast(
                    (Replay.result == "WIN"),
                    Integer,
                )
            ).label("wins"),
            func.sum(
                func.cast(
                    (Replay.result == "LOSS"),
                    Integer,
                )
            ).label("losses"),
            func.sum(Replay.duration_seconds).label("total_duration"),
        )
        .filter(
            Replay.replay_id.in_(user_replay_ids),
            Replay.played_at_utc.isnot(None),
        )
        .group_by(play_date)
        .order_by(play_date.desc())
        .limit(limit)
        .all()
    )

    if not session_aggregates:
        return PlaySessionList(sessions=[], total=0)

    # Get player stats aggregated by date for avg goals/saves
    stats_by_date = {}
    for date_str, _count, _wins, _losses, _duration in session_aggregates:
        # Query stats for this date's replays
        date_replays = (
            db.query(Replay.replay_id)
            .filter(
                Replay.replay_id.in_(user_replay_ids),
                func.date(Replay.played_at_utc) == date_str,
            )
            .subquery()
        )

        stats_agg = (
            db.query(
                func.avg(PlayerGameStats.goals).label("avg_goals"),
                func.avg(PlayerGameStats.saves).label("avg_saves"),
            )
            .filter(
                PlayerGameStats.replay_id.in_(date_replays),
                PlayerGameStats.is_me == True,  # noqa: E712
            )
            .first()
        )

        stats_by_date[date_str] = stats_agg

    # Build response
    sessions = []
    total_sessions = 0
    for date_val, count, wins, losses, duration in session_aggregates:
        total_sessions += 1
        stats = stats_by_date.get(date_val)
        avg_goals = round(float(stats.avg_goals or 0), 1) if stats else 0.0
        avg_saves = round(float(stats.avg_saves or 0), 1) if stats else 0.0

        # date_val is a string (YYYY-MM-DD) from func.date() in SQLite
        date_str = date_val if isinstance(date_val, str) else date_val.isoformat()
        sessions.append(
            PlaySessionItem(
                id=date_str,
                date=date_str,
                duration_minutes=int((duration or 0) / 60),
                replay_count=count or 0,
                wins=wins or 0,
                losses=losses or 0,
                avg_goals=avg_goals,
                avg_saves=avg_saves,
            )
        )

    return PlaySessionList(sessions=sessions, total=total_sessions)
