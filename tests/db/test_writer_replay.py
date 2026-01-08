# tests/db/test_writer_replay.py
from datetime import date
from pathlib import Path

import pytest

from rlcoach.config import IdentityConfig, PathsConfig, PreferencesConfig, RLCoachConfig
from rlcoach.db.models import Player, Replay
from rlcoach.db.session import create_session, init_db, reset_engine
from rlcoach.db.writer import ReplayExistsError, insert_replay


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
        "source_file": "/path/to/replay.replay",
        "metadata": {
            "playlist": "DOUBLES",
            "map": "DFH Stadium",
            "team_size": 2,
            "duration_seconds": 312.5,
            "overtime": False,
            "started_at_utc": "2024-12-24T02:00:00Z",  # Dec 23 in LA time
        },
        "teams": {
            "blue": {"score": 3, "players": ["steam:me123"]},
            "orange": {"score": 1, "players": ["steam:opp456"]},
        },
        "players": [
            {"player_id": "steam:me123", "display_name": "MePlayer", "team": "BLUE"},
            {"player_id": "steam:opp456", "display_name": "Opponent", "team": "ORANGE"},
        ],
        "analysis": {"per_player": {}},
    }


def test_insert_replay_creates_record(tmp_path, config, sample_report):
    db_path = tmp_path / "test.db"
    init_db(db_path)

    # Pre-create player
    session = create_session()
    session.add(Player(player_id="steam:me123", display_name="Me", is_me=True))
    session.commit()
    session.close()

    replay_id = insert_replay(sample_report, "filehash123", config)

    assert replay_id == "abc123hash"

    session = create_session()
    try:
        replay = session.get(Replay, "abc123hash")
        assert replay is not None
        assert replay.result == "WIN"
        assert replay.my_team == "BLUE"
        # Timezone conversion: 2024-12-24 02:00 UTC = 2024-12-23 in LA
        assert replay.play_date == date(2024, 12, 23)
    finally:
        session.close()


def test_insert_replay_rejects_duplicate_replay_id(tmp_path, config, sample_report):
    db_path = tmp_path / "test.db"
    init_db(db_path)

    session = create_session()
    session.add(Player(player_id="steam:me123", display_name="Me", is_me=True))
    session.commit()
    session.close()

    insert_replay(sample_report, "filehash123", config)

    # Try to insert same replay_id
    with pytest.raises(ReplayExistsError, match="replay_id"):
        insert_replay(sample_report, "different_hash", config)


def test_insert_replay_rejects_duplicate_file_hash(tmp_path, config, sample_report):
    db_path = tmp_path / "test.db"
    init_db(db_path)

    session = create_session()
    session.add(Player(player_id="steam:me123", display_name="Me", is_me=True))
    session.commit()
    session.close()

    insert_replay(sample_report, "samehash", config)

    # Different replay_id but same file_hash
    sample_report["replay_id"] = "different_id"
    with pytest.raises(ReplayExistsError, match="file_hash"):
        insert_replay(sample_report, "samehash", config)
