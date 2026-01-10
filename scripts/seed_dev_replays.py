#!/usr/bin/env python3
"""Seed database with test replays for dev user.

Usage: DATABASE_URL="sqlite:///data/rlcoach_dev.db" python scripts/seed_dev_replays.py
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from datetime import datetime, timezone
import hashlib

from rlcoach.db.session import init_db_from_url, create_session
from rlcoach.db.models import Base, Player, PlayerGameStats, Replay, User, UserReplay
from rlcoach.report import generate_report

# Dev user ID must match auth.ts DevCredentials
DEV_USER_ID = "dev-user-123"
REPLAYS_DIR = Path(__file__).parent.parent / "replays"


def main():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("Error: DATABASE_URL environment variable required")
        print("Example: DATABASE_URL='sqlite:////path/to/db.sqlite' python scripts/seed_dev_replays.py")
        return 1

    print(f"Database: {database_url}")
    print(f"Replays dir: {REPLAYS_DIR}")

    # Initialize database
    engine = init_db_from_url(database_url)
    Base.metadata.create_all(engine)
    session = create_session()

    # Create dev user if not exists
    user = session.query(User).filter_by(id=DEV_USER_ID).first()
    if not user:
        user = User(
            id=DEV_USER_ID,
            email="dev@localhost",
            display_name="Dev User",
            subscription_tier="pro",
        )
        session.add(user)
        session.commit()
        print(f"Created dev user: {DEV_USER_ID}")
    else:
        print(f"Dev user exists: {DEV_USER_ID}")

    # Find replay files
    replay_files = list(REPLAYS_DIR.glob("*.replay"))
    print(f"Found {len(replay_files)} replay files")

    if not replay_files:
        print("No replay files found!")
        return 1

    # Process replays
    success = 0
    skipped = 0
    errors = 0

    for i, replay_path in enumerate(replay_files):
        # Compute file hash for dedup
        with open(replay_path, "rb") as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()

        # Check if already exists by hash
        existing = session.query(Replay).filter_by(file_hash=file_hash).first()
        if existing:
            # Just ensure user ownership
            user_replay = session.query(UserReplay).filter_by(
                user_id=DEV_USER_ID, replay_id=existing.replay_id
            ).first()
            if not user_replay:
                user_replay = UserReplay(
                    user_id=DEV_USER_ID,
                    replay_id=existing.replay_id,
                    ownership_type="uploaded",
                )
                session.add(user_replay)
                session.commit()
            skipped += 1
            continue

        try:
            # Generate full report
            report = generate_report(replay_path, header_only=False, adapter_name="rust")

            if "error" in report:
                errors += 1
                if errors <= 5:
                    print(f"  Error parsing {replay_path.name}: {report.get('details', report['error'])}")
                continue

            # Extract metadata
            replay_id = report.get("replay_id", file_hash[:16])
            metadata = report.get("metadata", {})

            # Parse played_at
            played_at_str = metadata.get("played_at_utc") or metadata.get("date")
            if played_at_str:
                try:
                    if isinstance(played_at_str, str):
                        played_at = datetime.fromisoformat(played_at_str.replace("Z", "+00:00"))
                    else:
                        played_at = played_at_str
                except:
                    played_at = datetime.now(timezone.utc)
            else:
                played_at = datetime.now(timezone.utc)

            # Make timezone aware if not
            if played_at.tzinfo is None:
                played_at = played_at.replace(tzinfo=timezone.utc)

            # Get game info
            game_info = report.get("game_info", {})
            teams = report.get("teams", {})

            # Determine result
            my_team_key = None
            my_score = None
            opp_score = None
            result = None

            for team_key, team_data in teams.items():
                if team_data.get("is_my_team"):
                    my_team_key = team_key
                    my_score = team_data.get("score", 0)
                else:
                    opp_score = team_data.get("score", 0)

            if my_score is not None and opp_score is not None:
                if my_score > opp_score:
                    result = "WIN"
                elif my_score < opp_score:
                    result = "LOSS"
                else:
                    result = "DRAW"

            # Create Replay record
            replay = Replay(
                replay_id=replay_id,
                source_file=str(replay_path),
                file_hash=file_hash,
                match_id=metadata.get("match_guid"),
                played_at_utc=played_at,
                play_date=played_at.date(),
                map=metadata.get("map", "Unknown"),
                playlist=metadata.get("playlist", "Unknown"),
                team_size=metadata.get("team_size", 3),
                duration_seconds=metadata.get("duration_seconds", 300),
                overtime=metadata.get("overtime", False),
                my_team=my_team_key,
                my_score=my_score,
                opponent_score=opp_score,
                result=result,
            )
            session.add(replay)

            # Create UserReplay link
            user_replay = UserReplay(
                user_id=DEV_USER_ID,
                replay_id=replay.replay_id,
                ownership_type="uploaded",
            )
            session.add(user_replay)

            # Create players and stats from report
            players_data = report.get("players", [])
            for player_data in players_data:
                player_id = player_data.get("player_id") or player_data.get("unique_id") or player_data.get("name", f"unknown_{i}")

                # Get or create player
                player = session.query(Player).filter_by(player_id=player_id).first()
                if not player:
                    player = Player(
                        player_id=player_id,
                        display_name=player_data.get("name", "Unknown"),
                        platform=player_data.get("platform"),
                        is_me=player_data.get("is_me", False),
                    )
                    session.add(player)

                # Create game stats
                core_stats = player_data.get("core_stats", {})
                stats = PlayerGameStats(
                    replay_id=replay.replay_id,
                    player_id=player_id,
                    team=str(player_data.get("team", 0)),
                    score=core_stats.get("score", 0),
                    goals=core_stats.get("goals", 0),
                    assists=core_stats.get("assists", 0),
                    saves=core_stats.get("saves", 0),
                    shots=core_stats.get("shots", 0),
                    is_me=player_data.get("is_me", False),
                )
                session.add(stats)

            session.commit()
            success += 1

            if (i + 1) % 20 == 0:
                print(f"  Processed {i + 1}/{len(replay_files)}... ({success} success, {errors} errors)")

        except Exception as e:
            session.rollback()
            errors += 1
            if errors <= 5:
                print(f"  Error processing {replay_path.name}: {e}")

    print()
    print(f"Done! Success: {success}, Skipped: {skipped}, Errors: {errors}")
    print(f"Total replays for dev user: {session.query(UserReplay).filter_by(user_id=DEV_USER_ID).count()}")

    session.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
