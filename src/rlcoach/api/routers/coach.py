# src/rlcoach/api/routers/coach.py
"""AI Coach API endpoints.

Pro subscription required for full access.
Free tier users get 1 complimentary message to preview the coach.
Uses Claude Opus 4.5 with extended thinking for deep analysis.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from ...db import CoachMessage, CoachNote, CoachSession, User, get_session
from ...services.coach.budget import (
    abort_reservation,
    estimate_request_tokens,
    finalize_reservation,
    get_token_budget_remaining,
    release_expired_reservations,
    reserve_tokens,
)
from ...services.coach.prompts import build_system_prompt, get_tool_descriptions
from ...services.coach.tools import execute_tool
from ..auth import AuthenticatedUser, ProUser
from ..rate_limit import check_rate_limit, rate_limit_response
from ..security import sanitize_note_content, sanitize_string

logger = logging.getLogger(__name__)

# Valid note categories
ALLOWED_NOTE_CATEGORIES = {"strength", "weakness", "goal", "observation", None}

router = APIRouter(prefix="/api/v1/coach", tags=["coach"])


class ChatPreflightRequest(BaseModel):
    """Chat preflight request."""

    message: str
    session_id: str | None = None
    replay_id: str | None = None


class ChatPreflightResponse(BaseModel):
    """Chat preflight response payload."""

    session_id: str
    budget_remaining: int
    is_free_preview: bool
    history: list[dict]
    system_message: str
    estimated_tokens: int
    reservation_id: str


class ChatRecordMessage(BaseModel):
    """Chat message payload for recording."""

    role: str
    content_blocks: list[dict]
    content_text: str | None = None


class ChatRecordRequest(BaseModel):
    """Record coach chat messages after streaming finishes."""

    session_id: str
    reservation_id: str
    messages: list[ChatRecordMessage]
    tokens_used: int
    estimated_tokens: int
    is_free_preview: bool


class ChatAbortRequest(BaseModel):
    """Abort request to release token reservation."""

    session_id: str
    reservation_id: str
    partial_messages: list[ChatRecordMessage] | None = None


class SessionListItem(BaseModel):
    """Coach session list item."""

    id: str
    started_at: str
    message_count: int


class NoteRequest(BaseModel):
    """Coach note request."""

    content: str
    category: str | None = None


class NoteResponse(BaseModel):
    """Coach note response."""

    id: str
    content: str
    source: str
    category: str | None
    created_at: str


class ToolExecuteRequest(BaseModel):
    """Tool execution request."""

    tool_name: str
    tool_input: dict


@router.get("/tools/schema")
async def get_coach_tool_schema(user: AuthenticatedUser) -> dict:
    """Return available coach tools schema."""
    return {"tools": get_tool_descriptions()}


@router.post("/tools/execute")
async def execute_coach_tool(
    request: ToolExecuteRequest,
    user: AuthenticatedUser,
    db: Annotated[DBSession, Depends(get_session)],
) -> dict:
    """Execute a coach tool and return results."""
    result_json = await execute_tool(
        tool_name=request.tool_name,
        tool_input=request.tool_input,
        user_id=user.id,
        db=db,
    )
    return {"tool_name": request.tool_name, "result": json.loads(result_json)}


@router.post("/chat/preflight", response_model=ChatPreflightResponse)
async def chat_preflight(
    request: ChatPreflightRequest,
    user: AuthenticatedUser,
    db: Annotated[DBSession, Depends(get_session)],
) -> ChatPreflightResponse:
    """Preflight chat request, reserve tokens, and return context."""
    rate_result = check_rate_limit(user.id, "chat")
    if not rate_result.allowed:
        raise rate_limit_response(rate_result)

    if len(request.message) > 10000:
        raise HTTPException(
            status_code=400, detail="Message too long. Maximum 10,000 characters."
        )

    stmt = select(User).where(User.id == user.id).with_for_update()
    db_user = db.execute(stmt).scalar_one_or_none()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    is_pro = db_user.subscription_tier == "pro"
    is_free_preview = False

    if not is_pro:
        if db_user.free_coach_message_used:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=(
                    "You've used your free coach preview. "
                    "Upgrade to Pro for unlimited coaching at $10/month."
                ),
            )
        is_free_preview = True

    if request.session_id:
        session = (
            db.query(CoachSession)
            .filter(
                CoachSession.id == request.session_id,
                CoachSession.user_id == user.id,
            )
            .first()
        )
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
    else:
        session = CoachSession(
            id=str(uuid.uuid4()),
            user_id=user.id,
        )
        db.add(session)
        db.flush()

    release_expired_reservations(db_user, db)

    previous_messages = (
        db.query(CoachMessage)
        .filter(CoachMessage.session_id == session.id)
        .order_by(CoachMessage.created_at)
        .all()
    )

    history = [
        {
            "role": msg.role,
            "content": _parse_content_blocks(msg.content_json, msg.content or ""),
        }
        for msg in previous_messages
    ]

    estimated_tokens = estimate_request_tokens(
        message_length=len(request.message),
        history_messages=len(previous_messages),
        include_tools=True,
    )

    budget_remaining = get_token_budget_remaining(db_user)
    if budget_remaining <= 0:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Monthly token budget exhausted. Resets next billing cycle.",
        )

    if estimated_tokens > budget_remaining:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                f"Insufficient token budget. "
                f"Estimated: {estimated_tokens}, remaining: {budget_remaining}."
            ),
        )

    reservation_id = reserve_tokens(
        user=db_user,
        session_id=session.id,
        estimated_tokens=estimated_tokens,
        db=db,
    )
    db.refresh(db_user)

    system_message = build_system_prompt(
        user_notes=_get_user_notes(db, user.id),
        player_name=db_user.display_name,
    )

    return ChatPreflightResponse(
        session_id=session.id,
        budget_remaining=get_token_budget_remaining(db_user),
        is_free_preview=is_free_preview,
        history=history,
        system_message=system_message,
        estimated_tokens=estimated_tokens,
        reservation_id=reservation_id,
    )


@router.post("/chat/record")
async def chat_record(
    request: ChatRecordRequest,
    user: AuthenticatedUser,
    db: Annotated[DBSession, Depends(get_session)],
) -> dict:
    """Record chat messages and finalize reservation."""
    db_user = db.query(User).filter(User.id == user.id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    session = (
        db.query(CoachSession)
        .filter(
            CoachSession.id == request.session_id,
            CoachSession.user_id == user.id,
        )
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    for message in request.messages:
        content_blocks = message.content_blocks or []
        content_text = message.content_text or _extract_text_from_blocks(content_blocks)

        max_length = 10000 if message.role == "user" else 50000
        safe_text = sanitize_string(
            content_text,
            max_length=max_length,
            allow_newlines=True,
            strip_html=True,
            preserve_formatting=True,
        )

        db.add(
            CoachMessage(
                id=str(uuid.uuid4()),
                session_id=session.id,
                role=message.role,
                content=safe_text,
                content_json=json.dumps(content_blocks),
            )
        )

    session.message_count = (session.message_count or 0) + len(request.messages)
    session.total_output_tokens = (
        session.total_output_tokens or 0
    ) + request.tokens_used

    if request.is_free_preview:
        db_user.free_coach_message_used = True

    finalize_reservation(
        user=db_user,
        reservation_id=request.reservation_id,
        tokens_used=request.tokens_used,
        db=db,
    )

    return {"recorded": True}


@router.post("/chat/abort")
async def chat_abort(
    request: ChatAbortRequest,
    user: AuthenticatedUser,
    db: Annotated[DBSession, Depends(get_session)],
) -> dict:
    """Abort a chat and release reserved tokens."""
    db_user = db.query(User).filter(User.id == user.id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    session = (
        db.query(CoachSession)
        .filter(
            CoachSession.id == request.session_id,
            CoachSession.user_id == user.id,
        )
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if request.partial_messages:
        for message in request.partial_messages:
            content_blocks = message.content_blocks or []
            content_text = message.content_text or _extract_text_from_blocks(
                content_blocks
            )

            safe_text = sanitize_string(
                content_text,
                max_length=50000,
                allow_newlines=True,
                strip_html=True,
                preserve_formatting=True,
            )

            db.add(
                CoachMessage(
                    id=str(uuid.uuid4()),
                    session_id=session.id,
                    role=message.role,
                    content=safe_text,
                    content_json=json.dumps(content_blocks),
                )
            )

        session.message_count = (session.message_count or 0) + len(
            request.partial_messages
        )

    abort_reservation(
        user=db_user,
        reservation_id=request.reservation_id,
        db=db,
    )

    return {"aborted": True}


@router.get("/sessions", response_model=list[SessionListItem])
async def list_sessions(
    user: ProUser,
    db: Annotated[DBSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[SessionListItem]:
    """List the user's coach sessions.

    Requires Pro subscription.
    """
    sessions = (
        db.query(CoachSession)
        .filter(CoachSession.user_id == user.id)
        .order_by(CoachSession.started_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )

    result = []
    for session in sessions:
        result.append(
            SessionListItem(
                id=session.id,
                started_at=session.started_at.isoformat(),
                message_count=session.message_count or 0,
            )
        )

    return result


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(
    session_id: str,
    user: ProUser,
    db: Annotated[DBSession, Depends(get_session)],
) -> list[dict]:
    """Get all messages in a coach session.

    Requires Pro subscription.
    """
    session = (
        db.query(CoachSession)
        .filter(
            CoachSession.id == session_id,
            CoachSession.user_id == user.id,
        )
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = (
        db.query(CoachMessage)
        .filter(CoachMessage.session_id == session_id)
        .order_by(CoachMessage.created_at)
        .all()
    )

    # Note: Content is sanitized on storage now. Avoid re-sanitizing on retrieval
    # as that would double-escape entities and corrupt formatting.
    # Frontend uses React which escapes HTML by default when rendering text.
    # Legacy pre-sanitization messages are handled by React's auto-escaping.
    return [
        {
            "id": msg.id,
            "role": msg.role,
            "content": msg.content or "",
            "content_blocks": _parse_content_blocks(msg.content_json, msg.content or ""),
            "created_at": msg.created_at.isoformat(),
        }
        for msg in messages
    ]


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    user: ProUser,
    db: Annotated[DBSession, Depends(get_session)],
) -> dict:
    """Delete a coach session and all its messages.

    Requires Pro subscription.
    """
    session = (
        db.query(CoachSession)
        .filter(
            CoachSession.id == session_id,
            CoachSession.user_id == user.id,
        )
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Delete messages first
    db.query(CoachMessage).filter(CoachMessage.session_id == session_id).delete()
    db.delete(session)
    db.commit()

    return {"status": "deleted"}


class SessionRecapResponse(BaseModel):
    """Session recap response."""

    session_id: str
    message_count: int
    strengths: list[str]
    weaknesses: list[str]
    action_items: list[str]
    summary: str


@router.get("/sessions/{session_id}/recap", response_model=SessionRecapResponse)
async def get_session_recap(
    session_id: str,
    user: AuthenticatedUser,
    db: Annotated[DBSession, Depends(get_session)],
) -> SessionRecapResponse:
    """Generate a structured recap of a coaching session.

    Requires at least 3 messages in the session.
    Available to both free and pro users for sessions they participated in.
    """
    # Get session
    session = (
        db.query(CoachSession)
        .filter(
            CoachSession.id == session_id,
            CoachSession.user_id == user.id,
        )
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Get messages
    messages = (
        db.query(CoachMessage)
        .filter(CoachMessage.session_id == session_id)
        .order_by(CoachMessage.created_at)
        .all()
    )

    if len(messages) < 3:
        raise HTTPException(
            status_code=400,
            detail="Session needs at least 3 messages to generate a recap",
        )

    # Extract insights from assistant messages
    strengths = []
    weaknesses = []
    action_items = []

    # Keyword sets for extraction
    strength_kws = ["strength", "good at", "well done", "excellent", "impressive"]
    weakness_kws = ["weakness", "improve", "work on", "focus on", "lacking"]
    action_kws = ["practice", "try", "recommend", "should", "drill"]

    for msg in messages:
        if msg.role != "assistant" or not msg.content:
            continue

        content = msg.content.lower()

        # Simple keyword extraction for strengths
        if any(kw in content for kw in strength_kws):
            # Extract a summary sentence
            for sentence in msg.content.split("."):
                if any(kw in sentence.lower() for kw in strength_kws[:4]):
                    cleaned = sentence.strip()
                    if cleaned and len(cleaned) > 10:
                        strengths.append(cleaned[:200])
                        break

        # Simple keyword extraction for weaknesses
        if any(kw in content for kw in weakness_kws):
            for sentence in msg.content.split("."):
                if any(kw in sentence.lower() for kw in weakness_kws[:4]):
                    cleaned = sentence.strip()
                    if cleaned and len(cleaned) > 10:
                        weaknesses.append(cleaned[:200])
                        break

        # Simple keyword extraction for action items
        if any(kw in content for kw in action_kws):
            for sentence in msg.content.split("."):
                if any(kw in sentence.lower() for kw in action_kws[:4]):
                    cleaned = sentence.strip()
                    if cleaned and len(cleaned) > 10:
                        action_items.append(cleaned[:200])
                        break

    # Deduplicate
    strengths = list(dict.fromkeys(strengths))[:5]
    weaknesses = list(dict.fromkeys(weaknesses))[:5]
    action_items = list(dict.fromkeys(action_items))[:5]

    # Generate summary
    summary = f"Coaching session with {len(messages)} messages. "
    if strengths:
        summary += f"Identified {len(strengths)} strength(s). "
    if weaknesses:
        summary += f"Found {len(weaknesses)} area(s) to improve. "
    if action_items:
        summary += f"Suggested {len(action_items)} action item(s)."

    return SessionRecapResponse(
        session_id=session_id,
        message_count=len(messages),
        strengths=strengths,
        weaknesses=weaknesses,
        action_items=action_items,
        summary=summary.strip(),
    )


# --- Notes endpoints ---


@router.post("/notes", response_model=NoteResponse)
async def create_note(
    request: NoteRequest,
    user: ProUser,
    db: Annotated[DBSession, Depends(get_session)],
) -> NoteResponse:
    """Create a coaching note.

    Notes persist across sessions and inform future coaching.
    Requires Pro subscription.
    """
    # Rate limit check (20 notes per minute per user)
    rate_result = check_rate_limit(user.id, "notes")
    if not rate_result.allowed:
        raise rate_limit_response(rate_result)

    # Validate category
    if request.category is not None and request.category not in ALLOWED_NOTE_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail="Invalid category. Allowed: strength, weakness, goal, observation",
        )

    # Sanitize content to prevent XSS
    safe_content = sanitize_note_content(request.content)
    if not safe_content:
        raise HTTPException(status_code=400, detail="Note content is required")

    note = CoachNote(
        id=str(uuid.uuid4()),
        user_id=user.id,
        content=safe_content,
        source="user",
        category=request.category,
    )
    db.add(note)
    db.commit()
    db.refresh(note)

    return NoteResponse(
        id=note.id,
        content=note.content,
        source=note.source,
        category=note.category,
        created_at=note.created_at.isoformat(),
    )


@router.get("/notes", response_model=list[NoteResponse])
async def list_notes(
    user: ProUser,
    db: Annotated[DBSession, Depends(get_session)],
    category: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[NoteResponse]:
    """List coaching notes.

    Optionally filter by category.
    Requires Pro subscription.
    """
    query = db.query(CoachNote).filter(CoachNote.user_id == user.id)

    if category:
        query = query.filter(CoachNote.category == category)

    notes = (
        query.order_by(CoachNote.created_at.desc()).limit(limit).offset(offset).all()
    )

    return [
        NoteResponse(
            id=note.id,
            content=note.content,
            source=note.source,
            category=note.category,
            created_at=note.created_at.isoformat(),
        )
        for note in notes
    ]


@router.delete("/notes/{note_id}")
async def delete_note(
    note_id: str,
    user: ProUser,
    db: Annotated[DBSession, Depends(get_session)],
) -> dict:
    """Delete a coaching note.

    Requires Pro subscription.
    """
    note = (
        db.query(CoachNote)
        .filter(
            CoachNote.id == note_id,
            CoachNote.user_id == user.id,
        )
        .first()
    )
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")

    db.delete(note)
    db.commit()

    return {"status": "deleted"}


# --- Internal helpers ---


def _parse_content_blocks(
    content_json: str | None,
    fallback_text: str,
) -> list[dict]:
    if content_json:
        try:
            parsed = json.loads(content_json)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            logger.warning("Invalid content_json payload for coach message")
    return [{"type": "text", "text": fallback_text}]


def _extract_text_from_blocks(blocks: list[dict]) -> str:
    parts: list[str] = []
    for block in blocks:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "".join(parts)


def _get_user_notes(db: DBSession, user_id: str) -> list[str]:
    """Get all user notes for context."""
    notes = (
        db.query(CoachNote)
        .filter(CoachNote.user_id == user_id)
        .order_by(CoachNote.created_at.desc())
        .limit(50)
        .all()
    )
    return [note.content for note in notes]

