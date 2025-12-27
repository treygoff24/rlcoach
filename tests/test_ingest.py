"""Tests for the replay ingestion and validation module."""

import hashlib
import struct
import tempfile
from pathlib import Path

import pytest

from rlcoach.errors import (
    CRCValidationError,
    FileTooLargeError,
    FileTooSmallError,
    InvalidReplayFormatError,
    ReplayFileNotFoundError,
)
from rlcoach.ingest import (
    MAX_REPLAY_SIZE,
    MIN_REPLAY_SIZE,
    REPLAY_MAGIC_SEQUENCES,
    _calc_replay_crc,
    basic_format_check,
    bounds_check,
    crc_check_header,
    file_sha256,
    format_file_size,
    ingest_replay,
    read_replay_bytes,
)


def _encode_text(value: str) -> bytes:
    data = value.encode("windows-1252")
    return struct.pack("<i", len(data) + 1) + data + b"\x00"


def _encode_str(value: str) -> bytes:
    data = value.encode("utf-8")
    return struct.pack("<i", len(data) + 1) + data + b"\x00"


def build_minimal_replay(
    *,
    major: int = 868,
    minor: int = 23,
    net_version: int | None = None,
    include_magic: bool = True,
    content_payload: bytes = b"",
    pad_to_min_size: bool = True,
) -> bytes:
    """Construct a minimal, CRC-valid Rocket League replay payload for tests."""

    header_parts = [
        struct.pack("<i", major),
        struct.pack("<i", minor),
    ]

    if net_version is not None:
        header_parts.append(struct.pack("<i", net_version))

    game_type = "TAGame.Replay_Soccar_TA" if include_magic else "UNKNOWN.REPLAY"
    header_parts.append(_encode_text(game_type))
    # Terminate property list immediately
    header_parts.append(_encode_str("None"))

    header_bytes = b"".join(header_parts)
    header_crc = _calc_replay_crc(header_bytes)

    content_crc = _calc_replay_crc(content_payload)

    replay_bytes = (
        struct.pack("<iI", len(header_bytes), header_crc)
        + header_bytes
        + struct.pack("<iI", len(content_payload), content_crc)
        + content_payload
    )
    if pad_to_min_size and len(replay_bytes) < MIN_REPLAY_SIZE:
        replay_bytes += b"\x00" * (MIN_REPLAY_SIZE - len(replay_bytes))
    return replay_bytes


class TestFileSize:
    """Tests for file size utilities."""

    def test_format_file_size_bytes(self):
        """Test formatting of file sizes in bytes."""
        assert format_file_size(500) == "500 bytes"
        assert format_file_size(1023) == "1023 bytes"

    def test_format_file_size_kb(self):
        """Test formatting of file sizes in KB."""
        assert format_file_size(1024) == "1.0 KB"
        assert format_file_size(1536) == "1.5 KB"
        assert format_file_size(1048575) == "1024.0 KB"

    def test_format_file_size_mb(self):
        """Test formatting of file sizes in MB."""
        assert format_file_size(1048576) == "1.0 MB"
        assert format_file_size(2097152) == "2.0 MB"
        assert format_file_size(1572864) == "1.5 MB"


class TestBoundsCheck:
    """Tests for file size bounds checking."""

    def test_bounds_check_valid_size(self):
        """Test bounds check with valid file size."""
        size = 1000000  # 1MB
        valid, message = bounds_check(size)
        assert valid is True
        assert "1.0 MB" in message
        assert "OK" in message

    def test_bounds_check_too_small(self):
        """Test bounds check with too small file."""
        size = MIN_REPLAY_SIZE - 1
        valid, message = bounds_check(size)
        assert valid is False
        assert "too small" in message.lower()

    def test_bounds_check_too_large(self):
        """Test bounds check with too large file."""
        size = MAX_REPLAY_SIZE + 1
        valid, message = bounds_check(size)
        assert valid is False
        assert "too large" in message.lower()

    def test_bounds_check_min_boundary(self):
        """Test bounds check at minimum boundary."""
        size = MIN_REPLAY_SIZE
        valid, message = bounds_check(size)
        assert valid is True

    def test_bounds_check_max_boundary(self):
        """Test bounds check at maximum boundary."""
        size = MAX_REPLAY_SIZE
        valid, message = bounds_check(size)
        assert valid is True


class TestBasicFormatCheck:
    """Tests for basic replay format validation."""

    def test_format_check_too_short(self):
        """Test format check with too short data."""
        data = b"short"
        valid, message = basic_format_check(data)
        assert valid is False
        assert "too short" in message.lower()

    def test_format_check_valid_replay_magic(self):
        """Test format check with valid replay magic sequence."""
        # Create data with valid magic sequence
        magic = REPLAY_MAGIC_SEQUENCES[0]
        data = b"\x00" * 100 + magic + b"\x00" * 1000

        valid, message = basic_format_check(data)
        assert valid is True
        assert "Valid replay format detected" in message

    def test_format_check_text_file(self):
        """Test format check rejects text files."""
        data = b"This is clearly a text file, not a replay\n" + b"\x00" * 1000
        valid, message = basic_format_check(data)
        assert valid is False
        assert "text" in message.lower()

    def test_format_check_binary_but_no_magic(self):
        """Test format check with binary data but no magic sequence."""
        # Create binary data without replay magic (avoid ASCII range that looks like text)
        data = bytes([i + 128 for i in range(128)] * 20)  # Non-ASCII binary data
        valid, message = basic_format_check(data)
        assert valid is False
        assert "no known replay format markers" in message.lower()

    def test_format_check_all_magic_sequences(self):
        """Test format check works with all known magic sequences."""
        for magic in REPLAY_MAGIC_SEQUENCES:
            data = b"\x00" * 50 + magic + b"\x00" * 1000
            valid, message = basic_format_check(data)
            assert valid is True, f"Magic sequence {magic} should be detected"


class TestCRCCheck:
    """Tests for CRC validation (stub implementation)."""

    def test_crc_check_too_short(self):
        """Test CRC check with too short data."""
        data = b"short"
        valid, message, _ = crc_check_header(data)
        assert valid is False
        assert "truncated" in message.lower()

    def test_crc_check_valid_format(self):
        """Test CRC check with valid replay format."""
        data = build_minimal_replay()

        valid, message, details = crc_check_header(data)
        assert valid is True
        assert "passed" in message.lower()
        versions = details["versions"]
        assert versions["major"] == 868
        assert versions["minor"] == 23
        assert details["header"]["passed"] is True
        assert details["content"]["passed"] is True

    def test_crc_check_invalid_format(self):
        """Test CRC check with invalid format."""
        data = b"This is text data" + b"\x00" * 200
        valid, message, _ = crc_check_header(data)
        assert valid is False
        assert "trunc" in message.lower()

    def test_crc_check_content_mismatch(self):
        """CRC check should fail when content payload is tampered."""
        data = bytearray(build_minimal_replay(content_payload=b"abc", pad_to_min_size=False))
        header_size = struct.unpack_from("<i", data, 0)[0]
        header_total = 8 + header_size
        content_size = struct.unpack_from("<i", data, header_total)[0]
        assert content_size > 0
        content_start = header_total + 8
        data[content_start] ^= 0xFF  # Flip byte within content to force mismatch

        valid, message, details = crc_check_header(bytes(data))
        assert not valid
        assert "content crc mismatch" in message.lower()
        assert details["content"]["passed"] is False


class TestFileSHA256:
    """Tests for file hashing."""

    def test_file_sha256_existing_file(self):
        """Test SHA256 calculation for existing file."""
        content = b"test data for hashing"
        expected_hash = hashlib.sha256(content).hexdigest()

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(content)
            tmp.flush()

            tmp_path = Path(tmp.name)
            try:
                result = file_sha256(tmp_path)
                assert result == expected_hash
            finally:
                tmp_path.unlink()

    def test_file_sha256_nonexistent_file(self):
        """Test SHA256 calculation for nonexistent file."""
        nonexistent_path = Path("/tmp/definitely_does_not_exist.replay")

        with pytest.raises(ReplayFileNotFoundError) as exc_info:
            file_sha256(nonexistent_path)

        assert str(nonexistent_path) in str(exc_info.value)


class TestReadReplayBytes:
    """Tests for safe replay file reading."""

    def test_read_replay_bytes_success(self):
        """Test successful replay file reading."""
        # Create a valid-sized replay file with magic sequence
        magic = REPLAY_MAGIC_SEQUENCES[0]
        content = b"\x00" * 5000 + magic + b"\x00" * 10000  # 15KB total

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(content)
            tmp.flush()

            tmp_path = Path(tmp.name)
            try:
                result = read_replay_bytes(tmp_path)
                assert result == content
            finally:
                tmp_path.unlink()

    def test_read_replay_bytes_nonexistent(self):
        """Test reading nonexistent file."""
        nonexistent_path = Path("/tmp/does_not_exist.replay")

        with pytest.raises(ReplayFileNotFoundError) as exc_info:
            read_replay_bytes(nonexistent_path)

        assert str(nonexistent_path) in str(exc_info.value)

    def test_read_replay_bytes_too_small(self):
        """Test reading file that's too small."""
        content = b"tiny"  # Much smaller than MIN_REPLAY_SIZE

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(content)
            tmp.flush()

            tmp_path = Path(tmp.name)
            try:
                with pytest.raises(FileTooSmallError) as exc_info:
                    read_replay_bytes(tmp_path)

                assert exc_info.value.details["size_bytes"] == len(content)
                assert exc_info.value.details["min_size_bytes"] == MIN_REPLAY_SIZE
            finally:
                tmp_path.unlink()

    def test_read_replay_bytes_too_large(self):
        """Test reading file that's too large."""
        # Create a file larger than MAX_REPLAY_SIZE
        large_size = MAX_REPLAY_SIZE + 1000

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            # Write in chunks to avoid memory issues
            chunk_size = 1024 * 1024  # 1MB chunks
            written = 0
            while written < large_size:
                to_write = min(chunk_size, large_size - written)
                tmp.write(b"\x00" * to_write)
                written += to_write
            tmp.flush()

            tmp_path = Path(tmp.name)
            try:
                with pytest.raises(FileTooLargeError) as exc_info:
                    read_replay_bytes(tmp_path)

                assert exc_info.value.details["size_bytes"] == large_size
                assert exc_info.value.details["max_size_bytes"] == MAX_REPLAY_SIZE
            finally:
                tmp_path.unlink()

    def test_read_replay_bytes_directory(self):
        """Test reading a directory instead of file."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            dir_path = Path(tmp_dir)

            with pytest.raises(InvalidReplayFormatError) as exc_info:
                read_replay_bytes(dir_path)

            assert "not a regular file" in str(exc_info.value)


class TestIngestReplay:
    """Tests for the main ingest_replay function."""

    def create_test_replay(
        self,
        *,
        include_magic: bool = True,
        content_payload: bytes = b"",
        major: int = 868,
        minor: int = 23,
    ) -> bytes:
        return build_minimal_replay(
            major=major,
            minor=minor,
            include_magic=include_magic,
            content_payload=content_payload,
        )

    def test_ingest_replay_success(self):
        """Test successful replay ingestion."""
        content = self.create_test_replay()
        expected_hash = hashlib.sha256(content).hexdigest()

        with tempfile.NamedTemporaryFile(delete=False, suffix=".replay") as tmp:
            tmp.write(content)
            tmp.flush()

            tmp_path = Path(tmp.name)
            try:
                result = ingest_replay(tmp_path)

                # Check all expected fields are present
                assert result["file_path"] == str(tmp_path)
                assert result["sha256"] == expected_hash
                assert result["size_bytes"] == len(content)
                assert result["size_human"] is not None
                assert result["status"] == "success"

                # Check bounds check
                assert result["bounds_check"]["passed"] is True

                # Check format check
                assert result["format_check"]["passed"] is True

                # Check CRC check
                assert result["crc_check"]["passed"] is True
                assert result["crc_check"]["details"]["header"]["passed"] is True
                assert result["crc_check"]["details"]["content"]["passed"] is True
                assert result["header_versions"]["major"] == 868
                assert result["header_versions"]["minor"] == 23

                # Should have no warnings for valid file
                assert result["warnings"] == []

            finally:
                tmp_path.unlink()

    def test_ingest_replay_crc_failure(self):
        """Replay ingestion should raise when CRC validation fails."""
        content = bytearray(self.create_test_replay(content_payload=b"payload"))
        # Corrupt the stored header CRC (but not the header payload) to trigger mismatch
        content[4] ^= 0xFF

        with tempfile.NamedTemporaryFile(delete=False, suffix=".replay") as tmp:
            tmp.write(content)
            tmp.flush()

            tmp_path = Path(tmp.name)
            try:
                with pytest.raises(CRCValidationError) as exc_info:
                    ingest_replay(tmp_path)

                assert exc_info.value.details["section"] == "header"
            finally:
                tmp_path.unlink()

    def test_ingest_replay_file_not_found(self):
        """Test ingesting nonexistent file."""
        nonexistent_path = Path("/tmp/does_not_exist.replay")

        with pytest.raises(ReplayFileNotFoundError):
            ingest_replay(nonexistent_path)

    def test_ingest_replay_invalid_format(self):
        """Test ingesting invalid format file."""
        # Create file with no magic sequence
        content = self.create_test_replay(include_magic=False)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".replay") as tmp:
            tmp.write(content)
            tmp.flush()

            tmp_path = Path(tmp.name)
            try:
                with pytest.raises(InvalidReplayFormatError):
                    ingest_replay(tmp_path)
            finally:
                tmp_path.unlink()

    def test_ingest_replay_too_small(self):
        """Test ingesting file that's too small."""
        content = b"tiny file"

        with tempfile.NamedTemporaryFile(delete=False, suffix=".replay") as tmp:
            tmp.write(content)
            tmp.flush()

            tmp_path = Path(tmp.name)
            try:
                with pytest.raises(FileTooSmallError):
                    ingest_replay(tmp_path)
            finally:
                tmp_path.unlink()


class TestConstants:
    """Tests for module constants."""

    def test_replay_magic_sequences_not_empty(self):
        """Test that we have magic sequences defined."""
        assert len(REPLAY_MAGIC_SEQUENCES) > 0

    def test_replay_magic_sequences_are_bytes(self):
        """Test that magic sequences are bytes objects."""
        for magic in REPLAY_MAGIC_SEQUENCES:
            assert isinstance(magic, bytes)

    def test_size_bounds_reasonable(self):
        """Test that size bounds are reasonable."""
        assert MIN_REPLAY_SIZE > 0
        assert MAX_REPLAY_SIZE > MIN_REPLAY_SIZE
        assert MIN_REPLAY_SIZE >= 1000  # At least 1KB
        assert MAX_REPLAY_SIZE <= 100_000_000  # At most 100MB


if __name__ == "__main__":
    pytest.main([__file__])
