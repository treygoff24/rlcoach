"""Abstract parser interface for replay file adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from .types import Header, NetworkFrames


class ParserAdapter(ABC):
    """Abstract base class for replay parser adapters.

    This interface defines the contract that all parser adapters must implement.
    Adapters can specialize in different parsing approaches (e.g., Rust-based,
    Haskell-based, or Python-based parsers) while providing a consistent interface.

    The interface supports graceful degradation: if network frame parsing fails,
    adapters should still attempt to provide header-only information with
    appropriate quality warnings.
    """

    @abstractmethod
    def parse_header(self, path: Path) -> Header:
        """Parse header information from a replay file.

        This method should extract basic match information that is typically
        available in the replay header without requiring full network frame parsing.

        Args:
            path: Path to the replay file

        Returns:
            Header object with match metadata and player information

        Raises:
            HeaderParseError: If header parsing fails completely
            ReplayFileNotFoundError: If the file doesn't exist
            ReplayIOError: If there's an I/O error reading the file
        """
        pass

    @abstractmethod
    def parse_network(self, path: Path) -> NetworkFrames | None:
        """Parse network frame data from a replay file.

        This method attempts to extract detailed frame-by-frame data including
        ball and player positions, boost pickups, and other game events.

        Note: This method should only return None when network frame parsing is
        unavailable for the adapter itself (for example, missing runtime support).
        Adapters that support network parsing should return a NetworkFrames object
        and expose degraded parse diagnostics on that object when parsing fails.

        Args:
            path: Path to the replay file

        Returns:
            NetworkFrames object with frame data, or None if parsing fails/unsupported

        Raises:
            NetworkParseError: If parsing fails in an unexpected way
            ReplayFileNotFoundError: If the file doesn't exist
            ReplayIOError: If there's an I/O error reading the file
        """
        pass

    @property
    def backend_chain(self) -> list[str]:
        """Ordered parser backend identifiers used by this adapter.

        Adapters with a single backend can return one item. Adapters without
        backend chaining support can return an empty list.
        """
        return []

    @property
    @abstractmethod
    def name(self) -> str:
        """Get the name identifier for this adapter.

        Returns:
            String identifier (e.g., "null", "rust_boxcars", "haskell_rattletrap")
        """
        pass

    @property
    @abstractmethod
    def supports_network_parsing(self) -> bool:
        """Check if this adapter supports network frame parsing.

        Returns:
            True if the adapter can parse network frames, False for header-only
        """
        pass
