# src/rlcoach/api/routers/replays.py
"""Replay upload and management API endpoints.

Handles replay file uploads, processing status, and retrieval.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from ...db import Replay, UploadedReplay, UserReplay, get_session
from ..auth import AuthenticatedUser

router = APIRouter(prefix="/api/v1/replays", tags=["replays"])

# Upload limits
MAX_REPLAY_SIZE = 50 * 1024 * 1024  # 50MB
ALLOWED_EXTENSIONS = {".replay"}


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
    filename: str
    status: str
    played_at: str | None
    map_name: str | None
    playlist: str | None
    team_size: int | None
    created_at: str


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
    # Validate filename
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename required")

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # Read and validate file
    content = await file.read()
    if len(content) > MAX_REPLAY_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size: {MAX_REPLAY_SIZE // (1024*1024)}MB",
        )

    if len(content) < 1000:
        raise HTTPException(
            status_code=400, detail="File too small to be a valid replay"
        )

    # Compute SHA256
    sha256 = hashlib.sha256(content).hexdigest()

    # Check for duplicate
    existing = (
        db.query(UploadedReplay)
        .filter(
            UploadedReplay.user_id == user.id,
            UploadedReplay.sha256 == sha256,
        )
        .first()
    )
    if existing:
        return ReplayUploadResponse(
            upload_id=existing.id,
            status=existing.status,
            filename=existing.original_filename,
            size=existing.file_size,
            sha256=existing.sha256,
        )

    # Save file to upload directory
    upload_dir = Path(os.getenv("UPLOAD_DIR", "/tmp/rlcoach/uploads"))
    upload_dir.mkdir(parents=True, exist_ok=True)

    upload_id = str(uuid.uuid4())
    file_path = upload_dir / f"{upload_id}.replay"
    file_path.write_bytes(content)

    # Create upload record
    upload = UploadedReplay(
        id=upload_id,
        user_id=user.id,
        original_filename=file.filename,
        stored_path=str(file_path),
        file_size=len(content),
        sha256=sha256,
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
        filename=file.filename,
        size=len(content),
        sha256=sha256,
    )


@router.get("/uploads", response_model=list[ReplayListItem])
async def list_uploads(
    user: AuthenticatedUser,
    db: Annotated[DBSession, Depends(get_session)],
    status_filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[ReplayListItem]:
    """List the user's uploaded replays.

    Requires authentication.
    """
    query = db.query(UploadedReplay).filter(UploadedReplay.user_id == user.id)

    if status_filter:
        query = query.filter(UploadedReplay.status == status_filter)

    uploads = (
        query.order_by(UploadedReplay.created_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )

    result = []
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

        result.append(
            ReplayListItem(
                id=upload.id,
                filename=upload.original_filename,
                status=upload.status,
                played_at=played_at,
                map_name=replay.map_name if replay else None,
                playlist=replay.playlist if replay else None,
                team_size=replay.team_size if replay else None,
                created_at=upload.created_at.isoformat(),
            )
        )

    return result


@router.get("/uploads/{upload_id}", response_model=ReplayDetail)
async def get_upload(
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
        filename=upload.original_filename,
        status=upload.status,
        error_message=upload.error_message,
        played_at=played_at,
        map_name=replay.map_name if replay else None,
        playlist=replay.playlist if replay else None,
        team_size=replay.team_size if replay else None,
        duration_seconds=replay.duration_seconds if replay else None,
        created_at=upload.created_at.isoformat(),
        processed_at=processed_at,
    )


@router.delete("/uploads/{upload_id}")
async def delete_upload(
    upload_id: str,
    user: AuthenticatedUser,
    db: Annotated[DBSession, Depends(get_session)],
) -> dict:
    """Delete an uploaded replay.

    Removes the file and database records. Requires authentication.
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

    # Delete file if exists
    if upload.stored_path:
        file_path = Path(upload.stored_path)
        if file_path.exists():
            file_path.unlink()

    # Remove user-replay association if exists
    if upload.replay_id:
        db.query(UserReplay).filter(
            UserReplay.replay_id == upload.replay_id,
            UserReplay.user_id == user.id,
        ).delete()

    # Delete upload record
    db.delete(upload)
    db.commit()

    return {"status": "deleted"}


@router.get("/library", response_model=list[ReplayListItem])
async def list_library(
    user: AuthenticatedUser,
    db: Annotated[DBSession, Depends(get_session)],
    limit: int = 50,
    offset: int = 0,
) -> list[ReplayListItem]:
    """List all replays in the user's library.

    Includes both uploaded and shared replays.
    Requires authentication.
    """
    # Get replay IDs from user_replays
    user_replay_ids = (
        db.query(UserReplay.replay_id).filter(UserReplay.user_id == user.id).subquery()
    )

    replays = (
        db.query(Replay)
        .filter(Replay.replay_id.in_(user_replay_ids))
        .order_by(Replay.played_at_utc.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )

    # Get upload info for each replay
    result = []
    for replay in replays:
        upload = (
            db.query(UploadedReplay)
            .filter(UploadedReplay.replay_id == replay.replay_id)
            .first()
        )

        # Build field values with proper null handling
        filename = f"{replay.replay_id}.replay"
        if upload:
            filename = upload.original_filename
        status = upload.status if upload else "processed"
        played_at = None
        if replay.played_at_utc:
            played_at = replay.played_at_utc.isoformat()
        created_at = replay.created_at.isoformat()
        if upload:
            created_at = upload.created_at.isoformat()

        result.append(
            ReplayListItem(
                id=replay.replay_id,
                filename=filename,
                status=status,
                played_at=played_at,
                map_name=replay.map_name,
                playlist=replay.playlist,
                team_size=replay.team_size,
                created_at=created_at,
            )
        )

    return result
