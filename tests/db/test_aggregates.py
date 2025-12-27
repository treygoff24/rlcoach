# tests/db/test_aggregates.py
"""Tests for daily stats aggregation."""

from datetime import date, datetime, timezone

import pytest

from rlcoach.db.aggregates import update_daily_stats
from rlcoach.db.models import DailyStats, Player, PlayerGameStats, Replay
from rlcoach.db.session import create_session, init_db, reset_engine


@pytest.fixture(autouse=True)
def reset_db():
    yield
    reset_engine()


def _create_test_data(session, play_date: date, games: list[dict]):
    """Create test replays with stats."""
    # Ensure player exists
    if not session.get(Player, "steam:me123"):
        session.add(Player(player_id="steam:me123", display_name="Me", is_me=True))
        session.commit()

    # Count existing replays to avoid ID collision
    existing_count = session.query(Replay).filter(Replay.play_date == play_date).count()

    for i, game in enumerate(games):
        replay_id = f"replay_{play_date.isoformat()}_{existing_count + i}"
        session.add(Replay(
            replay_id=replay_id,
            source_file=f"/path/{replay_id}.replay",
            file_hash=f"hash_{replay_id}",
            played_at_utc=datetime.now(timezone.utc),
            play_date=play_date,
            map="DFH Stadium",
            playlist=game["playlist"],
            team_size=2,
            duration_seconds=300.0,
            my_player_id="steam:me123",
            my_team="BLUE",
            my_score=game["my_score"],
            opponent_score=game["opp_score"],
            result=game["result"],
            json_report_path=f"/path/{replay_id}.json",
        ))
        session.add(PlayerGameStats(
            replay_id=replay_id,
            player_id="steam:me123",
            team="BLUE",
            is_me=True,
            goals=game.get("goals", 0),
            assists=game.get("assists", 0),
            saves=game.get("saves", 0),
            shots=game.get("shots", 0),
            bcpm=game.get("bcpm"),
            avg_boost=game.get("avg_boost"),
            avg_speed_kph=game.get("avg_speed_kph"),
            behind_ball_pct=game.get("behind_ball_pct"),
        ))
    session.commit()


def test_update_daily_stats_creates_record(tmp_path):
    """Should create daily stats record from games."""
    db_path = tmp_path / "test.db"
    init_db(db_path)

    session = create_session()
    today = date(2024, 12, 23)

    _create_test_data(session, today, [
        {"playlist": "DOUBLES", "result": "WIN", "my_score": 3, "opp_score": 1,
         "goals": 2, "assists": 1, "saves": 1, "shots": 4, "bcpm": 380.0},
        {"playlist": "DOUBLES", "result": "LOSS", "my_score": 1, "opp_score": 3,
         "goals": 1, "assists": 0, "saves": 2, "shots": 3, "bcpm": 350.0},
        {"playlist": "DOUBLES", "result": "WIN", "my_score": 2, "opp_score": 1,
         "goals": 1, "assists": 1, "saves": 1, "shots": 3, "bcpm": 400.0},
    ])
    session.close()

    update_daily_stats(today, "DOUBLES")

    session = create_session()
    try:
        daily = session.query(DailyStats).filter_by(
            play_date=today, playlist="DOUBLES"
        ).first()

        assert daily is not None
        assert daily.games_played == 3
        assert daily.wins == 2
        assert daily.losses == 1
        assert daily.win_rate == pytest.approx(2/3 * 100, rel=0.01)
        assert daily.avg_goals == pytest.approx(4/3, rel=0.01)  # (2+1+1)/3
        assert daily.avg_bcpm == pytest.approx(376.67, rel=0.01)  # (380+350+400)/3
    finally:
        session.close()


def test_update_daily_stats_updates_existing(tmp_path):
    """Should update existing record when re-aggregated."""
    db_path = tmp_path / "test.db"
    init_db(db_path)

    session = create_session()
    today = date(2024, 12, 23)

    # Create initial games
    _create_test_data(session, today, [
        {"playlist": "DOUBLES", "result": "WIN", "my_score": 2, "opp_score": 1,
         "goals": 1, "bcpm": 350.0},
    ])
    session.close()

    # First aggregation
    update_daily_stats(today, "DOUBLES")

    # Verify initial state
    session = create_session()
    daily = session.query(DailyStats).filter_by(play_date=today, playlist="DOUBLES").first()
    assert daily.games_played == 1
    session.close()

    # Add more games
    session = create_session()
    _create_test_data(session, today, [
        {"playlist": "DOUBLES", "result": "WIN", "my_score": 3, "opp_score": 0,
         "goals": 2, "bcpm": 400.0},
    ])
    session.close()

    # Re-aggregate
    update_daily_stats(today, "DOUBLES")

    # Verify updated
    session = create_session()
    try:
        daily = session.query(DailyStats).filter_by(play_date=today, playlist="DOUBLES").first()
        assert daily.games_played == 2  # Now 2 games
        assert daily.wins == 2
    finally:
        session.close()


def test_update_daily_stats_no_games(tmp_path):
    """Should handle no games gracefully."""
    db_path = tmp_path / "test.db"
    init_db(db_path)

    today = date(2024, 12, 23)
    update_daily_stats(today, "DOUBLES")

    session = create_session()
    try:
        daily = session.query(DailyStats).filter_by(
            play_date=today, playlist="DOUBLES"
        ).first()
        # Either no record or zero games
        assert daily is None or daily.games_played == 0
    finally:
        session.close()
