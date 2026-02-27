# src/rlcoach/api/routers/gdpr.py
"""GDPR compliance endpoints for data removal requests.

Allows third parties to request removal of their data from replays
where they appear as a player (e.g., opponent in someone else's upload).
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session as DBSession

from ...db import get_session
from ...db.models import GDPRRemovalRequest, Player, PlayerGameStats
from ..auth import AuthenticatedUser
from ..rate_limit import check_rate_limit, rate_limit_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/gdpr", tags=["gdpr"])

# Admin user IDs allowed to process removal requests.
# Set GDPR_ADMIN_USER_IDS as comma-separated list of user UUIDs.
_ADMIN_IDS: set[str] | None = None


def _get_admin_ids() -> set[str]:
    global _ADMIN_IDS
    if _ADMIN_IDS is None:
        raw = os.getenv("GDPR_ADMIN_USER_IDS", "")
        _ADMIN_IDS = {uid.strip() for uid in raw.split(",") if uid.strip()}
    return _ADMIN_IDS


def _require_admin(user: AuthenticatedUser) -> None:
    """Raise 403 if the authenticated user is not a GDPR admin."""
    admin_ids = _get_admin_ids()
    if not admin_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No GDPR admins configured. Set GDPR_ADMIN_USER_IDS.",
        )
    if user.id not in admin_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required to process removal requests.",
        )


class RemovalRequest(BaseModel):
    """GDPR data removal request."""

    # Player identifier (Steam ID, Epic ID, or display name)
    player_identifier: str
    identifier_type: str  # "steam_id", "epic_id", "display_name"

    # Contact email for confirmation
    email: str

    # Reason for request (optional)
    reason: str | None = None

    @field_validator("identifier_type")
    @classmethod
    def validate_identifier_type(cls, v: str) -> str:
        allowed = {"steam_id", "epic_id", "display_name"}
        if v not in allowed:
            raise ValueError(f"identifier_type must be one of: {allowed}")
        return v

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        # Basic email validation
        email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        if not re.match(email_pattern, v):
            raise ValueError("Invalid email format")
        return v.lower()

    @field_validator("player_identifier")
    @classmethod
    def validate_identifier(cls, v: str) -> str:
        # Sanitize and validate identifier
        v = v.strip()
        if len(v) < 3 or len(v) > 100:
            raise ValueError("Player identifier must be 3-100 characters")
        # Remove potentially dangerous characters
        v = re.sub(r"[<>\"'&;]", "", v)
        return v


class RemovalRequestResponse(BaseModel):
    """Response to a removal request."""

    status: str
    request_id: str
    message: str
    affected_replays: int


class RemovalRequestStatus(BaseModel):
    """Status of a removal request."""

    request_id: str
    status: str  # "pending", "approved", "completed", "rejected"
    submitted_at: str
    processed_at: str | None
    affected_replays: int


def _generate_request_id(email: str, identifier: str) -> str:
    """Generate a deterministic request ID."""
    key = f"{email}:{identifier}:{datetime.now(timezone.utc).date().isoformat()}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _count_affected(db: DBSession, identifier_type: str, player_identifier: str) -> int:
    """Count PlayerGameStats rows affected by a removal request."""
    if identifier_type in ("steam_id", "epic_id"):
        prefix = "steam" if identifier_type == "steam_id" else "epic"
        prefixed_id = f"{prefix}:{player_identifier}"
        return (
            db.query(PlayerGameStats)
            .join(Player, PlayerGameStats.player_id == Player.player_id)
            .filter(Player.player_id == prefixed_id)
            .count()
        )
    elif identifier_type == "display_name":
        return (
            db.query(PlayerGameStats)
            .join(Player, PlayerGameStats.player_id == Player.player_id)
            .filter(Player.display_name.ilike(player_identifier))
            .count()
        )
    return 0


@router.post("/removal-request", response_model=RemovalRequestResponse)
async def submit_removal_request(
    request: RemovalRequest,
    db: Annotated[DBSession, Depends(get_session)],
) -> RemovalRequestResponse:
    """Submit a GDPR data removal request.

    Allows any person to request removal of their player data from
    replays where they appear. No authentication required.

    The request will be reviewed and processed within 30 days
    as required by GDPR.
    """
    # Rate limit by IP (prevent abuse)
    rate_result = check_rate_limit(request.email, "gdpr")
    if not rate_result.allowed:
        raise rate_limit_response(rate_result)

    affected_count = _count_affected(
        db, request.identifier_type, request.player_identifier
    )

    request_id = _generate_request_id(request.email, request.player_identifier)

    # Check for existing request with same ID
    existing = db.get(GDPRRemovalRequest, request_id)
    if existing:
        return RemovalRequestResponse(
            status=existing.status,
            request_id=request_id,
            message=(
                f"A removal request already exists (status: {existing.status}). "
                f"Affected replays: {existing.affected_count}."
            ),
            affected_replays=existing.affected_count,
        )

    # Persist to database
    removal = GDPRRemovalRequest(
        id=request_id,
        email=request.email,
        player_identifier=request.player_identifier,
        identifier_type=request.identifier_type,
        reason=request.reason,
        status="pending",
        affected_count=affected_count,
    )
    db.add(removal)
    db.commit()

    logger.info(
        f"GDPR removal request submitted: {request_id} "
        f"for {request.identifier_type}={request.player_identifier}, "
        f"affecting {affected_count} replays"
    )

    return RemovalRequestResponse(
        status="submitted",
        request_id=request_id,
        message=(
            f"Your removal request has been submitted. "
            f"We found {affected_count} replay(s) containing your data. "
            f"You will receive a confirmation email at {request.email} "
            f"once your request is processed (within 30 days)."
        ),
        affected_replays=affected_count,
    )


@router.get("/removal-request/{request_id}", response_model=RemovalRequestStatus)
async def get_removal_request_status(
    request_id: str,
    db: Annotated[DBSession, Depends(get_session)],
) -> RemovalRequestStatus:
    """Check the status of a removal request."""
    req = db.get(GDPRRemovalRequest, request_id)
    if not req:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Removal request not found",
        )

    return RemovalRequestStatus(
        request_id=request_id,
        status=req.status,
        submitted_at=req.submitted_at.isoformat(),
        processed_at=req.processed_at.isoformat() if req.processed_at else None,
        affected_replays=req.affected_count,
    )


@router.post("/removal-request/{request_id}/process")
async def process_removal_request(
    request_id: str,
    user: AuthenticatedUser,
    db: Annotated[DBSession, Depends(get_session)],
) -> dict:
    """Process a pending removal request (admin only).

    Anonymizes player data in affected replays.
    Requires admin authentication via GDPR_ADMIN_USER_IDS env var.
    """
    _require_admin(user)

    req = db.get(GDPRRemovalRequest, request_id)
    if not req:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Removal request not found",
        )

    if req.status != "pending":
        return {"status": req.status, "message": "Request already processed"}

    # Anonymize player data
    anonymized_count = 0

    try:
        if req.identifier_type in ("steam_id", "epic_id"):
            prefix = "steam" if req.identifier_type == "steam_id" else "epic"
            prefixed_id = f"{prefix}:{req.player_identifier}"
            result = (
                db.query(Player)
                .filter(Player.player_id == prefixed_id)
                .update(
                    {"display_name": f"[Removed Player {request_id[:8]}]"},
                    synchronize_session=False,
                )
            )
            anonymized_count = result
        elif req.identifier_type == "display_name":
            result = (
                db.query(Player)
                .filter(Player.display_name.ilike(req.player_identifier))
                .update(
                    {"display_name": f"[Removed Player {request_id[:8]}]"},
                    synchronize_session=False,
                )
            )
            anonymized_count = result

        # Update request status
        req.status = "completed"
        req.processed_at = datetime.now(timezone.utc)
        req.processed_by = user.id

        db.commit()

        logger.info(
            f"GDPR removal request completed: {request_id} by user {user.id}, "
            f"anonymized {anonymized_count} records"
        )

        return {
            "status": "completed",
            "request_id": request_id,
            "anonymized_count": anonymized_count,
        }

    except Exception as e:
        db.rollback()
        logger.exception(f"Error processing removal request {request_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process removal request",
        ) from e
