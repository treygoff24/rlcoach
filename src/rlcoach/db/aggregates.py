# src/rlcoach/db/aggregates.py
"""Daily stats aggregation.

Computes and stores aggregated statistics per day/playlist
for quick dashboard queries.
"""

from __future__ import annotations

from datetime import date
from sqlalchemy import func

from .session import create_session
from .models import Replay, PlayerGameStats, DailyStats


def update_daily_stats(play_date: date, playlist: str) -> None:
    """Update or create daily stats record for a date/playlist.

    Queries all games for the given day and playlist, computes
    aggregated stats, and upserts to the daily_stats table.

    Args:
        play_date: The local date to aggregate
        playlist: The playlist (DUEL, DOUBLES, STANDARD)
    """
    session = create_session()
    try:
        # Query replays for this date/playlist
        replays = session.query(Replay).filter(
            Replay.play_date == play_date,
            Replay.playlist == playlist,
        ).all()

        if not replays:
            # No games, nothing to do
            return

        # Compute win/loss/draw counts
        games_played = len(replays)
        wins = sum(1 for r in replays if r.result == "WIN")
        losses = sum(1 for r in replays if r.result == "LOSS")
        draws = sum(1 for r in replays if r.result == "DRAW")
        win_rate = (wins / games_played * 100) if games_played > 0 else 0

        # Get all my stats for these replays
        replay_ids = [r.replay_id for r in replays]
        my_stats = session.query(PlayerGameStats).filter(
            PlayerGameStats.replay_id.in_(replay_ids),
            PlayerGameStats.is_me == True,
        ).all()

        # Compute averages
        def safe_avg(values):
            valid = [v for v in values if v is not None]
            return sum(valid) / len(valid) if valid else None

        avg_goals = safe_avg([s.goals for s in my_stats])
        avg_assists = safe_avg([s.assists for s in my_stats])
        avg_saves = safe_avg([s.saves for s in my_stats])
        avg_shots = safe_avg([s.shots for s in my_stats])
        avg_shooting_pct = safe_avg([s.shooting_pct for s in my_stats])
        avg_bcpm = safe_avg([s.bcpm for s in my_stats])
        avg_boost = safe_avg([s.avg_boost for s in my_stats])
        avg_speed_kph = safe_avg([s.avg_speed_kph for s in my_stats])
        avg_behind_ball_pct = safe_avg([s.behind_ball_pct for s in my_stats])
        avg_first_man_pct = safe_avg([s.first_man_pct for s in my_stats])

        # Compute supersonic pct from time (assuming 300s games, rough estimate)
        supersonic_times = [s.time_supersonic_s for s in my_stats if s.time_supersonic_s is not None]
        if supersonic_times:
            # Assume average game ~300s, convert to percentage
            avg_supersonic_pct = (sum(supersonic_times) / len(supersonic_times)) / 300 * 100
        else:
            avg_supersonic_pct = None

        # Challenge win pct
        total_wins = sum(s.challenge_wins or 0 for s in my_stats)
        total_losses = sum(s.challenge_losses or 0 for s in my_stats)
        total_challenges = total_wins + total_losses
        avg_challenge_win_pct = (total_wins / total_challenges * 100) if total_challenges > 0 else None

        # Upsert daily stats
        existing = session.query(DailyStats).filter_by(
            play_date=play_date,
            playlist=playlist,
        ).first()

        if existing:
            existing.games_played = games_played
            existing.wins = wins
            existing.losses = losses
            existing.draws = draws
            existing.win_rate = win_rate
            existing.avg_goals = avg_goals
            existing.avg_assists = avg_assists
            existing.avg_saves = avg_saves
            existing.avg_shots = avg_shots
            existing.avg_shooting_pct = avg_shooting_pct
            existing.avg_bcpm = avg_bcpm
            existing.avg_boost = avg_boost
            existing.avg_speed_kph = avg_speed_kph
            existing.avg_supersonic_pct = avg_supersonic_pct
            existing.avg_behind_ball_pct = avg_behind_ball_pct
            existing.avg_first_man_pct = avg_first_man_pct
            existing.avg_challenge_win_pct = avg_challenge_win_pct
        else:
            daily = DailyStats(
                play_date=play_date,
                playlist=playlist,
                games_played=games_played,
                wins=wins,
                losses=losses,
                draws=draws,
                win_rate=win_rate,
                avg_goals=avg_goals,
                avg_assists=avg_assists,
                avg_saves=avg_saves,
                avg_shots=avg_shots,
                avg_shooting_pct=avg_shooting_pct,
                avg_bcpm=avg_bcpm,
                avg_boost=avg_boost,
                avg_speed_kph=avg_speed_kph,
                avg_supersonic_pct=avg_supersonic_pct,
                avg_behind_ball_pct=avg_behind_ball_pct,
                avg_first_man_pct=avg_first_man_pct,
                avg_challenge_win_pct=avg_challenge_win_pct,
            )
            session.add(daily)

        session.commit()

    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
