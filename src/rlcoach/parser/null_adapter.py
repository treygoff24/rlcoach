"""Null parser adapter that provides header-only fallback functionality."""

from __future__ import annotations

from pathlib import Path

from ..ingest import ingest_replay
from .errors import HeaderParseError
from .interface import ParserAdapter
from .types import Header, NetworkFrames, PlayerInfo


class NullAdapter(ParserAdapter):
    """Null parser adapter that provides minimal header information.

    This adapter serves as a fallback when full replay parsing is not available.
    It leverages the existing ingest module to validate files and extract
    basic information, but returns placeholder values for most fields.

    The null adapter always includes a quality warning indicating that
    network frame data was not parsed.
    """

    @property
    def name(self) -> str:
        """Get the adapter name."""
        return "null"

    @property
    def supports_network_parsing(self) -> bool:
        """Null adapter does not support network parsing."""
        return False

    def parse_header(self, path: Path) -> Header:
        """Parse minimal header information from a replay file.

        This implementation uses the existing ingest module to validate
        the file and extract basic metadata, then returns a Header with
        placeholder values and a quality warning.

        Args:
            path: Path to the replay file

        Returns:
            Header with minimal information and quality warning

        Raises:
            HeaderParseError: If the file cannot be processed
        """
        try:
            # Use existing ingest validation to check file
            ingest_result = ingest_replay(path)

            # Extract basic file information
            file_size_mb = ingest_result["size_bytes"] / (1024 * 1024)

            # Create minimal header with placeholders
            quality_warnings = [
                "network_data_unparsed_fallback_header_only",
                f"using_null_adapter_file_size_{file_size_mb:.1f}mb",
            ]

            # Add any warnings from ingest
            if ingest_result.get("warnings"):
                quality_warnings.extend(ingest_result["warnings"])

            # Create placeholder player info (we don't have real player data)
            placeholder_players = [
                PlayerInfo(name="Unknown Player 1", team=0),
                PlayerInfo(name="Unknown Player 2", team=1),
            ]

            header = Header(
                playlist_id="unknown",
                map_name="unknown",
                team_size=1,  # Conservative default
                team0_score=0,
                team1_score=0,
                match_length=0.0,
                players=placeholder_players,
                quality_warnings=quality_warnings,
            )

            return header

        except Exception as e:
            # Convert any errors to HeaderParseError
            raise HeaderParseError(
                str(path), f"Null adapter failed to process file: {str(e)}"
            ) from e

    def parse_network(self, path: Path) -> NetworkFrames | None:
        """Null adapter always returns None for network frames.

        Args:
            path: Path to the replay file (ignored)

        Returns:
            None (null adapter doesn't support network parsing)
        """
        return None
