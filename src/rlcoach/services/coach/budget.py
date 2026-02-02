# src/rlcoach/services/coach/budget.py
"""Token budget management for AI Coach."""

from datetime import datetime, timedelta, timezone

from dateutil.relativedelta import relativedelta
from sqlalchemy.orm import Session as DBSession

from ...db.models import CoachTokenReservation, User

# Monthly token budgets
MONTHLY_TOKEN_BUDGET = 150_000  # 150K tokens per month for Pro users
WARNING_THRESHOLD = 0.80  # Warn at 80% usage

# Per-request limits
MAX_INPUT_TOKENS = 16_000
MAX_OUTPUT_TOKENS = 8_000
EXTENDED_THINKING_BUDGET = 32_000  # Not counted against user budget
RESERVATION_TTL_MINUTES = 5


def get_token_budget_remaining(user: User) -> int:
    """Calculate remaining token budget for a user.

    Args:
        user: User model instance

    Returns:
        Remaining tokens (0 if exhausted)
    """
    used = user.token_budget_used or 0
    return max(0, MONTHLY_TOKEN_BUDGET - used)


class BudgetStatus:
    """Budget status response."""

    def __init__(
        self,
        used: int,
        remaining: int,
        total: int,
        reset_date: datetime,
        warning: bool = False,
        exhausted: bool = False,
    ):
        self.used = used
        self.remaining = remaining
        self.total = total
        self.reset_date = reset_date
        self.warning = warning
        self.exhausted = exhausted
        self.usage_pct = (used / total * 100) if total > 0 else 0

    def to_dict(self) -> dict:
        return {
            "used": self.used,
            "remaining": self.remaining,
            "total": self.total,
            "usage_pct": round(self.usage_pct, 1),
            "reset_date": self.reset_date.isoformat(),
            "warning": self.warning,
            "exhausted": self.exhausted,
        }


def get_budget_status(user: User) -> BudgetStatus:
    """Get the current token budget status for a user.

    Args:
        user: User model instance

    Returns:
        BudgetStatus with current usage info
    """
    used = user.token_budget_used or 0
    total = MONTHLY_TOKEN_BUDGET
    remaining = max(0, total - used)

    # Calculate reset date (next month anniversary)
    reset_at = user.token_budget_reset_at
    if reset_at is not None and reset_at.tzinfo is None:
        reset_at = reset_at.replace(tzinfo=timezone.utc)
    if reset_at is not None and reset_at.tzinfo is None:
        reset_at = reset_at.replace(tzinfo=timezone.utc)
    if reset_at is None:
        reset_at = datetime.now(timezone.utc)

    next_reset = reset_at + relativedelta(months=1)
    if next_reset.tzinfo is None:
        next_reset = next_reset.replace(tzinfo=timezone.utc)

    warning = (used / total) >= WARNING_THRESHOLD if total > 0 else False
    exhausted = remaining <= 0

    return BudgetStatus(
        used=used,
        remaining=remaining,
        total=total,
        reset_date=next_reset,
        warning=warning,
        exhausted=exhausted,
    )


def check_budget(user: User, estimated_tokens: int = 0) -> tuple[bool, str | None]:
    """Check if user has sufficient budget for a request.

    Args:
        user: User model instance
        estimated_tokens: Estimated tokens for this request

    Returns:
        Tuple of (can_proceed, error_message)
    """
    status = get_budget_status(user)

    if status.exhausted:
        return (
            False,
            "Monthly token budget exhausted. Resets on "
            f"{status.reset_date.strftime('%B %d')}.",
        )

    if estimated_tokens > status.remaining:
        return (
            False,
            f"Request would exceed budget. {status.remaining:,} tokens remaining.",
        )

    if status.warning:
        # Allow but will include warning in response
        pass

    return True, None


def update_budget(
    user: User,
    tokens_used: int,
    db: DBSession,
) -> BudgetStatus:
    """Update the user's token budget after a request.

    Args:
        user: User model instance
        tokens_used: Number of tokens consumed
        db: Database session

    Returns:
        Updated BudgetStatus
    """
    # Check if we need to reset (new billing period)
    _maybe_reset_budget(user, db)

    # Update usage
    user.token_budget_used = (user.token_budget_used or 0) + tokens_used
    user.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(user)

    return get_budget_status(user)


def reserve_tokens(
    user: User,
    session_id: str,
    estimated_tokens: int,
    db: DBSession,
) -> str:
    """Reserve tokens for an in-flight coach request.

    Returns the reservation ID.
    """
    _maybe_reset_budget(user, db)

    expires_at = datetime.now(timezone.utc) + timedelta(minutes=RESERVATION_TTL_MINUTES)
    reservation = CoachTokenReservation(
        user_id=user.id,
        session_id=session_id,
        estimated_tokens=estimated_tokens,
        expires_at=expires_at,
    )
    user.token_budget_used = (user.token_budget_used or 0) + estimated_tokens
    user.updated_at = datetime.now(timezone.utc)

    db.add(reservation)
    db.commit()
    db.refresh(reservation)
    return reservation.id


def release_expired_reservations(user: User, db: DBSession) -> int:
    """Release any expired reservations and restore budget."""
    _maybe_reset_budget(user, db)
    now = datetime.now(timezone.utc)
    reservations = (
        db.query(CoachTokenReservation)
        .filter(
            CoachTokenReservation.user_id == user.id,
            CoachTokenReservation.expires_at <= now,
        )
        .all()
    )

    if not reservations:
        return 0

    total_released = sum(r.estimated_tokens for r in reservations)
    user.token_budget_used = max(0, (user.token_budget_used or 0) - total_released)
    user.updated_at = datetime.now(timezone.utc)

    for reservation in reservations:
        db.delete(reservation)

    db.commit()
    return len(reservations)


def finalize_reservation(
    user: User,
    reservation_id: str,
    tokens_used: int,
    db: DBSession,
) -> None:
    """Finalize a reservation by reconciling estimated and actual usage."""
    reservation = (
        db.query(CoachTokenReservation)
        .filter(
            CoachTokenReservation.id == reservation_id,
            CoachTokenReservation.user_id == user.id,
        )
        .first()
    )
    if not reservation:
        return

    delta = tokens_used - reservation.estimated_tokens
    user.token_budget_used = max(0, (user.token_budget_used or 0) + delta)
    user.updated_at = datetime.now(timezone.utc)

    db.delete(reservation)
    db.commit()


def abort_reservation(user: User, reservation_id: str, db: DBSession) -> None:
    """Abort a reservation and restore the estimated tokens immediately."""
    reservation = (
        db.query(CoachTokenReservation)
        .filter(
            CoachTokenReservation.id == reservation_id,
            CoachTokenReservation.user_id == user.id,
        )
        .first()
    )
    if not reservation:
        return

    user.token_budget_used = max(
        0, (user.token_budget_used or 0) - reservation.estimated_tokens
    )
    user.updated_at = datetime.now(timezone.utc)

    db.delete(reservation)
    db.commit()


def _maybe_reset_budget(user: User, db: DBSession) -> bool:
    """Reset budget if we're in a new billing period.

    Args:
        user: User model instance
        db: Database session

    Returns:
        True if budget was reset
    """
    reset_at = user.token_budget_reset_at

    if reset_at is None:
        # First time - set reset date
        user.token_budget_reset_at = datetime.now(timezone.utc)
        user.token_budget_used = 0
        db.commit()
        return True

    # Check if we've passed the reset date
    now = datetime.now(timezone.utc)
    next_reset = reset_at + relativedelta(months=1)
    if next_reset.tzinfo is None:
        next_reset = next_reset.replace(tzinfo=timezone.utc)

    if now >= next_reset:
        # Reset budget
        user.token_budget_used = 0
        user.token_budget_reset_at = now
        db.commit()
        return True

    return False


def estimate_request_tokens(
    message_length: int,
    history_messages: int = 0,
    include_tools: bool = True,
) -> int:
    """Estimate tokens for a request.

    Args:
        message_length: Character length of user message
        history_messages: Number of previous messages in context
        include_tools: Whether tools are included

    Returns:
        Estimated token count
    """
    # Rough estimation: ~4 chars per token for English
    message_tokens = message_length // 4

    # History estimate: ~200 tokens per message average
    history_tokens = history_messages * 200

    # System prompt + tools: ~2000 tokens
    overhead = 2000 if include_tools else 500

    # Output estimate: ~500 tokens average response
    output_estimate = 500

    return message_tokens + history_tokens + overhead + output_estimate
