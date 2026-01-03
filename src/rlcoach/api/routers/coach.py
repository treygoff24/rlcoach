# src/rlcoach/api/routers/coach.py
"""AI Coach API endpoints.

All endpoints require Pro subscription tier.
Uses Claude Opus 4.5 with extended thinking for deep analysis.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from ...db import CoachMessage, CoachNote, CoachSession, User, get_session
from ..auth import ProUser

router = APIRouter(prefix="/api/v1/coach", tags=["coach"])

# Token costs for Claude Opus 4.5
INPUT_TOKEN_COST = 0.015 / 1000  # $15 per million input tokens
OUTPUT_TOKEN_COST = 0.075 / 1000  # $75 per million output tokens
MONTHLY_TOKEN_BUDGET = 500_000  # Default Pro budget


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


class SessionListItem(BaseModel):
    """Coach session list item."""

    id: str
    title: str | None
    created_at: str
    message_count: int


class NoteRequest(BaseModel):
    """Coach note request."""

    content: str
    replay_id: str | None = None


class NoteResponse(BaseModel):
    """Coach note response."""

    id: str
    content: str
    is_ai_generated: bool
    created_at: str
    replay_id: str | None


@router.post("/chat", response_model=MessageResponse)
async def send_message(
    request: MessageRequest,
    user: ProUser,
    db: Annotated[DBSession, Depends(get_session)],
) -> MessageResponse:
    """Send a message to the AI coach.

    Creates a new session if session_id is not provided.
    Requires Pro subscription.
    """
    # Check token budget
    db_user = db.query(User).filter(User.id == user.id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    if db_user.token_budget_remaining <= 0:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Monthly token budget exhausted. Resets next billing cycle.",
        )

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
            raise HTTPException(status_code=404, detail="Session not found")
    else:
        session = CoachSession(
            id=str(uuid.uuid4()),
            user_id=user.id,
            title=request.message[:100] if request.message else "New Session",
            replay_id=request.replay_id,
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
    try:
        response_content, thinking, tokens_used = await _get_coach_response(
            user_message=request.message,
            history=previous_messages,
            replay_id=request.replay_id,
            user_notes=_get_user_notes(db, user.id),
            user_id=user.id,
            db=db,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI service error: {str(e)}",
        ) from e

    # Store user message
    user_msg = CoachMessage(
        id=str(uuid.uuid4()),
        session_id=session.id,
        role="user",
        content=request.message,
    )
    db.add(user_msg)

    # Store assistant message
    assistant_msg = CoachMessage(
        id=str(uuid.uuid4()),
        session_id=session.id,
        role="assistant",
        content=response_content,
        thinking_content=thinking,
        input_tokens=tokens_used.get("input", 0),
        output_tokens=tokens_used.get("output", 0),
    )
    db.add(assistant_msg)

    # Update user token budget
    total_tokens = tokens_used.get("input", 0) + tokens_used.get("output", 0)
    new_budget = max(0, db_user.token_budget_remaining - total_tokens)
    db_user.token_budget_remaining = new_budget
    db_user.updated_at = datetime.now(timezone.utc)

    # Update session
    session.updated_at = datetime.now(timezone.utc)
    session.total_tokens += total_tokens

    db.commit()

    return MessageResponse(
        session_id=session.id,
        message_id=assistant_msg.id,
        content=response_content,
        thinking=thinking,
        tokens_used=total_tokens,
        budget_remaining=db_user.token_budget_remaining,
    )


@router.get("/sessions", response_model=list[SessionListItem])
async def list_sessions(
    user: ProUser,
    db: Annotated[DBSession, Depends(get_session)],
    limit: int = 20,
    offset: int = 0,
) -> list[SessionListItem]:
    """List the user's coach sessions.

    Requires Pro subscription.
    """
    sessions = (
        db.query(CoachSession)
        .filter(CoachSession.user_id == user.id)
        .order_by(CoachSession.updated_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )

    result = []
    for session in sessions:
        message_count = (
            db.query(CoachMessage).filter(CoachMessage.session_id == session.id).count()
        )
        result.append(
            SessionListItem(
                id=session.id,
                title=session.title,
                created_at=session.created_at.isoformat(),
                message_count=message_count,
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

    return [
        {
            "id": msg.id,
            "role": msg.role,
            "content": msg.content,
            "thinking": msg.thinking_content,
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
    note = CoachNote(
        id=str(uuid.uuid4()),
        user_id=user.id,
        content=request.content,
        replay_id=request.replay_id,
        is_ai_generated=False,
    )
    db.add(note)
    db.commit()
    db.refresh(note)

    return NoteResponse(
        id=note.id,
        content=note.content,
        is_ai_generated=note.is_ai_generated,
        created_at=note.created_at.isoformat(),
        replay_id=note.replay_id,
    )


@router.get("/notes", response_model=list[NoteResponse])
async def list_notes(
    user: ProUser,
    db: Annotated[DBSession, Depends(get_session)],
    replay_id: str | None = None,
) -> list[NoteResponse]:
    """List coaching notes.

    Optionally filter by replay_id.
    Requires Pro subscription.
    """
    query = db.query(CoachNote).filter(CoachNote.user_id == user.id)

    if replay_id:
        query = query.filter(CoachNote.replay_id == replay_id)

    notes = query.order_by(CoachNote.created_at.desc()).all()

    return [
        NoteResponse(
            id=note.id,
            content=note.content,
            is_ai_generated=note.is_ai_generated,
            created_at=note.created_at.isoformat(),
            replay_id=note.replay_id,
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

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })

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
    }

    return response_text, thinking_text, token_counts
