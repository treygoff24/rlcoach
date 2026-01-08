# src/rlcoach/db/models.py
"""SQLAlchemy models for RLCoach database.

IMPORTANT: All datetime fields store UTC. Use datetime.now(timezone.utc).
The play_date field is computed from played_at_utc + configured timezone.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, relationship


def _utc_now() -> datetime:
    """Get current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


def _generate_uuid() -> str:
    """Generate a new UUID string."""
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


# =============================================================================
# EXISTING TABLES (adapted for PostgreSQL)
# =============================================================================


class Replay(Base):
    __tablename__ = "replays"

    replay_id = Column(String, primary_key=True)
    source_file = Column(String, nullable=False)
    file_hash = Column(String, nullable=False, index=True)  # For dedup
    match_id = Column(String, index=True)  # Rocket League match GUID for dedup
    ingested_at = Column(DateTime(timezone=True), default=_utc_now)
    played_at_utc = Column(DateTime(timezone=True), nullable=False)
    play_date = Column(Date, nullable=False)  # Local date from timezone
    map = Column(String, nullable=False)
    playlist = Column(String, nullable=False)
    team_size = Column(Integer, nullable=False)
    duration_seconds = Column(Float, nullable=False)
    overtime = Column(Boolean, default=False)
    my_player_id = Column(String, ForeignKey("players.player_id"), nullable=True)
    my_team = Column(String, nullable=True)
    my_score = Column(Integer, nullable=True)
    opponent_score = Column(Integer, nullable=True)
    result = Column(String, nullable=True)
    json_report_path = Column(String, nullable=True)
    # Session grouping (replays within 30 min = same session)
    session_id = Column(String, index=True)

    player_stats = relationship(
        "PlayerGameStats", back_populates="replay", cascade="all, delete-orphan"
    )
    user_replays = relationship(
        "UserReplay", back_populates="replay", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_replays_play_date", play_date.desc()),
        Index("ix_replays_playlist", playlist),
        Index("ix_replays_result", result),
        Index("ix_replays_session", session_id),
    )


class Player(Base):
    __tablename__ = "players"

    player_id = Column(String, primary_key=True)
    display_name = Column(String, nullable=False)
    platform = Column(String)
    is_me = Column(Boolean, default=False, index=True)
    is_tagged_teammate = Column(Boolean, default=False)
    teammate_notes = Column(Text)
    first_seen_utc = Column(DateTime(timezone=True), default=_utc_now)
    last_seen_utc = Column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now)
    games_with_me = Column(Integer, default=0)


class PlayerGameStats(Base):
    __tablename__ = "player_game_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    replay_id = Column(
        String, ForeignKey("replays.replay_id", ondelete="CASCADE"), nullable=False
    )
    player_id = Column(
        String, ForeignKey("players.player_id", ondelete="CASCADE"), nullable=False
    )
    team = Column(String, nullable=False)
    is_me = Column(Boolean, default=False)
    is_teammate = Column(Boolean, default=False)
    is_opponent = Column(Boolean, default=False)

    # Fundamentals
    goals = Column(Integer, default=0)
    assists = Column(Integer, default=0)
    saves = Column(Integer, default=0)
    shots = Column(Integer, default=0)
    shooting_pct = Column(Float)
    score = Column(Integer, default=0)
    demos_inflicted = Column(Integer, default=0)
    demos_taken = Column(Integer, default=0)

    # Boost
    bcpm = Column(Float)
    avg_boost = Column(Float)
    time_zero_boost_s = Column(Float)
    time_full_boost_s = Column(Float)
    boost_collected = Column(Float)
    boost_stolen = Column(Float)
    big_pads = Column(Integer)
    small_pads = Column(Integer)

    # Movement
    avg_speed_kph = Column(Float)
    distance_km = Column(Float)
    max_speed_kph = Column(Float)
    time_supersonic_s = Column(Float)
    time_slow_s = Column(Float)
    time_ground_s = Column(Float)
    time_low_air_s = Column(Float)
    time_high_air_s = Column(Float)

    # Positioning
    time_offensive_third_s = Column(Float)
    time_middle_third_s = Column(Float)
    time_defensive_third_s = Column(Float)
    behind_ball_pct = Column(Float)
    avg_distance_to_ball_m = Column(Float)
    avg_distance_to_teammate_m = Column(Float)
    first_man_pct = Column(Float)
    second_man_pct = Column(Float)
    third_man_pct = Column(Float)

    # Challenges
    challenge_wins = Column(Integer)
    challenge_losses = Column(Integer)
    challenge_neutral = Column(Integer)
    first_to_ball_pct = Column(Float)

    # Kickoffs
    kickoffs_participated = Column(Integer)
    kickoff_first_touches = Column(Integer)

    # Mechanics
    wavedash_count = Column(Integer)
    halfflip_count = Column(Integer)
    speedflip_count = Column(Integer)
    aerial_count = Column(Integer)
    flip_cancel_count = Column(Integer)

    # Recovery
    total_recoveries = Column(Integer)
    avg_recovery_momentum = Column(Float)

    # Defense
    time_last_defender_s = Column(Float)
    time_shadow_defense_s = Column(Float)

    # xG
    total_xg = Column(Float)
    shots_xg_list = Column(Text)  # JSON array

    __table_args__ = (
        UniqueConstraint("replay_id", "player_id", name="uq_replay_player"),
        Index("ix_player_game_stats_replay", "replay_id"),
        Index("ix_player_game_stats_player", "player_id"),
        # PostgreSQL partial index using text() for compatibility
        Index(
            "ix_player_game_stats_is_me",
            "is_me",
            postgresql_where=text("is_me = true"),
        ),
    )

    replay = relationship("Replay", back_populates="player_stats")


class DailyStats(Base):
    __tablename__ = "daily_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    play_date = Column(Date, nullable=False)
    playlist = Column(String, nullable=False)
    games_played = Column(Integer, default=0)
    wins = Column(Integer, default=0)
    losses = Column(Integer, default=0)
    draws = Column(Integer, default=0)
    win_rate = Column(Float)

    # Averaged stats
    avg_goals = Column(Float)
    avg_assists = Column(Float)
    avg_saves = Column(Float)
    avg_shots = Column(Float)
    avg_shooting_pct = Column(Float)
    avg_bcpm = Column(Float)
    avg_boost = Column(Float)
    avg_speed_kph = Column(Float)
    avg_supersonic_pct = Column(Float)
    avg_behind_ball_pct = Column(Float)
    avg_first_man_pct = Column(Float)
    avg_challenge_win_pct = Column(Float)

    updated_at = Column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now)

    __table_args__ = (
        UniqueConstraint("play_date", "playlist", name="uq_daily_playlist"),
        Index("ix_daily_stats_lookup", play_date.desc(), "playlist"),
    )


class Benchmark(Base):
    __tablename__ = "benchmarks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    metric = Column(String, nullable=False)
    playlist = Column(String, nullable=False)
    rank_tier = Column(String, nullable=False)
    median_value = Column(Float, nullable=False)
    p25_value = Column(Float)
    p75_value = Column(Float)
    elite_threshold = Column(Float)
    source = Column(String, nullable=False)
    source_date = Column(Date)
    notes = Column(Text)
    imported_at = Column(DateTime(timezone=True), default=_utc_now)

    __table_args__ = (
        UniqueConstraint("metric", "playlist", "rank_tier", name="uq_benchmark"),
        Index("ix_benchmarks_lookup", "metric", "playlist", "rank_tier"),
    )


# =============================================================================
# NEW SAAS TABLES
# =============================================================================


class SubscriptionTier(str, Enum):
    FREE = "free"
    PRO = "pro"


class SubscriptionStatus(str, Enum):
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"


class User(Base):
    """User accounts with subscription info."""

    __tablename__ = "users"

    id = Column(String, primary_key=True, default=_generate_uuid)
    email = Column(String, unique=True, nullable=True, index=True)
    email_verified = Column(DateTime(timezone=True), nullable=True)
    display_name = Column(String, nullable=True)
    image = Column(String, nullable=True)  # Avatar URL

    # Subscription fields (stored directly, not separate table)
    subscription_tier = Column(String, default="free", nullable=False)
    subscription_status = Column(String, nullable=True)  # active, past_due, canceled
    stripe_customer_id = Column(String, unique=True, nullable=True, index=True)
    stripe_subscription_id = Column(String, unique=True, nullable=True)
    subscription_period_end = Column(DateTime(timezone=True), nullable=True)

    # Token budget for AI coach
    token_budget_used = Column(Integer, default=0, nullable=False)
    token_budget_reset_at = Column(DateTime(timezone=True), default=_utc_now)

    # Free tier coach preview (1 free message for non-Pro users)
    free_coach_message_used = Column(Boolean, default=False, nullable=False)

    # Terms acceptance
    tos_accepted_at = Column(DateTime(timezone=True), nullable=True)

    # Account deletion
    deletion_requested_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False
    )

    # Relationships
    oauth_accounts = relationship(
        "OAuthAccount", back_populates="user", cascade="all, delete-orphan"
    )
    sessions = relationship(
        "Session", back_populates="user", cascade="all, delete-orphan"
    )
    coach_sessions = relationship(
        "CoachSession", back_populates="user", cascade="all, delete-orphan"
    )
    coach_notes = relationship(
        "CoachNote", back_populates="user", cascade="all, delete-orphan"
    )
    user_replays = relationship(
        "UserReplay", back_populates="user", cascade="all, delete-orphan"
    )
    uploaded_replays = relationship(
        "UploadedReplay", back_populates="user", cascade="all, delete-orphan"
    )


class OAuthAccount(Base):
    """Linked OAuth providers (NextAuth 'accounts' table)."""

    __tablename__ = "accounts"

    id = Column(String, primary_key=True, default=_generate_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    type = Column(String, nullable=False)  # "oauth" | "oidc" | "email"
    provider = Column(String, nullable=False)  # discord, steam, google, epic
    provider_account_id = Column(String, nullable=False)
    refresh_token = Column(Text, nullable=True)
    access_token = Column(Text, nullable=True)
    expires_at = Column(Integer, nullable=True)
    token_type = Column(String, nullable=True)
    scope = Column(String, nullable=True)
    id_token = Column(Text, nullable=True)
    session_state = Column(String, nullable=True)

    user = relationship("User", back_populates="oauth_accounts")

    __table_args__ = (
        UniqueConstraint("provider", "provider_account_id", name="uq_provider_account"),
        Index("ix_accounts_user", "user_id"),
    )


class Session(Base):
    """NextAuth session storage."""

    __tablename__ = "sessions"

    id = Column(String, primary_key=True, default=_generate_uuid)
    session_token = Column(String, unique=True, nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    expires = Column(DateTime(timezone=True), nullable=False)

    user = relationship("User", back_populates="sessions")

    __table_args__ = (Index("ix_sessions_user_id", "user_id"),)


class VerificationToken(Base):
    """NextAuth email verification tokens."""

    __tablename__ = "verification_tokens"

    identifier = Column(String, primary_key=True)
    token = Column(String, primary_key=True)
    expires = Column(DateTime(timezone=True), nullable=False)


class CoachSession(Base):
    """AI coach conversation sessions."""

    __tablename__ = "coach_sessions"

    id = Column(String, primary_key=True, default=_generate_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    started_at = Column(DateTime(timezone=True), default=_utc_now, nullable=False)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    total_input_tokens = Column(Integer, default=0, nullable=False)
    total_output_tokens = Column(Integer, default=0, nullable=False)
    total_thinking_tokens = Column(Integer, default=0, nullable=False)
    message_count = Column(Integer, default=0, nullable=False)

    user = relationship("User", back_populates="coach_sessions")
    messages = relationship(
        "CoachMessage", back_populates="session", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_coach_sessions_user", "user_id"),)


class CoachMessage(Base):
    """Individual messages in coach conversations."""

    __tablename__ = "coach_messages"

    id = Column(String, primary_key=True, default=_generate_uuid)
    session_id = Column(
        String, ForeignKey("coach_sessions.id", ondelete="CASCADE"), nullable=False
    )
    role = Column(String, nullable=False)  # "user" | "assistant"
    content = Column(Text, nullable=False)
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    thinking_tokens = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utc_now, nullable=False)

    session = relationship("CoachSession", back_populates="messages")

    __table_args__ = (Index("ix_coach_messages_session", "session_id"),)


class CoachNote(Base):
    """Persistent coaching notes."""

    __tablename__ = "coach_notes"

    id = Column(String, primary_key=True, default=_generate_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)
    source = Column(String, nullable=False)  # "coach" | "user"
    category = Column(String, nullable=True)  # weakness, strength, goal, observation
    created_at = Column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False
    )

    user = relationship("User", back_populates="coach_notes")

    __table_args__ = (Index("ix_coach_notes_user", "user_id"),)


class UploadedReplay(Base):
    """Track replay upload status."""

    __tablename__ = "uploaded_replays"

    id = Column(String, primary_key=True, default=_generate_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    replay_id = Column(
        String, ForeignKey("replays.replay_id", ondelete="SET NULL"), nullable=True
    )
    filename = Column(String, nullable=False)
    file_hash = Column(String, nullable=False, index=True)
    file_size_bytes = Column(Integer, nullable=False)
    storage_path = Column(String, nullable=False)
    status = Column(
        String, default="pending", nullable=False
    )  # pending, processing, completed, failed
    error_message = Column(Text, nullable=True)
    uploaded_at = Column(DateTime(timezone=True), default=_utc_now, nullable=False)
    processed_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="uploaded_replays")

    __table_args__ = (
        Index("ix_uploaded_replays_user", "user_id"),
        Index("ix_uploaded_replays_status", "status"),
        Index("ix_uploaded_replays_replay_id", "replay_id"),
    )


class OwnershipType(str, Enum):
    UPLOADED = "uploaded"
    CLAIMED = "claimed"
    AUTO_MATCHED = "auto_matched"


class UserReplay(Base):
    """Many-to-many join table for replay ownership.

    Allows multiple users to 'own' the same replay (dedup case)
    and one user to own multiple replays (normal case).
    """

    __tablename__ = "user_replays"

    id = Column(String, primary_key=True, default=_generate_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    replay_id = Column(
        String, ForeignKey("replays.replay_id", ondelete="CASCADE"), nullable=False
    )
    ownership_type = Column(
        String, default="uploaded", nullable=False
    )  # uploaded, claimed, auto_matched
    created_at = Column(DateTime(timezone=True), default=_utc_now, nullable=False)

    user = relationship("User", back_populates="user_replays")
    replay = relationship("Replay", back_populates="user_replays")

    __table_args__ = (
        UniqueConstraint("user_id", "replay_id", name="uq_user_replay"),
        Index("ix_user_replays_user", "user_id"),
        Index("ix_user_replays_replay", "replay_id"),
    )
