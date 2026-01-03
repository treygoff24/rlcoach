# src/rlcoach/db/__init__.py
"""Database module for RLCoach."""

from .models import (
    Base,
    Benchmark,
    CoachMessage,
    CoachNote,
    CoachSession,
    DailyStats,
    OAuthAccount,
    OwnershipType,
    Player,
    PlayerGameStats,
    Replay,
    Session,
    SubscriptionStatus,
    SubscriptionTier,
    UploadedReplay,
    User,
    UserReplay,
    VerificationToken,
)
from .replay_sessions import (
    assign_sessions_to_replays,
    detect_session_for_replay,
    generate_session_id,
    get_sessions_for_user,
)
from .session import (
    create_session,
    get_database_info,
    get_session,
    init_db,
    init_db_from_url,
    is_postgresql,
    reset_engine,
)

__all__ = [
    # Base
    "Base",
    # Existing models
    "Replay",
    "Player",
    "PlayerGameStats",
    "DailyStats",
    "Benchmark",
    # New SaaS models
    "User",
    "OAuthAccount",
    "Session",
    "VerificationToken",
    "CoachSession",
    "CoachMessage",
    "CoachNote",
    "UploadedReplay",
    "UserReplay",
    # Enums
    "SubscriptionTier",
    "SubscriptionStatus",
    "OwnershipType",
    # Session management
    "init_db",
    "init_db_from_url",
    "get_session",
    "create_session",
    "reset_engine",
    "is_postgresql",
    "get_database_info",
    # Replay sessions
    "generate_session_id",
    "detect_session_for_replay",
    "assign_sessions_to_replays",
    "get_sessions_for_user",
]
