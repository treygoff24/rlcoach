"""Tests for the parser interface and adapters."""

import tempfile
from pathlib import Path
from unittest import mock

import pytest

from rlcoach.parser import (
    AdapterNotFoundError,
    Header,
    HeaderParseError,
    NetworkFrames,
    ParserAdapter,
    PlayerInfo,
    get_adapter,
    list_adapters,
    register_adapter,
)
from rlcoach.parser.interface import ParserAdapter as BaseParserAdapter
from rlcoach.parser.null_adapter import NullAdapter


class TestTypes:
    """Tests for parser data types."""

    def test_player_info_creation(self):
        """Test PlayerInfo dataclass creation."""
        player = PlayerInfo(
            name="TestPlayer", platform_id="steam123", team=0, score=100
        )
        assert player.name == "TestPlayer"
        assert player.platform_id == "steam123"
        assert player.team == 0
        assert player.score == 100

        # Test defaults
        minimal_player = PlayerInfo(name="MinimalPlayer")
        assert minimal_player.platform_id is None
        assert minimal_player.team is None
        assert minimal_player.score == 0

    def test_player_info_immutable(self):
        """Test that PlayerInfo is immutable."""
        player = PlayerInfo(name="TestPlayer")
        with pytest.raises(AttributeError):
            player.name = "NewName"

    def test_header_creation(self):
        """Test Header dataclass creation."""
        players = [
            PlayerInfo(name="Player1", team=0),
            PlayerInfo(name="Player2", team=1),
        ]
        warnings = ["test_warning"]

        header = Header(
            playlist_id="ranked_doubles",
            map_name="DFHStadium",
            team_size=2,
            team0_score=3,
            team1_score=2,
            match_length=300.5,
            players=players,
            quality_warnings=warnings,
        )

        assert header.playlist_id == "ranked_doubles"
        assert header.map_name == "DFHStadium"
        assert header.team_size == 2
        assert header.team0_score == 3
        assert header.team1_score == 2
        assert header.match_length == 300.5
        assert len(header.players) == 2
        assert header.quality_warnings == warnings

    def test_header_defaults(self):
        """Test Header with default values."""
        header = Header()
        assert header.playlist_id is None
        assert header.map_name is None
        assert header.team_size == 0
        assert header.team0_score == 0
        assert header.team1_score == 0
        assert header.match_length == 0.0
        assert header.players == []
        assert header.quality_warnings == []

    def test_header_validation(self):
        """Test Header validation in __post_init__."""
        # Valid header should not raise
        Header(team_size=2, team0_score=3, team1_score=2, match_length=300.0)

        # Invalid team_size
        with pytest.raises(ValueError, match="team_size cannot be negative"):
            Header(team_size=-1)

        # Invalid scores
        with pytest.raises(ValueError, match="team scores cannot be negative"):
            Header(team0_score=-1)

        with pytest.raises(ValueError, match="team scores cannot be negative"):
            Header(team1_score=-1)

        # Invalid match length
        with pytest.raises(ValueError, match="match_length cannot be negative"):
            Header(match_length=-10.0)

    def test_network_frames_creation(self):
        """Test NetworkFrames dataclass creation."""
        frames = NetworkFrames(frame_count=1800, sample_rate=30.0, frames=[])
        assert frames.frame_count == 1800
        assert frames.sample_rate == 30.0
        assert frames.frames == []

    def test_network_frames_validation(self):
        """Test NetworkFrames validation."""
        # Valid frames should not raise
        NetworkFrames(frame_count=1800, sample_rate=30.0)

        # Invalid frame count
        with pytest.raises(ValueError, match="frame_count cannot be negative"):
            NetworkFrames(frame_count=-1)

        # Invalid sample rate
        with pytest.raises(ValueError, match="sample_rate must be positive"):
            NetworkFrames(sample_rate=0)

        with pytest.raises(ValueError, match="sample_rate must be positive"):
            NetworkFrames(sample_rate=-30.0)


class TestParserInterface:
    """Tests for the abstract parser interface."""

    def test_interface_is_abstract(self):
        """Test that ParserAdapter cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseParserAdapter()

    def test_interface_methods_are_abstract(self):
        """Test that interface methods are marked as abstract."""

        # Create a concrete implementation that's missing methods
        class IncompleteAdapter(BaseParserAdapter):
            pass

        with pytest.raises(TypeError):
            IncompleteAdapter()


class TestNullAdapter:
    """Tests for the null adapter implementation."""

    @pytest.fixture
    def adapter(self):
        """Create a null adapter instance."""
        return NullAdapter()

    @pytest.fixture
    def test_replay_file(self):
        """Create a temporary test replay file."""
        # Use the same content as in test_ingest.py - make sure it's binary
        from rlcoach.ingest import REPLAY_MAGIC_SEQUENCES

        magic = REPLAY_MAGIC_SEQUENCES[0]
        # Create properly binary content that won't be detected as text
        header_content = bytes([i % 256 for i in range(1000)])  # Binary header
        content = header_content + magic + b"\x00" * 14000  # 15KB total

        with tempfile.NamedTemporaryFile(delete=False, suffix=".replay") as tmp:
            tmp.write(content)
            tmp.flush()
            yield Path(tmp.name)

        # Clean up
        Path(tmp.name).unlink(missing_ok=True)

    def test_adapter_properties(self, adapter):
        """Test adapter properties."""
        assert adapter.name == "null"
        assert adapter.supports_network_parsing is False

    def test_parse_header_success(self, adapter, test_replay_file):
        """Test successful header parsing."""
        header = adapter.parse_header(test_replay_file)

        assert isinstance(header, Header)
        assert "network_data_unparsed_fallback_header_only" in header.quality_warnings
        assert any(
            "using_null_adapter_file_size" in warning
            for warning in header.quality_warnings
        )
        assert header.playlist_id == "unknown"
        assert header.map_name == "unknown"
        assert header.team_size == 1
        assert len(header.players) == 2
        assert header.players[0].name == "Unknown Player 1"
        assert header.players[0].team == 0
        assert header.players[1].name == "Unknown Player 2"
        assert header.players[1].team == 1

    def test_parse_header_nonexistent_file(self, adapter):
        """Test header parsing with nonexistent file."""
        nonexistent_path = Path("/tmp/does_not_exist.replay")

        with pytest.raises(HeaderParseError) as exc_info:
            adapter.parse_header(nonexistent_path)

        assert str(nonexistent_path) in str(exc_info.value)
        assert "Null adapter failed to process file" in str(exc_info.value)

    def test_parse_header_with_ingest_warnings(self, adapter):
        """Test header parsing when ingest has warnings."""
        # Mock ingest_replay to return warnings
        mock_ingest_result = {
            "size_bytes": 15000,
            "warnings": ["mock_crc_warning", "mock_format_warning"],
        }

        with mock.patch("rlcoach.parser.null_adapter.ingest_replay") as mock_ingest:
            mock_ingest.return_value = mock_ingest_result

            header = adapter.parse_header(Path("/tmp/mock.replay"))

            # Should include both null adapter warnings and ingest warnings
            assert (
                "network_data_unparsed_fallback_header_only" in header.quality_warnings
            )
            assert "mock_crc_warning" in header.quality_warnings
            assert "mock_format_warning" in header.quality_warnings

    def test_parse_network_always_returns_none(self, adapter, test_replay_file):
        """Test that network parsing always returns None."""
        result = adapter.parse_network(test_replay_file)
        assert result is None

        # Should work with any path, even nonexistent ones
        result = adapter.parse_network(Path("/tmp/does_not_exist.replay"))
        assert result is None


class TestAdapterRegistry:
    """Tests for the adapter registry system."""

    def test_get_default_adapter(self):
        """Test getting the default (null) adapter."""
        adapter = get_adapter()
        assert isinstance(adapter, NullAdapter)
        assert adapter.name == "null"

    def test_get_null_adapter_explicitly(self):
        """Test getting null adapter explicitly."""
        adapter = get_adapter("null")
        assert isinstance(adapter, NullAdapter)
        assert adapter.name == "null"

    def test_get_nonexistent_adapter(self):
        """Test getting a nonexistent adapter."""
        with pytest.raises(AdapterNotFoundError) as exc_info:
            get_adapter("nonexistent")

        assert "nonexistent" in str(exc_info.value)
        assert "null" in str(exc_info.value)  # Should mention available adapters

    def test_list_adapters(self):
        """Test listing available adapters."""
        adapters = list_adapters()
        assert "null" in adapters
        assert len(adapters) >= 1

    def test_register_new_adapter(self):
        """Test registering a new adapter."""

        class TestAdapter(ParserAdapter):
            @property
            def name(self):
                return "test"

            @property
            def supports_network_parsing(self):
                return False

            def parse_header(self, path):
                return Header()

            def parse_network(self, path):
                return None

        # Register the adapter
        register_adapter("test", TestAdapter)

        try:
            # Should now be available
            assert "test" in list_adapters()
            adapter = get_adapter("test")
            assert isinstance(adapter, TestAdapter)
        finally:
            # Clean up (remove from registry)
            from rlcoach.parser import _ADAPTER_REGISTRY

            _ADAPTER_REGISTRY.pop("test", None)

    def test_register_duplicate_adapter(self):
        """Test registering an adapter with existing name."""

        class TestAdapter(ParserAdapter):
            @property
            def name(self):
                return "test"

            @property
            def supports_network_parsing(self):
                return False

            def parse_header(self, path):
                return Header()

            def parse_network(self, path):
                return None

        # Should fail to register over existing "null" adapter
        with pytest.raises(ValueError, match="already registered"):
            register_adapter("null", TestAdapter)

    def test_register_invalid_adapter_class(self):
        """Test registering a class that doesn't implement ParserAdapter."""

        class NotAnAdapter:
            pass

        with pytest.raises(TypeError, match="must inherit from ParserAdapter"):
            register_adapter("invalid", NotAnAdapter)


class TestIntegrationWithTestReplay:
    """Integration tests using the actual testing_replay.replay file."""

    def test_parse_real_replay_file(self):
        """Test parsing the actual testing replay file if it exists."""
        replay_path = Path("testing_replay.replay")

        if not replay_path.exists():
            pytest.skip("testing_replay.replay not found - skipping integration test")

        adapter = get_adapter("null")

        # Should be able to parse header
        header = adapter.parse_header(replay_path)
        assert isinstance(header, Header)
        assert "network_data_unparsed_fallback_header_only" in header.quality_warnings

        # Network parsing should return None
        frames = adapter.parse_network(replay_path)
        assert frames is None

    def test_adapter_selection_with_real_file(self):
        """Test adapter selection system with real file."""
        replay_path = Path("testing_replay.replay")

        if not replay_path.exists():
            pytest.skip("testing_replay.replay not found - skipping integration test")

        # Get list of available adapters
        available = list_adapters()
        assert "null" in available

        # Try each adapter
        for adapter_name in available:
            adapter = get_adapter(adapter_name)
            header = adapter.parse_header(replay_path)
            assert isinstance(header, Header)


if __name__ == "__main__":
    pytest.main([__file__])
