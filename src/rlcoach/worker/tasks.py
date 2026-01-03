"""Celery tasks for background replay processing."""

import logging
import os
import resource
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from celery.exceptions import SoftTimeLimitExceeded

from rlcoach.worker.celery_app import celery_app

logger = logging.getLogger(__name__)

# Memory limit for parsing (512MB in bytes)
MEMORY_LIMIT_BYTES = 512 * 1024 * 1024

# Storage paths
STORAGE_PATH = Path(os.getenv("STORAGE_PATH", "/app/storage"))
TEMP_PATH = Path(os.getenv("TEMP_PATH", "/tmp/rlcoach"))


def set_memory_limit():
    """Set memory limit for subprocess."""
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT_BYTES, MEMORY_LIMIT_BYTES))


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
)
def process_replay(
    self,
    upload_id: str,
    file_path: str,
    user_id: str,
) -> dict:
    """
    Process a single replay file.

    Args:
        upload_id: UUID of the UploadedReplay record
        file_path: Path to the .replay file
        user_id: UUID of the user who uploaded

    Returns:
        dict with processing result
    """
    logger.info(f"Processing replay {upload_id} for user {user_id}")

    try:
        # Validate file exists
        replay_path = Path(file_path)
        if not replay_path.exists():
            logger.error(f"Replay file not found: {file_path}")
            return {
                "status": "failed",
                "error": "File not found",
                "upload_id": upload_id,
            }

        # Create output directory
        output_dir = STORAGE_PATH / "parsed" / user_id
        output_dir.mkdir(parents=True, exist_ok=True)

        # Run the parsing pipeline in a subprocess with memory limits
        result = _run_parser_subprocess(replay_path, output_dir, upload_id)

        if result["status"] == "success":
            # Update database with results
            # This will be implemented when we have async DB session
            logger.info(f"Successfully processed replay {upload_id}")
        else:
            logger.error(f"Failed to process replay {upload_id}: {result.get('error')}")

        return result

    except SoftTimeLimitExceeded:
        logger.warning(f"Soft time limit exceeded for replay {upload_id}")
        return {
            "status": "failed",
            "error": "Processing timeout",
            "upload_id": upload_id,
        }
    except Exception:
        logger.exception(f"Error processing replay {upload_id}")
        raise  # Let Celery handle retry


def _run_parser_subprocess(
    replay_path: Path,
    output_dir: Path,
    upload_id: str,
) -> dict:
    """Run the replay parser in a subprocess with resource limits."""
    output_file = output_dir / f"{upload_id}.json"

    try:
        # Build the command
        cmd = [
            "python",
            "-m",
            "rlcoach.cli",
            "analyze",
            str(replay_path),
            "--adapter",
            "rust",
            "--out",
            str(output_dir),
            "--pretty",
        ]

        # Run with timeout and memory limits
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            preexec_fn=set_memory_limit,
            env={**os.environ, "PYTHONPATH": "src"},
        )

        if result.returncode == 0:
            return {
                "status": "success",
                "upload_id": upload_id,
                "output_path": str(output_file),
            }
        else:
            return {
                "status": "failed",
                "upload_id": upload_id,
                "error": result.stderr[:500] if result.stderr else "Unknown error",
            }

    except subprocess.TimeoutExpired:
        return {
            "status": "failed",
            "upload_id": upload_id,
            "error": "Parser timeout (30s)",
        }
    except Exception as e:
        return {
            "status": "failed",
            "upload_id": upload_id,
            "error": str(e),
        }


@celery_app.task(bind=True)
def migrate_to_cold_storage(
    self,
    replay_id: str,
    file_path: str,
) -> dict:
    """
    Migrate an old replay file to Backblaze B2 cold storage.

    Args:
        replay_id: UUID of the replay
        file_path: Current local path to the replay file

    Returns:
        dict with migration result
    """
    logger.info(f"Migrating replay {replay_id} to cold storage")

    try:
        # This will use the B2 SDK when implemented
        # For now, just log the intent
        return {
            "status": "pending",
            "replay_id": replay_id,
            "message": "Cold storage migration not yet implemented",
        }
    except Exception as e:
        logger.exception(f"Error migrating replay {replay_id}")
        return {
            "status": "failed",
            "replay_id": replay_id,
            "error": str(e),
        }


@celery_app.task
def cleanup_temp_files(max_age_hours: int = 24) -> dict:
    """
    Clean up temporary files older than max_age_hours.

    Args:
        max_age_hours: Maximum age of temp files in hours

    Returns:
        dict with cleanup stats
    """
    logger.info(f"Cleaning up temp files older than {max_age_hours} hours")

    deleted_count = 0
    freed_bytes = 0

    try:
        TEMP_PATH.mkdir(parents=True, exist_ok=True)
        cutoff = datetime.now(timezone.utc).timestamp() - (max_age_hours * 3600)

        for file_path in TEMP_PATH.rglob("*"):
            if file_path.is_file() and file_path.stat().st_mtime < cutoff:
                size = file_path.stat().st_size
                file_path.unlink()
                deleted_count += 1
                freed_bytes += size

        logger.info(f"Cleaned up {deleted_count} files, freed {freed_bytes} bytes")

        return {
            "status": "success",
            "deleted_count": deleted_count,
            "freed_bytes": freed_bytes,
        }
    except Exception as e:
        logger.exception("Error cleaning up temp files")
        return {
            "status": "failed",
            "error": str(e),
            "deleted_count": deleted_count,
        }
