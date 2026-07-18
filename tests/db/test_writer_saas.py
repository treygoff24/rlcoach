"""Behavioral coverage for the SaaS report persistence path."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from rlcoach.db.models import OAuthAccount, Player, PlayerGameStats, Replay, User
from rlcoach.db.session import create_session, init_db, reset_engine
from rlcoach.db.writer import ReplayExistsError, write_report_saas


@pytest.fixture
def saas_db(tmp_path):
    init_db(tmp_path / "writer-saas.db")
    yield
    reset_engine()


@pytest.fixture
def saas_report():
    return {
        "replay_id": "saas-replay-1",
        "source_file": "upload.replay",
        "metadata": {
            "started_at_utc": "2026-07-17T12:00:00Z",
            "map": "DFH Stadium",
            "playlist": "DOUBLES",
            "team_size": 2,
            "duration_seconds": 300,
        },
        "teams": {"blue": {"score": 3}, "orange": {"score": 1}},
        "players": [
            {
                "player_id": "discord:player-1",
                "display_name": "Uploader",
                "team": "BLUE",
            },
            {
                "player_id": "epic:teammate",
                "display_name": "Teammate",
                "team": "BLUE",
            },
            {
                "player_id": "steam:opponent",
                "display_name": "Opponent",
                "team": "ORANGE",
            },
        ],
        "analysis": {
            "per_player": {
                "discord:player-1": {"fundamentals": {"goals": 2}},
                "epic:teammate": {"fundamentals": {"assists": 1}},
                "steam:opponent": {"fundamentals": {"saves": 1}},
            }
        },
    }


def test_write_report_saas_resolves_identity_and_persists_roles_atomically(
    saas_db, saas_report
):
    session = create_session()
    session.add(
        User(
            id="user-1",
            email="uploader@example.com",
            token_budget_reset_at=datetime.now(timezone.utc),
        )
    )
    session.add(
        OAuthAccount(
            user_id="user-1",
            type="oauth",
            provider="discord",
            provider_account_id="player-1",
        )
    )
    session.commit()
    session.close()

    replay_id = write_report_saas(
        saas_report,
        file_hash="saas-hash-1",
        json_report_path="/reports/saas-replay-1.json",
        user_id="user-1",
    )

    verify = create_session()
    try:
        replay = verify.get(Replay, replay_id)
        assert replay is not None
        assert (replay.my_player_id, replay.result) == (
            "discord:player-1",
            "WIN",
        )
        assert verify.query(Player).count() == 3
        roles = {
            row.player_id: (row.is_me, row.is_teammate, row.is_opponent)
            for row in verify.query(PlayerGameStats).all()
        }
        assert roles == {
            "discord:player-1": (True, False, False),
            "epic:teammate": (False, True, False),
            "steam:opponent": (False, False, True),
        }
    finally:
        verify.close()


def test_write_report_saas_duplicate_rolls_back_without_partial_rows(
    saas_db, saas_report
):
    write_report_saas(saas_report, "same-hash", "/reports/first.json")

    duplicate = {**saas_report, "replay_id": "different-replay-id"}
    with pytest.raises(ReplayExistsError):
        write_report_saas(duplicate, "same-hash", "/reports/duplicate.json")

    verify = create_session()
    try:
        assert verify.query(Replay).count() == 1
        assert verify.query(PlayerGameStats).count() == 3
    finally:
        verify.close()
