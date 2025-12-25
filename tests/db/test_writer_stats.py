# tests/db/test_writer_stats.py
import pytest
from datetime import datetime, date, timezone
from pathlib import Path
from rlcoach.db.writer import insert_player_stats
from rlcoach.db.session import init_db, create_session, reset_engine
from rlcoach.db.models import Player, Replay, PlayerGameStats
from rlcoach.config import IdentityConfig, PathsConfig, PreferencesConfig, RLCoachConfig


@pytest.fixture(autouse=True)
def reset_db():
    yield
    reset_engine()


@pytest.fixture
def config():
    return RLCoachConfig(
        identity=IdentityConfig(platform_ids=["steam:me123"]),
        paths=PathsConfig(
            watch_folder=Path("~/Replays"),
            data_dir=Path("~/.rlcoach/data"),
            reports_dir=Path("~/.rlcoach/reports"),
        ),
        preferences=PreferencesConfig(timezone="America/Los_Angeles"),
    )


@pytest.fixture
def sample_report():
    return {
        "replay_id": "abc123hash",
        "players": [
            {"player_id": "steam:me123", "display_name": "MePlayer", "team": "BLUE"},
            {"player_id": "steam:opp456", "display_name": "Opponent", "team": "ORANGE"},
        ],
        "analysis": {
            "per_player": {
                "steam:me123": {
                    "fundamentals": {"goals": 2, "assists": 1, "saves": 3, "shots": 5, "score": 450},
                    "boost": {"bpm": 380.5, "avg_boost": 32.1},
                    "movement": {"avg_speed_kph": 58.2, "time_supersonic_s": 65.0},
                    "positioning": {"behind_ball_pct": 58.0},
                },
                "steam:opp456": {
                    "fundamentals": {"goals": 1, "assists": 0, "saves": 1, "shots": 3, "score": 200},
                    "boost": {"bpm": 320.0, "avg_boost": 38.0},
                    "movement": {"avg_speed_kph": 52.0, "time_supersonic_s": 45.0},
                    "positioning": {"behind_ball_pct": 52.0},
                },
            }
        },
    }


def test_insert_player_stats_creates_records(tmp_path, sample_report, config):
    db_path = tmp_path / "test.db"
    init_db(db_path)

    # Pre-create players and replay
    session = create_session()
    session.add(Player(player_id="steam:me123", display_name="Me", is_me=True))
    session.add(Player(player_id="steam:opp456", display_name="Opp", is_me=False))
    session.add(Replay(
        replay_id="abc123hash",
        source_file="/path/to/file.replay",
        file_hash="hash123",
        played_at_utc=datetime.now(timezone.utc),
        play_date=date.today(),
        map="DFH Stadium",
        playlist="DOUBLES",
        team_size=2,
        duration_seconds=300.0,
        my_player_id="steam:me123",
        my_team="BLUE",
        my_score=3,
        opponent_score=1,
        result="WIN",
        json_report_path="/path/to/report.json",
    ))
    session.commit()
    session.close()

    insert_player_stats(sample_report, config)

    session = create_session()
    try:
        stats = session.query(PlayerGameStats).all()
        assert len(stats) == 2

        my_stats = session.query(PlayerGameStats).filter_by(player_id="steam:me123").first()
        assert my_stats is not None
        assert my_stats.goals == 2
        assert my_stats.bcpm == pytest.approx(380.5, rel=0.01)
        assert my_stats.avg_speed_kph == pytest.approx(58.2, rel=0.01)
    finally:
        session.close()


def test_insert_player_stats_handles_missing_metrics(tmp_path, config):
    """Stats with missing metrics should still be inserted with None values."""
    db_path = tmp_path / "test.db"
    init_db(db_path)

    session = create_session()
    session.add(Player(player_id="steam:me123", display_name="Me", is_me=True))
    session.add(Replay(
        replay_id="abc123hash",
        source_file="/path/to/file.replay",
        file_hash="hash123",
        played_at_utc=datetime.now(timezone.utc),
        play_date=date.today(),
        map="DFH Stadium",
        playlist="DOUBLES",
        team_size=2,
        duration_seconds=300.0,
        my_player_id="steam:me123",
        my_team="BLUE",
        my_score=1,
        opponent_score=0,
        result="WIN",
        json_report_path="/path/to/report.json",
    ))
    session.commit()
    session.close()

    # Minimal report with sparse analysis
    sparse_report = {
        "replay_id": "abc123hash",
        "players": [{"player_id": "steam:me123", "display_name": "Me", "team": "BLUE"}],
        "analysis": {
            "per_player": {
                "steam:me123": {
                    "fundamentals": {"goals": 1},
                }
            }
        },
    }

    insert_player_stats(sparse_report, config)

    session = create_session()
    try:
        stats = session.query(PlayerGameStats).filter_by(player_id="steam:me123").first()
        assert stats is not None
        assert stats.goals == 1
        assert stats.bcpm is None  # Missing metric
    finally:
        session.close()