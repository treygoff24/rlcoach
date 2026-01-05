# src/rlcoach/api/routers/coach.py
"""AI Coach API endpoints.

Pro subscription required for full access.
Free tier users get 1 complimentary message to preview the coach.
Uses Claude Opus 4.5 with extended thinking for deep analysis.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from ...db import CoachMessage, CoachNote, CoachSession, User, get_session
from ...services.coach.budget import (
    estimate_request_tokens,
    get_token_budget_remaining,
)
from ..auth import AuthenticatedUser, ProUser
from ..rate_limit import check_rate_limit, rate_limit_response
from ..security import sanitize_note_content, sanitize_string

logger = logging.getLogger(__name__)

# Valid note categories
ALLOWED_NOTE_CATEGORIES = {"strength", "weakness", "goal", "observation", None}

router = APIRouter(prefix="/api/v1/coach", tags=["coach"])


class MessageRequest(BaseModel):
    """Chat message request."""

    message: str
    session_id: str | None = None
    replay_id: str | None = None


class MessageResponse(BaseModel):
    """Chat message response."""

    session_id: str
    message_id: str
    content: str
    thinking: str | None = None
    tokens_used: int
    budget_remaining: int
    is_free_preview: bool = False  # True if this was the user's free preview message


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


@router.post("/chat", response_model=MessageResponse)
async def send_message(
    request: MessageRequest,
    user: AuthenticatedUser,
    db: Annotated[DBSession, Depends(get_session)],
) -> MessageResponse:
    """Send a message to the AI coach.

    Creates a new session if session_id is not provided.
    Pro users have full access. Free tier users get 1 complimentary message.
    """
    from sqlalchemy import select

    # Rate limit check (30 messages per minute per user)
    rate_result = check_rate_limit(user.id, "chat")
    if not rate_result.allowed:
        raise rate_limit_response(rate_result)

    # Validate message length (prevent abuse)
    if len(request.message) > 10000:
        raise HTTPException(
            status_code=400,
            detail="Message too long. Maximum 10,000 characters."
        )

    # Sanitize message content for storage (XSS prevention)
    safe_message = sanitize_string(
        request.message,
        max_length=10000,
        allow_newlines=True,
        strip_html=True,
        preserve_formatting=True,
    )

    # Use SELECT FOR UPDATE to prevent race conditions on budget
    stmt = select(User).where(User.id == user.id).with_for_update()
    db_user = db.execute(stmt).scalar_one_or_none()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Check subscription tier and free preview eligibility
    is_pro = db_user.subscription_tier == "pro"
    is_free_preview = False

    if not is_pro:
        # Free tier user - check if they've used their free preview
        if db_user.free_coach_message_used:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=(
                    "You've used your free coach preview. "
                    "Upgrade to Pro for unlimited coaching at $10/month."
                ),
            )
        # This will be their free preview message
        is_free_preview = True

    # Get conversation history count for estimation
    history_count = 0
    if request.session_id:
        history_count = (
            db.query(CoachMessage)
            .filter(CoachMessage.session_id == request.session_id)
            .count()
        )

    # Estimate tokens for this request
    estimated_tokens = estimate_request_tokens(
        message_length=len(request.message),
        history_messages=history_count,
        include_tools=True,
    )

    budget_remaining = get_token_budget_remaining(db_user)

    # Check if we have enough budget for estimated usage
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

    # PRE-RESERVE tokens to prevent race condition
    # This ensures concurrent requests can't all pass the budget check
    db_user.token_budget_used = (db_user.token_budget_used or 0) + estimated_tokens
    db.flush()  # Reserve immediately but don't commit yet

    # Get or create session
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
            # Rollback the reservation
            db.rollback()
            raise HTTPException(status_code=404, detail="Session not found")
    else:
        session = CoachSession(
            id=str(uuid.uuid4()),
            user_id=user.id,
        )
        db.add(session)
        db.flush()

    # Build conversation context
    previous_messages = (
        db.query(CoachMessage)
        .filter(CoachMessage.session_id == session.id)
        .order_by(CoachMessage.created_at)
        .all()
    )

    # Get AI response
    # Send raw user message to Claude for best coaching responses
    # (safe_message is only used for storage/return)
    try:
        response_content, thinking, tokens_used = await _get_coach_response(
            user_message=request.message,  # Raw message to Claude
            history=previous_messages,
            replay_id=request.replay_id,
            user_notes=_get_user_notes(db, user.id),
            user_id=user.id,
            db=db,
        )
    except Exception as e:
        # Rollback reservation on failure
        db.rollback()
        logger.exception(f"AI service error for user {user.id}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service temporarily unavailable. Please try again.",
        ) from e

    # Store user message (sanitized)
    user_msg = CoachMessage(
        id=str(uuid.uuid4()),
        session_id=session.id,
        role="user",
        content=safe_message,
    )
    db.add(user_msg)

    # Store assistant message
    input_tokens = tokens_used.get("input", 0)
    output_tokens = tokens_used.get("output", 0)
    thinking_tokens = tokens_used.get("thinking", 0)

    # Sanitize AI response for storage (defense in depth against XSS)
    # Claude won't output malicious HTML, but sanitize to protect against edge cases
    safe_response = sanitize_string(
        response_content,
        max_length=50000,
        allow_newlines=True,
        strip_html=True,
        preserve_formatting=True,  # Keep code block formatting
    )

    assistant_msg = CoachMessage(
        id=str(uuid.uuid4()),
        session_id=session.id,
        role="assistant",
        content=safe_response,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        thinking_tokens=thinking_tokens,
    )
    db.add(assistant_msg)

    # Adjust token budget: replace estimated with actual
    actual_tokens = input_tokens + output_tokens
    # We already added estimated_tokens, so adjust the difference
    token_adjustment = actual_tokens - estimated_tokens
    db_user.token_budget_used = (db_user.token_budget_used or 0) + token_adjustment
    db_user.updated_at = datetime.now(timezone.utc)

    # Mark free preview as used for free tier users
    if is_free_preview:
        db_user.free_coach_message_used = True

    # Update session token counts
    session.total_input_tokens = (session.total_input_tokens or 0) + input_tokens
    session.total_output_tokens = (session.total_output_tokens or 0) + output_tokens
    session.total_thinking_tokens = (
        session.total_thinking_tokens or 0
    ) + thinking_tokens
    session.message_count = (session.message_count or 0) + 2  # user + assistant

    db.commit()

    # Sanitize thinking content if present (defense in depth)
    safe_thinking = None
    if thinking:
        safe_thinking = sanitize_string(
            thinking,
            max_length=100000,
            allow_newlines=True,
            strip_html=True,
            preserve_formatting=True,  # Keep formatting in thinking
        )

    return MessageResponse(
        session_id=session.id,
        message_id=assistant_msg.id,
        content=safe_response,  # Return sanitized content
        thinking=safe_thinking,  # Return sanitized thinking
        tokens_used=actual_tokens,
        budget_remaining=get_token_budget_remaining(db_user),
        is_free_preview=is_free_preview,
    )


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


async def _get_coach_response(
    user_message: str,
    history: list[CoachMessage],
    replay_id: str | None,
    user_notes: list[str],
    user_id: str | None = None,
    db: DBSession | None = None,
) -> tuple[str, str | None, dict[str, int]]:
    """Get response from Claude Opus 4.5.

    Uses extended thinking for deep analysis and tool use for data access.

    Returns:
        Tuple of (response_content, thinking_content, token_counts)
    """
    import anthropic

    from ...services.coach.prompts import build_system_prompt, get_tool_descriptions
    from ...services.coach.tools import execute_tool

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not configured")

    client = anthropic.Anthropic(api_key=api_key)

    # Build system prompt with context
    system = build_system_prompt(user_notes=user_notes)

    # Build messages from history
    messages = []
    for msg in history:
        messages.append({"role": msg.role, "content": msg.content})
    messages.append({"role": "user", "content": user_message})

    # Get tool definitions
    tools = get_tool_descriptions()

    # Initial call with extended thinking and tools
    response = client.messages.create(
        model="claude-opus-4-5-20250514",
        max_tokens=8192,
        thinking={
            "type": "enabled",
            "budget_tokens": 4096,
        },
        system=system,
        messages=messages,
        tools=tools,
    )

    # Track total tokens
    total_input = response.usage.input_tokens
    total_output = response.usage.output_tokens

    # Handle tool use loop (max 5 iterations)
    max_iterations = 5
    iteration = 0

    while response.stop_reason == "tool_use" and iteration < max_iterations:
        iteration += 1

        # Extract tool calls
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                # Execute the tool
                if user_id and db:
                    result = await execute_tool(
                        tool_name=block.name,
                        tool_input=block.input,
                        user_id=user_id,
                        db=db,
                    )
                else:
                    result = '{"error": "Tool execution not available"}'

                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    }
                )

        # Continue conversation with tool results
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

        response = client.messages.create(
            model="claude-opus-4-5-20250514",
            max_tokens=8192,
            thinking={
                "type": "enabled",
                "budget_tokens": 2048,  # Smaller budget for follow-ups
            },
            system=system,
            messages=messages,
            tools=tools,
        )

        total_input += response.usage.input_tokens
        total_output += response.usage.output_tokens

    # Extract final response and thinking
    response_text = ""
    thinking_text = None

    for block in response.content:
        if block.type == "thinking":
            thinking_text = block.thinking
        elif block.type == "text":
            response_text = block.text

    token_counts = {
        "input": total_input,
        "output": total_output,
        "thinking": 0,  # Thinking tokens not counted in usage separately
    }

    return response_text, thinking_text, token_counts
