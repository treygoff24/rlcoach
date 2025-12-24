# tests/db/test_models.py
import pytest
from datetime import datetime, timezone, date
from pathlib import Path
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from rlcoach.db.models import Base, Replay, Player, PlayerGameStats, DailyStats, Benchmark


def test_create_tables(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)

    assert db_path.exists()

    inspector = inspect(engine)
    tables = inspector.get_table_names()
    assert "replays" in tables
    assert "players" in tables
    assert "player_game_stats" in tables
    assert "daily_stats" in tables
    assert "benchmarks" in tables


def test_insert_replay_with_utc_datetime(tmp_path):
    """Replay should use timezone-aware UTC datetime."""
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        # First create the player
        player = Player(
            player_id="steam:123",
            display_name="TestPlayer",
            platform="steam",
            is_me=True,
        )
        session.add(player)
        session.flush()

        replay = Replay(
            replay_id="abc123",
            source_file="/path/to/replay.replay",
            file_hash="sha256hash",
            played_at_utc=datetime.now(timezone.utc),  # Must be UTC aware
            play_date=date(2024, 12, 23),
            map="DFH Stadium",
            playlist="DOUBLES",
            team_size=2,
            duration_seconds=312.5,
            my_player_id="steam:123",
            my_team="BLUE",
            my_score=3,
            opponent_score=1,
            result="WIN",
            json_report_path="/path/to/report.json",
        )
        session.add(replay)
        session.commit()

        fetched = session.get(Replay, "abc123")
        assert fetched is not None
        assert fetched.result == "WIN"
        assert fetched.play_date == date(2024, 12, 23)


def test_indexes_exist(tmp_path):
    """Verify performance indexes are created."""
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)

    inspector = inspect(engine)

    # Check replays indexes
    replay_indexes = {idx["name"] for idx in inspector.get_indexes("replays")}
    assert "ix_replays_play_date" in replay_indexes
    assert "ix_replays_playlist" in replay_indexes

    # Check player_game_stats indexes
    pgs_indexes = {idx["name"] for idx in inspector.get_indexes("player_game_stats")}
    assert "ix_player_game_stats_is_me" in pgs_indexes
