# src/rlcoach/db/models.py
"""SQLAlchemy models for RLCoach database.

IMPORTANT: All datetime fields store UTC. Use datetime.now(timezone.utc).
The play_date field is computed from played_at_utc + configured timezone.
"""

from __future__ import annotations

from datetime import datetime, timezone

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
)
from sqlalchemy.orm import DeclarativeBase, relationship


def _utc_now() -> datetime:
    """Get current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Replay(Base):
    __tablename__ = "replays"

    replay_id = Column(String, primary_key=True)
    source_file = Column(String, nullable=False)
    file_hash = Column(String, nullable=False, index=True)  # For dedup
    ingested_at = Column(DateTime(timezone=True), default=_utc_now)
    played_at_utc = Column(DateTime(timezone=True), nullable=False)
    play_date = Column(Date, nullable=False)  # Local date from timezone
    map = Column(String, nullable=False)
    playlist = Column(String, nullable=False)
    team_size = Column(Integer, nullable=False)
    duration_seconds = Column(Float, nullable=False)
    overtime = Column(Boolean, default=False)
    my_player_id = Column(String, ForeignKey("players.player_id"), nullable=False)
    my_team = Column(String, nullable=False)
    my_score = Column(Integer, nullable=False)
    opponent_score = Column(Integer, nullable=False)
    result = Column(String, nullable=False)
    json_report_path = Column(String, nullable=False)

    player_stats = relationship(
        "PlayerGameStats", back_populates="replay", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_replays_play_date", play_date.desc()),
        Index("ix_replays_playlist", playlist),
        Index("ix_replays_result", result),
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
    player_id = Column(String, ForeignKey("players.player_id"), nullable=False)
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
        Index("ix_player_game_stats_is_me", "is_me", sqlite_where=is_me),
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
