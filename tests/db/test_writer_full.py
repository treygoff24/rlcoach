# tests/db/test_writer_full.py
from datetime import date
from pathlib import Path

import pytest

from rlcoach.config import IdentityConfig, PathsConfig, PreferencesConfig, RLCoachConfig
from rlcoach.db.models import Player, PlayerGameStats, Replay
from rlcoach.db.session import create_session, init_db, reset_engine
from rlcoach.db.writer import write_report


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
def full_report():
    return {
        "replay_id": "abc123hash",
        "source_file": "/path/to/replay.replay",
        "metadata": {
            "playlist": "DOUBLES",
            "map": "DFH Stadium",
            "team_size": 2,
            "duration_seconds": 312.5,
            "overtime": False,
            "started_at_utc": "2024-12-24T02:00:00Z",
        },
        "teams": {
            "blue": {"score": 3, "players": ["steam:me123"]},
            "orange": {"score": 1, "players": ["steam:opp456"]},
        },
        "players": [
            {"player_id": "steam:me123", "display_name": "MePlayer", "team": "BLUE"},
            {"player_id": "steam:opp456", "display_name": "Opponent", "team": "ORANGE"},
        ],
        "analysis": {
            "per_player": {
                "steam:me123": {
                    "fundamentals": {
                        "goals": 2,
                        "assists": 1,
                        "saves": 3,
                        "shots": 5,
                        "score": 450,
                    },
                    "boost": {"bpm": 380.5, "avg_boost": 32.1},
                    "movement": {"avg_speed_kph": 58.2, "time_supersonic_s": 65.0},
                    "positioning": {"behind_ball_pct": 58.0},
                },
                "steam:opp456": {
                    "fundamentals": {
                        "goals": 1,
                        "assists": 0,
                        "saves": 1,
                        "shots": 3,
                        "score": 200,
                    },
                    "boost": {"bpm": 320.0, "avg_boost": 38.0},
                    "movement": {"avg_speed_kph": 52.0, "time_supersonic_s": 45.0},
                    "positioning": {"behind_ball_pct": 52.0},
                },
            }
        },
    }


def test_write_report_full_pipeline(tmp_path, config, full_report):
    """write_report should create players, replay, and stats in one call."""
    db_path = tmp_path / "test.db"
    init_db(db_path)

    replay_id = write_report(full_report, "filehash123", config)

    assert replay_id == "abc123hash"

    session = create_session()
    try:
        # Check players were created
        players = session.query(Player).all()
        assert len(players) == 2

        me = session.get(Player, "steam:me123")
        assert me is not None
        assert me.is_me is True

        # Check replay was created
        replay = session.get(Replay, "abc123hash")
        assert replay is not None
        assert replay.result == "WIN"
        assert replay.play_date == date(2024, 12, 23)

        # Check stats were created
        stats = session.query(PlayerGameStats).all()
        assert len(stats) == 2

        my_stats = (
            session.query(PlayerGameStats).filter_by(player_id="steam:me123").first()
        )
        assert my_stats.goals == 2
        assert my_stats.bcpm == pytest.approx(380.5, rel=0.01)
    finally:
        session.close()


def test_write_report_is_idempotent_on_duplicate(tmp_path, config, full_report):
    """Attempting to write same report twice should raise error."""
    db_path = tmp_path / "test.db"
    init_db(db_path)

    from rlcoach.db.writer import ReplayExistsError

    write_report(full_report, "filehash123", config)

    with pytest.raises(ReplayExistsError):
        write_report(full_report, "filehash123", config)
