"""Celery tasks for background replay processing."""

import hashlib
import json
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


def get_db_session():
    """Get a database session for worker tasks."""
    from rlcoach.db.session import create_session, init_db

    # Initialize DB if not already done
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        from rlcoach.db.session import init_db_from_url

        init_db_from_url(database_url)
    else:
        init_db()

    return create_session()


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
    soft_time_limit=60,
    time_limit=90,
)
def process_replay(self, upload_id: str) -> dict:
    """
    Process a single replay file.

    Args:
        upload_id: UUID of the UploadedReplay record

    Returns:
        dict with processing result
    """
    logger.info(f"Processing replay {upload_id}")

    session = get_db_session()
    try:
        from rlcoach.db import UploadedReplay, UserReplay

        # Get the upload record
        upload = session.query(UploadedReplay).filter_by(id=upload_id).first()
        if not upload:
            logger.error(f"Upload record not found: {upload_id}")
            return {"status": "failed", "error": "Upload not found"}

        # Update status to processing
        upload.status = "processing"
        session.commit()

        # Validate file exists
        replay_path = Path(upload.stored_path)
        if not replay_path.exists():
            upload.status = "failed"
            upload.error_message = "File not found"
            session.commit()
            return {"status": "failed", "error": "File not found"}

        # Create output directory
        output_dir = STORAGE_PATH / "parsed" / upload.user_id
        output_dir.mkdir(parents=True, exist_ok=True)

        # Run the parsing pipeline
        result = _run_parser_subprocess(replay_path, output_dir, upload_id)

        if result["status"] == "success":
            # Read the parsed JSON to extract replay_id and metadata
            output_file = Path(result["output_path"])
            if output_file.exists():
                with open(output_file) as f:
                    parsed_data = json.load(f)

                # Extract replay_id from parsed data
                replay_id = parsed_data.get("metadata", {}).get("replay_id")
                if replay_id:
                    upload.replay_id = replay_id

                    # Create UserReplay association
                    user_replay = UserReplay(
                        user_id=upload.user_id,
                        replay_id=replay_id,
                        ownership_type="uploaded",
                    )
                    session.merge(user_replay)

            upload.status = "completed"
            upload.processed_at = datetime.now(timezone.utc)
            session.commit()
            logger.info(f"Successfully processed replay {upload_id}")
        else:
            upload.status = "failed"
            upload.error_message = result.get("error", "Unknown error")[:500]
            session.commit()
            logger.error(f"Failed to process replay {upload_id}: {result.get('error')}")

        return result

    except SoftTimeLimitExceeded:
        logger.warning(f"Soft time limit exceeded for replay {upload_id}")
        upload = session.query(UploadedReplay).filter_by(id=upload_id).first()
        if upload:
            upload.status = "failed"
            upload.error_message = "Processing timeout"
            session.commit()
        return {"status": "failed", "error": "Processing timeout"}
    except Exception as e:
        logger.exception(f"Error processing replay {upload_id}")
        upload = session.query(UploadedReplay).filter_by(id=upload_id).first()
        if upload:
            upload.status = "failed"
            upload.error_message = str(e)[:500]
            session.commit()
        raise
    finally:
        session.close()


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
def migrate_to_cold_storage(self, replay_id: str, file_path: str) -> dict:
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
        import b2sdk.v2 as b2

        # Get B2 credentials
        key_id = os.getenv("BACKBLAZE_KEY_ID")
        app_key = os.getenv("BACKBLAZE_APPLICATION_KEY")
        bucket_name = os.getenv("BACKBLAZE_BUCKET_NAME")

        if not all([key_id, app_key, bucket_name]):
            return {
                "status": "failed",
                "error": "B2 credentials not configured",
            }

        # Initialize B2
        info = b2.InMemoryAccountInfo()
        b2_api = b2.B2Api(info)
        b2_api.authorize_account("production", key_id, app_key)
        bucket = b2_api.get_bucket_by_name(bucket_name)

        # Upload file
        local_path = Path(file_path)
        if not local_path.exists():
            return {"status": "failed", "error": "Local file not found"}

        remote_name = f"replays/{replay_id}.replay"
        bucket.upload_local_file(
            local_file=str(local_path),
            file_name=remote_name,
        )

        # Get the download URL
        download_url = f"https://f002.backblazeb2.com/file/{bucket_name}/{remote_name}"

        # Update database with new storage path
        session = get_db_session()
        try:
            from rlcoach.db import UploadedReplay

            upload = (
                session.query(UploadedReplay).filter_by(replay_id=replay_id).first()
            )
            if upload:
                upload.stored_path = download_url
                session.commit()
        finally:
            session.close()

        # Delete local file
        local_path.unlink()

        logger.info(f"Migrated replay {replay_id} to B2: {download_url}")
        return {
            "status": "success",
            "replay_id": replay_id,
            "b2_url": download_url,
        }

    except ImportError:
        return {
            "status": "failed",
            "error": "b2sdk not installed",
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


@celery_app.task
def check_disk_usage() -> dict:
    """
    Check disk usage and return stats.

    Returns:
        dict with disk usage info
    """
    import shutil

    try:
        total, used, free = shutil.disk_usage(STORAGE_PATH)
        usage_pct = (used / total) * 100

        result = {
            "status": "success",
            "total_gb": round(total / (1024**3), 2),
            "used_gb": round(used / (1024**3), 2),
            "free_gb": round(free / (1024**3), 2),
            "usage_percent": round(usage_pct, 1),
        }

        if usage_pct >= 90:
            result["warning"] = "CRITICAL: Disk usage above 90%"
            logger.warning(f"Critical disk usage: {usage_pct:.1f}%")
        elif usage_pct >= 80:
            result["warning"] = "WARNING: Disk usage above 80%"
            logger.warning(f"High disk usage: {usage_pct:.1f}%")

        return result

    except Exception as e:
        logger.exception("Error checking disk usage")
        return {"status": "failed", "error": str(e)}


def get_queue_length() -> int:
    """Get the current length of the replay processing queue."""
    try:
        from rlcoach.worker.celery_app import celery_app

        with celery_app.connection() as conn:
            queue = conn.default_channel.queue_declare(
                "celery", passive=True
            )
            return queue.message_count
    except Exception:
        return 0


def can_accept_upload() -> tuple[bool, str | None]:
    """
    Check if we can accept new uploads.

    Returns:
        Tuple of (can_accept, reason_if_not)
    """
    import shutil

    # Check disk usage
    try:
        total, used, _ = shutil.disk_usage(STORAGE_PATH)
        usage_pct = (used / total) * 100
        if usage_pct >= 90:
            return False, "Disk space low. Please try again later."
    except Exception:
        pass

    # Check queue length
    queue_len = get_queue_length()
    if queue_len >= 1000:
        return False, f"Processing queue full ({queue_len} pending). Try again later."

    return True, None
