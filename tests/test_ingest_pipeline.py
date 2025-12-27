# tests/test_ingest_pipeline.py
"""Tests for the integrated ingestion pipeline."""

from unittest.mock import patch

import pytest

from rlcoach.db.writer import ReplayExistsError
from rlcoach.pipeline import (
    IngestionResult,
    IngestionStatus,
    process_replay_file,
)


@pytest.fixture
def mock_config(tmp_path):
    """Create a mock config for testing."""
    from rlcoach.config import (
        IdentityConfig,
        PathsConfig,
        PreferencesConfig,
        RLCoachConfig,
    )

    return RLCoachConfig(
        identity=IdentityConfig(
            platform_ids=["steam:me123"],
            display_names=["TestPlayer"],
        ),
        paths=PathsConfig(
            watch_folder=tmp_path / "replays",
            data_dir=tmp_path / "data",
            reports_dir=tmp_path / "reports",
        ),
        preferences=PreferencesConfig(
            primary_playlist="DOUBLES",
            target_rank="GC1",
        ),
    )


class TestProcessReplayFile:
    """Tests for process_replay_file function."""

    def test_process_replay_returns_result(self, mock_config, tmp_path):
        """Should return IngestionResult with correct status."""
        # Create a minimal mock replay file path
        replay_path = tmp_path / "test.replay"
        replay_path.write_bytes(b"x" * 100)

        # Mock the pipeline components
        with (
            patch("rlcoach.pipeline.ingest_replay") as mock_ingest,
            patch("rlcoach.pipeline.generate_report") as mock_report,
            patch("rlcoach.pipeline.write_report") as mock_write,
            patch("rlcoach.pipeline.init_db"),
        ):

            mock_ingest.return_value = {"sha256": "abc123", "status": "success"}
            mock_report.return_value = {
                "replay_id": "test123",
                "players": [],
                "metadata": {},
                "teams": {"blue": {"score": 0}, "orange": {"score": 0}},
            }
            mock_write.return_value = "test123"

            result = process_replay_file(replay_path, mock_config)

            assert isinstance(result, IngestionResult)
            assert result.status == IngestionStatus.SUCCESS
            assert result.replay_id == "test123"

    def test_process_replay_handles_duplicate(self, mock_config, tmp_path):
        """Should return DUPLICATE status for existing replays."""
        replay_path = tmp_path / "test.replay"
        replay_path.write_bytes(b"x" * 100)

        with (
            patch("rlcoach.pipeline.ingest_replay") as mock_ingest,
            patch("rlcoach.pipeline.generate_report") as mock_report,
            patch("rlcoach.pipeline.write_report") as mock_write,
            patch("rlcoach.pipeline.init_db"),
        ):

            mock_ingest.return_value = {"sha256": "abc123", "status": "success"}
            mock_report.return_value = {
                "replay_id": "test123",
                "players": [],
                "metadata": {},
                "teams": {"blue": {"score": 0}, "orange": {"score": 0}},
            }
            mock_write.side_effect = ReplayExistsError("Duplicate")

            result = process_replay_file(replay_path, mock_config)

            assert result.status == IngestionStatus.DUPLICATE

    def test_process_replay_handles_error(self, mock_config, tmp_path):
        """Should return ERROR status on failure."""
        replay_path = tmp_path / "test.replay"
        replay_path.write_bytes(b"x" * 100)

        with (
            patch("rlcoach.pipeline.ingest_replay") as mock_ingest,
            patch("rlcoach.pipeline.init_db"),
        ):

            mock_ingest.side_effect = ValueError("Parse error")

            result = process_replay_file(replay_path, mock_config)

            assert result.status == IngestionStatus.ERROR
            assert "Parse error" in result.error

    def test_process_replay_initializes_database(self, mock_config, tmp_path):
        """Should initialize database before processing."""
        replay_path = tmp_path / "test.replay"
        replay_path.write_bytes(b"x" * 100)

        with (
            patch("rlcoach.pipeline.ingest_replay") as mock_ingest,
            patch("rlcoach.pipeline.generate_report") as mock_report,
            patch("rlcoach.pipeline.write_report") as mock_write,
            patch("rlcoach.pipeline.init_db") as mock_init,
        ):

            mock_ingest.return_value = {"sha256": "abc123", "status": "success"}
            mock_report.return_value = {
                "replay_id": "test123",
                "players": [],
                "metadata": {},
                "teams": {"blue": {"score": 0}, "orange": {"score": 0}},
            }
            mock_write.return_value = "test123"

            process_replay_file(replay_path, mock_config)

            mock_init.assert_called_once_with(mock_config.db_path)

    def test_process_replay_excludes_when_me_is_excluded(self, tmp_path):
        """Should return EXCLUDED status when 'me' matches an excluded name."""
        from rlcoach.config import (
            IdentityConfig,
            PathsConfig,
            PreferencesConfig,
            RLCoachConfig,
        )

        # Config with excluded account
        config = RLCoachConfig(
            identity=IdentityConfig(
                display_names=["MainAccount"],
                excluded_names=["CasualAccount"],
            ),
            paths=PathsConfig(
                watch_folder=tmp_path / "replays",
                data_dir=tmp_path / "data",
                reports_dir=tmp_path / "reports",
            ),
            preferences=PreferencesConfig(),
        )

        replay_path = tmp_path / "test.replay"
        replay_path.write_bytes(b"x" * 100)

        with (
            patch("rlcoach.pipeline.ingest_replay") as mock_ingest,
            patch("rlcoach.pipeline.generate_report") as mock_report,
            patch("rlcoach.pipeline.init_db"),
        ):

            mock_ingest.return_value = {"sha256": "abc123", "status": "success"}
            # "me" is playing as CasualAccount (excluded)
            mock_report.return_value = {
                "replay_id": "test123",
                "players": [
                    {"player_id": "steam:123", "display_name": "CasualAccount"},
                    {"player_id": "steam:456", "display_name": "Opponent"},
                ],
                "metadata": {},
                "teams": {"blue": {"score": 0}, "orange": {"score": 0}},
            }

            result = process_replay_file(replay_path, config)

            assert result.status == IngestionStatus.EXCLUDED

    def test_process_replay_not_excluded_when_only_opponent_matches(self, tmp_path):
        """Should NOT exclude when only an opponent matches excluded name."""
        from rlcoach.config import (
            IdentityConfig,
            PathsConfig,
            PreferencesConfig,
            RLCoachConfig,
        )

        # Config with excluded account
        config = RLCoachConfig(
            identity=IdentityConfig(
                display_names=["MainAccount"],
                excluded_names=["CasualAccount"],
            ),
            paths=PathsConfig(
                watch_folder=tmp_path / "replays",
                data_dir=tmp_path / "data",
                reports_dir=tmp_path / "reports",
            ),
            preferences=PreferencesConfig(),
        )

        replay_path = tmp_path / "test.replay"
        replay_path.write_bytes(b"x" * 100)

        with (
            patch("rlcoach.pipeline.ingest_replay") as mock_ingest,
            patch("rlcoach.pipeline.generate_report") as mock_report,
            patch("rlcoach.pipeline.write_report") as mock_write,
            patch("rlcoach.pipeline.init_db"),
        ):

            mock_ingest.return_value = {"sha256": "abc123", "status": "success"}
            # "me" is MainAccount, opponent happens to be CasualAccount
            mock_report.return_value = {
                "replay_id": "test123",
                "players": [
                    {"player_id": "steam:123", "display_name": "MainAccount"},
                    {"player_id": "steam:456", "display_name": "CasualAccount"},
                ],
                "metadata": {},
                "teams": {"blue": {"score": 0}, "orange": {"score": 0}},
            }
            mock_write.return_value = "test123"

            result = process_replay_file(replay_path, config)

            # Should NOT be excluded - CasualAccount is an opponent, not "me"
            assert result.status == IngestionStatus.SUCCESS
