# src/rlcoach/pipeline.py
"""Integrated ingestion pipeline for processing replay files.

This module provides the complete pipeline for:
1. Ingesting replay files (validation, hashing)
2. Generating analysis reports
3. Writing to database
4. Updating daily statistics
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from .config import RLCoachConfig, compute_play_date
from .db.session import init_db
from .db.writer import PlayerNotFoundError, ReplayExistsError, write_report
from .identity import PlayerIdentityResolver
from .ingest import ingest_replay
from .report import generate_report, write_report_atomically

logger = logging.getLogger(__name__)


class IngestionStatus(Enum):
    """Status of replay ingestion."""

    SUCCESS = "success"
    DUPLICATE = "duplicate"
    ERROR = "error"
    PLAYER_NOT_FOUND = "player_not_found"
    EXCLUDED = "excluded"


@dataclass
class IngestionResult:
    """Result of processing a replay file."""

    status: IngestionStatus
    path: Path
    replay_id: str | None = None
    file_hash: str | None = None
    error: str | None = None

    def __str__(self) -> str:
        if self.status == IngestionStatus.SUCCESS:
            return f"✓ {self.path.name} -> {self.replay_id}"
        elif self.status == IngestionStatus.DUPLICATE:
            return f"⊘ {self.path.name} (duplicate)"
        elif self.status == IngestionStatus.EXCLUDED:
            return f"⊘ {self.path.name} (excluded)"
        else:
            return f"✗ {self.path.name}: {self.error}"


def process_replay_file(
    path: Path,
    config: RLCoachConfig,
    *,
    adapter_name: str = "rust",
    header_only: bool = False,
) -> IngestionResult:
    """Process a single replay file through the full pipeline.

    This function:
    1. Initializes the database if needed
    2. Ingests the replay file (validation + hashing)
    3. Generates the analysis report
    4. Writes to database (players, replay, stats)

    Args:
        path: Path to the .replay file
        config: RLCoach configuration
        adapter_name: Parser adapter to use
        header_only: Whether to use header-only mode

    Returns:
        IngestionResult with status and details
    """
    try:
        # Initialize database
        init_db(config.db_path)

        # Step 1: Ingest (validate + hash)
        ingest_result = ingest_replay(path)
        file_hash = ingest_result["sha256"]

        # Step 2: Generate report
        report = generate_report(
            path,
            header_only=header_only,
            adapter_name=adapter_name,
            identity_config=config.identity,
        )

        # Check for error report
        if "error" in report:
            return IngestionResult(
                status=IngestionStatus.ERROR,
                path=path,
                error=report.get("error", "Unknown error"),
            )

        # Check if "me" should be excluded
        # Logic: excluded_names are user's accounts they don't want analyzed.
        # If find_me succeeds -> that's "me", can't be excluded (validation
        # prevents overlap).
        # If find_me fails -> check if any player matches excluded_names (that
        # would be "me").
        resolver = PlayerIdentityResolver(config.identity)
        players = report.get("players", [])
        me = resolver.find_me(players)
        if me is None:
            # "me" not found via display_names - check if playing on excluded account
            for player in players:
                display_name = player.get("display_name", "")
                if resolver.should_exclude(display_name):
                    logger.debug(f"Excluded replay (account: {display_name}): {path}")
                    return IngestionResult(
                        status=IngestionStatus.EXCLUDED,
                        path=path,
                    )

        # Add source_file to report
        report["source_file"] = str(path)

        # Step 3: Write JSON report to disk
        # Compute json_report_path matching what insert_replay stores
        metadata = report.get("metadata", {})
        played_at_str = metadata.get("started_at_utc", "")
        if played_at_str:
            played_at_str = played_at_str.replace("Z", "+00:00")
            played_at_utc = datetime.fromisoformat(played_at_str)
        else:
            played_at_utc = datetime.now(timezone.utc)
        play_date = compute_play_date(played_at_utc, config.preferences.timezone)

        replay_id = report.get("replay_id", file_hash[:16])
        json_report_path = (
            config.paths.reports_dir / play_date.isoformat() / f"{replay_id}.json"
        )
        write_report_atomically(report, json_report_path, pretty=True)

        # Step 4: Write to database
        write_report(report, file_hash, config)

        logger.info(f"Processed {path} -> {replay_id}")

        return IngestionResult(
            status=IngestionStatus.SUCCESS,
            path=path,
            replay_id=replay_id,
            file_hash=file_hash,
        )

    except ReplayExistsError as e:
        logger.debug(f"Duplicate replay: {path}")
        return IngestionResult(
            status=IngestionStatus.DUPLICATE,
            path=path,
            error=str(e),
        )

    except PlayerNotFoundError as e:
        logger.warning(f"Player not found in replay: {path}")
        return IngestionResult(
            status=IngestionStatus.PLAYER_NOT_FOUND,
            path=path,
            error=str(e),
        )

    except Exception as e:
        logger.error(f"Error processing {path}: {e}")
        return IngestionResult(
            status=IngestionStatus.ERROR,
            path=path,
            error=str(e),
        )


def process_batch(
    paths: list[Path],
    config: RLCoachConfig,
    *,
    adapter_name: str = "rust",
    header_only: bool = False,
    on_progress: callable | None = None,
) -> list[IngestionResult]:
    """Process multiple replay files.

    Args:
        paths: List of paths to replay files
        config: RLCoach configuration
        adapter_name: Parser adapter to use
        header_only: Whether to use header-only mode
        on_progress: Optional callback(index, total, result) for progress

    Returns:
        List of IngestionResults
    """
    results = []
    total = len(paths)

    for i, path in enumerate(paths):
        result = process_replay_file(
            path,
            config,
            adapter_name=adapter_name,
            header_only=header_only,
        )
        results.append(result)

        if on_progress:
            on_progress(i + 1, total, result)

    return results
