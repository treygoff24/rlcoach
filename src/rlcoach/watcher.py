# src/rlcoach/watcher.py
"""Watch folder service and file stability utilities.

This module provides:
- File stability checking (wait for files to finish syncing/writing)
- Directory watching for new replay files
- Integration with the ingestion pipeline
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Callable, Protocol

logger = logging.getLogger(__name__)


class WatcherCallback(Protocol):
    """Protocol for replay watcher callbacks."""

    def __call__(self, path: Path) -> None:
        """Process a replay file.

        Args:
            path: Path to the replay file to process
        """
        ...


class FileStabilityTimeout(Exception):
    """Raised when a file doesn't stabilize within the timeout period."""

    def __init__(self, path: Path, timeout: float):
        self.path = path
        self.timeout = timeout
        super().__init__(
            f"File '{path}' did not stabilize within {timeout} seconds"
        )


def wait_for_stable_file(
    path: Path,
    stability_seconds: float = 2.0,
    check_interval: float = 0.5,
    timeout: float = 60.0,
) -> bool:
    """Wait for a file's size to stabilize before processing.

    This is useful for files being synced (e.g., from Dropbox) or written
    by another process. The file is considered stable when its size hasn't
    changed for `stability_seconds`.

    Args:
        path: Path to the file to monitor
        stability_seconds: Time in seconds the file size must remain unchanged
        check_interval: How often to check the file size
        timeout: Maximum time to wait before raising FileStabilityTimeout

    Returns:
        True if file is stable

    Raises:
        FileNotFoundError: If the file doesn't exist
        FileStabilityTimeout: If the file doesn't stabilize within timeout
    """
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    start_time = time.monotonic()
    last_size = path.stat().st_size
    stable_since = time.monotonic()

    while True:
        elapsed = time.monotonic() - start_time
        if elapsed > timeout:
            raise FileStabilityTimeout(path, timeout)

        time.sleep(check_interval)

        current_size = path.stat().st_size
        if current_size != last_size:
            # File changed, reset stability timer
            last_size = current_size
            stable_since = time.monotonic()
        else:
            # File unchanged, check if stable long enough
            stable_duration = time.monotonic() - stable_since
            if stable_duration >= stability_seconds:
                return True


class ReplayWatcher:
    """Watch a directory for new .replay files and process them.

    This uses polling rather than filesystem events for reliability across
    different platforms and filesystems (especially network/synced folders).

    Example:
        def process_replay(path: Path) -> None:
            print(f"Processing: {path}")

        watcher = ReplayWatcher(
            watch_dir=Path("~/Replays"),
            callback=process_replay,
        )
        watcher.start()
        # ... later ...
        watcher.stop()
    """

    def __init__(
        self,
        watch_dir: Path,
        callback: WatcherCallback,
        poll_interval: float = 2.0,
        stability_seconds: float = 2.0,
        stability_timeout: float = 60.0,
        process_existing: bool = True,
    ):
        """Initialize the replay watcher.

        Args:
            watch_dir: Directory to watch for .replay files
            callback: Function to call for each new replay file
            poll_interval: How often to scan the directory (seconds)
            stability_seconds: How long a file must be unchanged before processing
            stability_timeout: Maximum time to wait for file stability
            process_existing: If True, process existing files on start
        """
        self.watch_dir = watch_dir
        self.callback = callback
        self.poll_interval = poll_interval
        self.stability_seconds = stability_seconds
        self.stability_timeout = stability_timeout
        self.process_existing = process_existing

        self._processed: set[Path] = set()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start watching the directory in a background thread."""
        if self._thread is not None and self._thread.is_alive():
            return

        self._stop_event.clear()

        # If not processing existing, mark them as already processed
        if not self.process_existing:
            for path in self.watch_dir.glob("*.replay"):
                self._processed.add(path)

        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()
        logger.info(f"Started watching {self.watch_dir}")

    def stop(self) -> None:
        """Stop watching and wait for the thread to finish."""
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        self._thread = None
        logger.info(f"Stopped watching {self.watch_dir}")

    def _watch_loop(self) -> None:
        """Main watch loop that runs in background thread."""
        while not self._stop_event.is_set():
            try:
                self._scan_for_new_files()
            except Exception as e:
                logger.error(f"Error during scan: {e}")

            # Wait for poll interval or stop signal
            self._stop_event.wait(self.poll_interval)

    def _scan_for_new_files(self) -> None:
        """Scan directory for new .replay files and process them."""
        if not self.watch_dir.exists():
            return

        for path in self.watch_dir.glob("*.replay"):
            if path in self._processed:
                continue

            if self._stop_event.is_set():
                break

            try:
                # Wait for file to stabilize
                # Use check_interval proportional to stability_seconds
                check_interval = min(0.5, self.stability_seconds / 2)
                wait_for_stable_file(
                    path,
                    stability_seconds=self.stability_seconds,
                    check_interval=check_interval,
                    timeout=self.stability_timeout,
                )

                # Process the file
                self._process_file(path)

            except FileStabilityTimeout:
                logger.warning(
                    f"File {path} did not stabilize, skipping for now"
                )
            except Exception as e:
                logger.error(f"Error processing {path}: {e}")
                # Mark as processed to avoid infinite retry
                self._processed.add(path)

    def _process_file(self, path: Path) -> None:
        """Process a single replay file."""
        try:
            self.callback(path)
            self._processed.add(path)
            logger.info(f"Processed: {path}")
        except Exception as e:
            logger.error(f"Callback error for {path}: {e}")
            # Still mark as processed to avoid infinite retry
            self._processed.add(path)
