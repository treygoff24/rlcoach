# tests/db/test_writer_players.py
import pytest
from datetime import datetime, timezone
from rlcoach.db.writer import upsert_players
from rlcoach.db.session import init_db, create_session, reset_engine
from rlcoach.db.models import Player
from rlcoach.config import IdentityConfig


@pytest.fixture(autouse=True)
def reset_db():
    yield
    reset_engine()


def test_upsert_players_creates_new(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)

    identity = IdentityConfig(platform_ids=["steam:me123"])
    players = [
        {"player_id": "steam:me123", "display_name": "MePlayer", "team": "BLUE"},
        {"player_id": "steam:other456", "display_name": "OtherPlayer", "team": "ORANGE"},
    ]

    upsert_players(players, identity)

    session = create_session()
    try:
        me = session.get(Player, "steam:me123")
        assert me is not None
        assert me.is_me is True
        assert me.games_with_me == 0  # I don't count as game with myself

        other = session.get(Player, "steam:other456")
        assert other is not None
        assert other.is_me is False
        assert other.games_with_me == 1  # This player was in a game with me
    finally:
        session.close()


def test_upsert_players_updates_existing(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)

    identity = IdentityConfig(platform_ids=["steam:me123"])

    # First call
    upsert_players([
        {"player_id": "steam:other456", "display_name": "OldName", "team": "BLUE"},
    ], identity)

    # Second call with new name
    upsert_players([
        {"player_id": "steam:other456", "display_name": "NewName", "team": "BLUE"},
    ], identity)

    session = create_session()
    try:
        player = session.get(Player, "steam:other456")
        assert player.display_name == "NewName"
        assert player.games_with_me == 2  # Appeared in 2 games
    finally:
        session.close()