"""Initial schema with all tables.

Revision ID: 001_initial
Revises:
Create Date: 2026-01-03 20:00:00+00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ==========================================================================
    # USERS & AUTH (NextAuth compatible)
    # ==========================================================================

    op.create_table(
        "users",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("email", sa.String(), unique=True, nullable=True, index=True),
        sa.Column("email_verified", sa.DateTime(timezone=True), nullable=True),
        sa.Column("display_name", sa.String(), nullable=True),
        sa.Column("image", sa.String(), nullable=True),
        # Subscription
        sa.Column("subscription_tier", sa.String(), nullable=False, default="free"),
        sa.Column("subscription_status", sa.String(), nullable=True),
        sa.Column("stripe_customer_id", sa.String(), unique=True, nullable=True, index=True),
        sa.Column("stripe_subscription_id", sa.String(), unique=True, nullable=True),
        sa.Column("subscription_period_end", sa.DateTime(timezone=True), nullable=True),
        # Token budget
        sa.Column("token_budget_used", sa.Integer(), nullable=False, default=0),
        sa.Column("token_budget_reset_at", sa.DateTime(timezone=True), nullable=True),
        # Compliance
        sa.Column("tos_accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deletion_requested_at", sa.DateTime(timezone=True), nullable=True),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "accounts",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("provider_account_id", sa.String(), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=True),
        sa.Column("access_token", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.Integer(), nullable=True),
        sa.Column("token_type", sa.String(), nullable=True),
        sa.Column("scope", sa.String(), nullable=True),
        sa.Column("id_token", sa.Text(), nullable=True),
        sa.Column("session_state", sa.String(), nullable=True),
    )
    op.create_unique_constraint("uq_provider_account", "accounts", ["provider", "provider_account_id"])
    op.create_index("ix_accounts_user", "accounts", ["user_id"])

    op.create_table(
        "sessions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("session_token", sa.String(), unique=True, nullable=False, index=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expires", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "verification_tokens",
        sa.Column("identifier", sa.String(), primary_key=True),
        sa.Column("token", sa.String(), primary_key=True),
        sa.Column("expires", sa.DateTime(timezone=True), nullable=False),
    )

    # ==========================================================================
    # REPLAY DATA (existing tables, adapted)
    # ==========================================================================

    op.create_table(
        "players",
        sa.Column("player_id", sa.String(), primary_key=True),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("platform", sa.String(), nullable=True),
        sa.Column("is_me", sa.Boolean(), default=False, index=True),
        sa.Column("is_tagged_teammate", sa.Boolean(), default=False),
        sa.Column("teammate_notes", sa.Text(), nullable=True),
        sa.Column("first_seen_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("games_with_me", sa.Integer(), default=0),
    )

    op.create_table(
        "replays",
        sa.Column("replay_id", sa.String(), primary_key=True),
        sa.Column("source_file", sa.String(), nullable=False),
        sa.Column("file_hash", sa.String(), nullable=False, index=True),
        sa.Column("match_id", sa.String(), nullable=True, index=True),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("played_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("play_date", sa.Date(), nullable=False),
        sa.Column("map", sa.String(), nullable=False),
        sa.Column("playlist", sa.String(), nullable=False),
        sa.Column("team_size", sa.Integer(), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=False),
        sa.Column("overtime", sa.Boolean(), default=False),
        sa.Column("my_player_id", sa.String(), sa.ForeignKey("players.player_id"), nullable=True),
        sa.Column("my_team", sa.String(), nullable=True),
        sa.Column("my_score", sa.Integer(), nullable=True),
        sa.Column("opponent_score", sa.Integer(), nullable=True),
        sa.Column("result", sa.String(), nullable=True),
        sa.Column("json_report_path", sa.String(), nullable=True),
        sa.Column("session_id", sa.String(), nullable=True, index=True),
    )
    op.create_index("ix_replays_play_date", "replays", [sa.text("play_date DESC")])
    op.create_index("ix_replays_playlist", "replays", ["playlist"])
    op.create_index("ix_replays_result", "replays", ["result"])

    op.create_table(
        "player_game_stats",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("replay_id", sa.String(), sa.ForeignKey("replays.replay_id", ondelete="CASCADE"), nullable=False),
        sa.Column("player_id", sa.String(), sa.ForeignKey("players.player_id"), nullable=False),
        sa.Column("team", sa.String(), nullable=False),
        sa.Column("is_me", sa.Boolean(), default=False),
        sa.Column("is_teammate", sa.Boolean(), default=False),
        sa.Column("is_opponent", sa.Boolean(), default=False),
        # Fundamentals
        sa.Column("goals", sa.Integer(), default=0),
        sa.Column("assists", sa.Integer(), default=0),
        sa.Column("saves", sa.Integer(), default=0),
        sa.Column("shots", sa.Integer(), default=0),
        sa.Column("shooting_pct", sa.Float(), nullable=True),
        sa.Column("score", sa.Integer(), default=0),
        sa.Column("demos_inflicted", sa.Integer(), default=0),
        sa.Column("demos_taken", sa.Integer(), default=0),
        # Boost
        sa.Column("bcpm", sa.Float(), nullable=True),
        sa.Column("avg_boost", sa.Float(), nullable=True),
        sa.Column("time_zero_boost_s", sa.Float(), nullable=True),
        sa.Column("time_full_boost_s", sa.Float(), nullable=True),
        sa.Column("boost_collected", sa.Float(), nullable=True),
        sa.Column("boost_stolen", sa.Float(), nullable=True),
        sa.Column("big_pads", sa.Integer(), nullable=True),
        sa.Column("small_pads", sa.Integer(), nullable=True),
        # Movement
        sa.Column("avg_speed_kph", sa.Float(), nullable=True),
        sa.Column("distance_km", sa.Float(), nullable=True),
        sa.Column("max_speed_kph", sa.Float(), nullable=True),
        sa.Column("time_supersonic_s", sa.Float(), nullable=True),
        sa.Column("time_slow_s", sa.Float(), nullable=True),
        sa.Column("time_ground_s", sa.Float(), nullable=True),
        sa.Column("time_low_air_s", sa.Float(), nullable=True),
        sa.Column("time_high_air_s", sa.Float(), nullable=True),
        # Positioning
        sa.Column("time_offensive_third_s", sa.Float(), nullable=True),
        sa.Column("time_middle_third_s", sa.Float(), nullable=True),
        sa.Column("time_defensive_third_s", sa.Float(), nullable=True),
        sa.Column("behind_ball_pct", sa.Float(), nullable=True),
        sa.Column("avg_distance_to_ball_m", sa.Float(), nullable=True),
        sa.Column("avg_distance_to_teammate_m", sa.Float(), nullable=True),
        sa.Column("first_man_pct", sa.Float(), nullable=True),
        sa.Column("second_man_pct", sa.Float(), nullable=True),
        sa.Column("third_man_pct", sa.Float(), nullable=True),
        # Challenges
        sa.Column("challenge_wins", sa.Integer(), nullable=True),
        sa.Column("challenge_losses", sa.Integer(), nullable=True),
        sa.Column("challenge_neutral", sa.Integer(), nullable=True),
        sa.Column("first_to_ball_pct", sa.Float(), nullable=True),
        # Kickoffs
        sa.Column("kickoffs_participated", sa.Integer(), nullable=True),
        sa.Column("kickoff_first_touches", sa.Integer(), nullable=True),
        # Mechanics
        sa.Column("wavedash_count", sa.Integer(), nullable=True),
        sa.Column("halfflip_count", sa.Integer(), nullable=True),
        sa.Column("speedflip_count", sa.Integer(), nullable=True),
        sa.Column("aerial_count", sa.Integer(), nullable=True),
        sa.Column("flip_cancel_count", sa.Integer(), nullable=True),
        # Recovery
        sa.Column("total_recoveries", sa.Integer(), nullable=True),
        sa.Column("avg_recovery_momentum", sa.Float(), nullable=True),
        # Defense
        sa.Column("time_last_defender_s", sa.Float(), nullable=True),
        sa.Column("time_shadow_defense_s", sa.Float(), nullable=True),
        # xG
        sa.Column("total_xg", sa.Float(), nullable=True),
        sa.Column("shots_xg_list", sa.Text(), nullable=True),
    )
    op.create_unique_constraint("uq_replay_player", "player_game_stats", ["replay_id", "player_id"])
    op.create_index("ix_player_game_stats_replay", "player_game_stats", ["replay_id"])
    op.create_index("ix_player_game_stats_player", "player_game_stats", ["player_id"])
    # PostgreSQL partial index for is_me
    op.execute(
        "CREATE INDEX ix_player_game_stats_is_me ON player_game_stats (is_me) WHERE is_me = true"
    )

    op.create_table(
        "daily_stats",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("play_date", sa.Date(), nullable=False),
        sa.Column("playlist", sa.String(), nullable=False),
        sa.Column("games_played", sa.Integer(), default=0),
        sa.Column("wins", sa.Integer(), default=0),
        sa.Column("losses", sa.Integer(), default=0),
        sa.Column("draws", sa.Integer(), default=0),
        sa.Column("win_rate", sa.Float(), nullable=True),
        sa.Column("avg_goals", sa.Float(), nullable=True),
        sa.Column("avg_assists", sa.Float(), nullable=True),
        sa.Column("avg_saves", sa.Float(), nullable=True),
        sa.Column("avg_shots", sa.Float(), nullable=True),
        sa.Column("avg_shooting_pct", sa.Float(), nullable=True),
        sa.Column("avg_bcpm", sa.Float(), nullable=True),
        sa.Column("avg_boost", sa.Float(), nullable=True),
        sa.Column("avg_speed_kph", sa.Float(), nullable=True),
        sa.Column("avg_supersonic_pct", sa.Float(), nullable=True),
        sa.Column("avg_behind_ball_pct", sa.Float(), nullable=True),
        sa.Column("avg_first_man_pct", sa.Float(), nullable=True),
        sa.Column("avg_challenge_win_pct", sa.Float(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_unique_constraint("uq_daily_playlist", "daily_stats", ["play_date", "playlist"])
    op.create_index("ix_daily_stats_lookup", "daily_stats", [sa.text("play_date DESC"), "playlist"])

    op.create_table(
        "benchmarks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("metric", sa.String(), nullable=False),
        sa.Column("playlist", sa.String(), nullable=False),
        sa.Column("rank_tier", sa.String(), nullable=False),
        sa.Column("median_value", sa.Float(), nullable=False),
        sa.Column("p25_value", sa.Float(), nullable=True),
        sa.Column("p75_value", sa.Float(), nullable=True),
        sa.Column("elite_threshold", sa.Float(), nullable=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("source_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_unique_constraint("uq_benchmark", "benchmarks", ["metric", "playlist", "rank_tier"])
    op.create_index("ix_benchmarks_lookup", "benchmarks", ["metric", "playlist", "rank_tier"])

    # ==========================================================================
    # AI COACH TABLES
    # ==========================================================================

    op.create_table(
        "coach_sessions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_input_tokens", sa.Integer(), default=0, nullable=False),
        sa.Column("total_output_tokens", sa.Integer(), default=0, nullable=False),
        sa.Column("total_thinking_tokens", sa.Integer(), default=0, nullable=False),
        sa.Column("message_count", sa.Integer(), default=0, nullable=False),
    )
    op.create_index("ix_coach_sessions_user", "coach_sessions", ["user_id"])

    op.create_table(
        "coach_messages",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("session_id", sa.String(), sa.ForeignKey("coach_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("thinking_tokens", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_coach_messages_session", "coach_messages", ["session_id"])

    op.create_table(
        "coach_notes",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_coach_notes_user", "coach_notes", ["user_id"])

    # ==========================================================================
    # UPLOAD & OWNERSHIP TABLES
    # ==========================================================================

    op.create_table(
        "uploaded_replays",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("replay_id", sa.String(), sa.ForeignKey("replays.replay_id", ondelete="SET NULL"), nullable=True),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("file_hash", sa.String(), nullable=False, index=True),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_path", sa.String(), nullable=False),
        sa.Column("status", sa.String(), default="pending", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_uploaded_replays_user", "uploaded_replays", ["user_id"])
    op.create_index("ix_uploaded_replays_status", "uploaded_replays", ["status"])

    op.create_table(
        "user_replays",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("replay_id", sa.String(), sa.ForeignKey("replays.replay_id", ondelete="CASCADE"), nullable=False),
        sa.Column("ownership_type", sa.String(), default="uploaded", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_unique_constraint("uq_user_replay", "user_replays", ["user_id", "replay_id"])
    op.create_index("ix_user_replays_user", "user_replays", ["user_id"])
    op.create_index("ix_user_replays_replay", "user_replays", ["replay_id"])


def downgrade() -> None:
    op.drop_table("user_replays")
    op.drop_table("uploaded_replays")
    op.drop_table("coach_notes")
    op.drop_table("coach_messages")
    op.drop_table("coach_sessions")
    op.drop_table("benchmarks")
    op.drop_table("daily_stats")
    op.drop_table("player_game_stats")
    op.drop_table("replays")
    op.drop_table("players")
    op.drop_table("verification_tokens")
    op.drop_table("sessions")
    op.drop_table("accounts")
    op.drop_table("users")
