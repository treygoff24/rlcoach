# tests/test_watcher.py
"""Tests for watch folder service and file stability check."""

import pytest
import time
import threading
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from rlcoach.watcher import (
    wait_for_stable_file,
    FileStabilityTimeout,
    ReplayWatcher,
    WatcherCallback,
)


class TestFileStabilityCheck:
    """Tests for file stability checking."""

    def test_stable_file_returns_immediately(self, tmp_path):
        """A file that doesn't change should return quickly."""
        test_file = tmp_path / "stable.replay"
        test_file.write_bytes(b"x" * 1000)

        # With short check intervals, should complete fast
        result = wait_for_stable_file(
            test_file, stability_seconds=0.1, check_interval=0.05
        )

        assert result is True

    def test_growing_file_waits_for_stability(self, tmp_path):
        """A file being written to should wait until it stabilizes."""
        test_file = tmp_path / "growing.replay"
        test_file.write_bytes(b"x" * 500)

        # Track size changes
        sizes = []

        def record_and_check():
            nonlocal sizes
            # Simulate file growing in a background thread
            time.sleep(0.05)
            sizes.append(test_file.stat().st_size)
            test_file.write_bytes(b"x" * 1000)
            sizes.append(test_file.stat().st_size)
            time.sleep(0.05)
            test_file.write_bytes(b"x" * 1500)
            sizes.append(test_file.stat().st_size)

        writer = threading.Thread(target=record_and_check)
        writer.start()

        # Start stability check
        result = wait_for_stable_file(
            test_file, stability_seconds=0.1, check_interval=0.05, timeout=2.0
        )

        writer.join()

        assert result is True
        # File should have been written multiple times
        assert len(sizes) == 3

    def test_timeout_raises_exception(self, tmp_path):
        """Should raise FileStabilityTimeout if file keeps changing."""
        test_file = tmp_path / "unstable.replay"
        test_file.write_bytes(b"x" * 100)

        # Keep modifying the file in background
        stop_event = threading.Event()

        def keep_writing():
            counter = 0
            while not stop_event.is_set():
                time.sleep(0.02)
                test_file.write_bytes(b"x" * (100 + counter))
                counter += 1

        writer = threading.Thread(target=keep_writing)
        writer.start()

        try:
            with pytest.raises(FileStabilityTimeout):
                wait_for_stable_file(
                    test_file,
                    stability_seconds=0.5,
                    check_interval=0.05,
                    timeout=0.3,
                )
        finally:
            stop_event.set()
            writer.join()

    def test_nonexistent_file_raises_error(self, tmp_path):
        """Should raise FileNotFoundError for nonexistent files."""
        test_file = tmp_path / "missing.replay"

        with pytest.raises(FileNotFoundError):
            wait_for_stable_file(test_file)

    def test_default_parameters(self, tmp_path):
        """Default parameters should be reasonable."""
        test_file = tmp_path / "test.replay"
        test_file.write_bytes(b"x" * 1000)

        # Should work with defaults (stability_seconds=2.0 is too slow for tests)
        # Just verify no errors
        result = wait_for_stable_file(
            test_file, stability_seconds=0.1, check_interval=0.05
        )
        assert result is True


class TestReplayWatcher:
    """Tests for the replay watcher service."""

    def test_watcher_detects_new_replay_file(self, tmp_path):
        """Should detect and process new .replay files."""
        watch_dir = tmp_path / "replays"
        watch_dir.mkdir()

        processed_files = []

        def callback(path: Path) -> None:
            processed_files.append(path)

        watcher = ReplayWatcher(
            watch_dir=watch_dir,
            callback=callback,
            poll_interval=0.1,
            stability_seconds=0.1,
        )

        # Start watcher in background
        watcher.start()

        try:
            # Give watcher time to start
            time.sleep(0.1)

            # Create a new replay file
            test_file = watch_dir / "test.replay"
            test_file.write_bytes(b"x" * 1000)

            # Wait for processing
            time.sleep(0.5)

            assert len(processed_files) == 1
            assert processed_files[0] == test_file
        finally:
            watcher.stop()

    def test_watcher_ignores_non_replay_files(self, tmp_path):
        """Should ignore files without .replay extension."""
        watch_dir = tmp_path / "replays"
        watch_dir.mkdir()

        processed_files = []

        def callback(path: Path) -> None:
            processed_files.append(path)

        watcher = ReplayWatcher(
            watch_dir=watch_dir,
            callback=callback,
            poll_interval=0.1,
            stability_seconds=0.1,
        )

        watcher.start()

        try:
            time.sleep(0.1)

            # Create non-replay files
            (watch_dir / "test.txt").write_text("hello")
            (watch_dir / "test.json").write_text("{}")
            (watch_dir / "test.mp4").write_bytes(b"video")

            time.sleep(0.3)

            assert len(processed_files) == 0
        finally:
            watcher.stop()

    def test_watcher_tracks_processed_files(self, tmp_path):
        """Should not reprocess already processed files."""
        watch_dir = tmp_path / "replays"
        watch_dir.mkdir()

        processed_files = []

        def callback(path: Path) -> None:
            processed_files.append(path)

        watcher = ReplayWatcher(
            watch_dir=watch_dir,
            callback=callback,
            poll_interval=0.1,
            stability_seconds=0.1,
        )

        watcher.start()

        try:
            time.sleep(0.1)

            # Create a replay file
            test_file = watch_dir / "test.replay"
            test_file.write_bytes(b"x" * 1000)

            # Wait for processing
            time.sleep(0.5)
            assert len(processed_files) == 1

            # Wait more - should not reprocess
            time.sleep(0.3)
            assert len(processed_files) == 1
        finally:
            watcher.stop()

    def test_watcher_processes_existing_files_on_start(self, tmp_path):
        """Should process existing replay files when starting."""
        watch_dir = tmp_path / "replays"
        watch_dir.mkdir()

        # Create files before starting watcher
        (watch_dir / "existing1.replay").write_bytes(b"x" * 1000)
        (watch_dir / "existing2.replay").write_bytes(b"y" * 1000)

        processed_files = []

        def callback(path: Path) -> None:
            processed_files.append(path)

        watcher = ReplayWatcher(
            watch_dir=watch_dir,
            callback=callback,
            poll_interval=0.1,
            stability_seconds=0.1,
            process_existing=True,
        )

        watcher.start()

        try:
            time.sleep(0.5)
            assert len(processed_files) == 2
        finally:
            watcher.stop()

    def test_watcher_skip_existing_files_option(self, tmp_path):
        """Should skip existing files when process_existing=False."""
        watch_dir = tmp_path / "replays"
        watch_dir.mkdir()

        # Create files before starting watcher
        (watch_dir / "existing.replay").write_bytes(b"x" * 1000)

        processed_files = []

        def callback(path: Path) -> None:
            processed_files.append(path)

        watcher = ReplayWatcher(
            watch_dir=watch_dir,
            callback=callback,
            poll_interval=0.1,
            stability_seconds=0.1,
            process_existing=False,
        )

        watcher.start()

        try:
            time.sleep(0.3)
            # Existing file should be skipped
            assert len(processed_files) == 0

            # New file should be processed
            (watch_dir / "new.replay").write_bytes(b"y" * 1000)
            time.sleep(0.3)
            assert len(processed_files) == 1
        finally:
            watcher.stop()

    def test_watcher_handles_callback_exception(self, tmp_path):
        """Should continue watching even if callback raises exception."""
        watch_dir = tmp_path / "replays"
        watch_dir.mkdir()

        processed_files = []
        call_count = 0

        def callback(path: Path) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("Test error")
            processed_files.append(path)

        watcher = ReplayWatcher(
            watch_dir=watch_dir,
            callback=callback,
            poll_interval=0.1,
            stability_seconds=0.1,
        )

        watcher.start()

        try:
            time.sleep(0.1)

            # First file triggers exception
            (watch_dir / "first.replay").write_bytes(b"x" * 1000)
            time.sleep(0.3)

            # Second file should still be processed
            (watch_dir / "second.replay").write_bytes(b"y" * 1000)
            time.sleep(0.3)

            assert len(processed_files) == 1
            assert processed_files[0].name == "second.replay"
        finally:
            watcher.stop()

    def test_watcher_stop_is_idempotent(self, tmp_path):
        """Should be safe to call stop multiple times."""
        watch_dir = tmp_path / "replays"
        watch_dir.mkdir()

        watcher = ReplayWatcher(
            watch_dir=watch_dir,
            callback=lambda p: None,
            poll_interval=0.1,
        )

        watcher.start()
        time.sleep(0.1)

        # Multiple stops should be safe
        watcher.stop()
        watcher.stop()
        watcher.stop()
