"""File ingestion and validation for Rocket League replay files."""

from __future__ import annotations

import hashlib
import struct
from pathlib import Path
from typing import Any, Dict, Tuple

from .errors import (
    CRCValidationError,
    FileTooLargeError,
    FileTooSmallError,
    InvalidReplayFormatError,
    ReplayFileNotFoundError,
    ReplayIOError,
)

# File size bounds (configurable constants)
MIN_REPLAY_SIZE = 10_000  # 10KB minimum - smaller files likely corrupted
MAX_REPLAY_SIZE = 50_000_000  # 50MB maximum - handles large overtime replays

# Known Rocket League replay format markers
# These are common byte sequences found in valid replay headers
REPLAY_MAGIC_SEQUENCES = [
    b"TAGame.Replay_Soccar_TA",  # Standard soccar replay
    b"TAGame.Replay_",  # General replay marker
    b"\x00\x00\x00\x00\x08\x00\x00\x00TAGame",  # Header format variant
]

# CRC configuration derived from Rocket League's replay format / Unreal Engine implementation
_CRC_POLY = 0x04C11DB7
_CRC_XOR_IN = 0x10340DFE
_CRC_XOR_OUT = 0xFFFFFFFF


def _calc_replay_crc(data: bytes) -> int:
    """Compute the Rocket League replay CRC for the provided data."""

    crc = _CRC_XOR_IN
    for byte in data:
        crc ^= byte << 24
        for _ in range(8):
            if crc & 0x8000_0000:
                crc = ((crc << 1) ^ _CRC_POLY) & 0xFFFFFFFF
            else:
                crc = (crc << 1) & 0xFFFFFFFF
    return crc ^ _CRC_XOR_OUT


def _read_i32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<i", data, offset)[0]


def _read_u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def read_replay_bytes(path: Path) -> bytes:
    """Safely read replay file with validation.

    Args:
        path: Path to the replay file

    Returns:
        Raw bytes of the replay file

    Raises:
        ReplayFileNotFoundError: If file doesn't exist
        ReplayIOError: If there's an I/O error reading the file
        FileTooSmallError: If file is smaller than minimum size
        FileTooLargeError: If file exceeds maximum size
    """
    path_str = str(path)

    # Check if file exists
    if not path.exists():
        raise ReplayFileNotFoundError(path_str)

    # Check if it's actually a file (not a directory)
    if not path.is_file():
        raise InvalidReplayFormatError(path_str, "Path is not a regular file")

    # Check file size bounds before reading
    try:
        file_size = path.stat().st_size
    except OSError as e:
        raise ReplayIOError(path_str, e) from e

    if file_size < MIN_REPLAY_SIZE:
        raise FileTooSmallError(file_size, MIN_REPLAY_SIZE, path_str)

    if file_size > MAX_REPLAY_SIZE:
        raise FileTooLargeError(file_size, MAX_REPLAY_SIZE, path_str)

    # Read file contents
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError as e:
        raise ReplayIOError(path_str, e) from e

    return data


def file_sha256(path: Path) -> str:
    """Compute SHA256 hash of a file.

    Args:
        path: Path to the file

    Returns:
        SHA256 hash as hexadecimal string

    Raises:
        ReplayFileNotFoundError: If file doesn't exist
        ReplayIOError: If there's an I/O error reading the file
    """
    path_str = str(path)

    if not path.exists():
        raise ReplayFileNotFoundError(path_str)

    try:
        hash_sha256 = hashlib.sha256()
        with open(path, "rb") as f:
            # Read file in chunks to handle large files efficiently
            for chunk in iter(lambda: f.read(4096), b""):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()
    except OSError as e:
        raise ReplayIOError(path_str, e) from e


def bounds_check(size_bytes: int) -> tuple[bool, str]:
    """Check if file size is within reasonable bounds.

    Args:
        size_bytes: Size of the file in bytes

    Returns:
        Tuple of (is_valid, message)
    """
    if size_bytes < MIN_REPLAY_SIZE:
        size_kb = size_bytes / 1024
        min_kb = MIN_REPLAY_SIZE / 1024
        return False, f"File too small: {size_kb:.1f} KB < {min_kb:.1f} KB minimum"

    if size_bytes > MAX_REPLAY_SIZE:
        size_mb = size_bytes / (1024 * 1024)
        max_mb = MAX_REPLAY_SIZE / (1024 * 1024)
        return False, f"File too large: {size_mb:.1f} MB > {max_mb:.1f} MB maximum"

    size_mb = size_bytes / (1024 * 1024)
    return True, f"File size OK: {size_mb:.1f} MB"


def format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable format.

    Args:
        size_bytes: Size in bytes

    Returns:
        Human-readable size string
    """
    if size_bytes < 1024:
        return f"{size_bytes} bytes"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def basic_format_check(data: bytes) -> tuple[bool, str]:
    """Check if data looks like a Rocket League replay file.

    This is a basic format validation that looks for known magic sequences.
    More comprehensive parsing will be implemented in later tickets.

    Args:
        data: Raw file bytes

    Returns:
        Tuple of (is_valid, message)
    """
    if len(data) < 100:
        return False, "File too short to be a valid replay"

    # Check for known replay magic sequences in the first 2KB
    header_chunk = data[:2048]

    for magic_sequence in REPLAY_MAGIC_SEQUENCES:
        if magic_sequence in header_chunk:
            return (
                True,
                f"Valid replay format detected "
                f"(found '{magic_sequence.decode('ascii', errors='replace')}')",
            )

    # Check if it looks like binary data (not text)
    try:
        data[:100].decode("utf-8")
        return False, "File appears to be text, not a binary replay file"
    except UnicodeDecodeError:
        # Binary data is expected for replay files
        pass

    return False, "No known replay format markers found"


def crc_check_header(data: bytes) -> Tuple[bool, str, Dict[str, Any]]:
    """Perform Rocket League replay CRC validation for header and content sections."""

    details: Dict[str, Any] = {}

    min_size = 4 + 4 + 4 + 4  # header_size + header_crc + content_size + content_crc
    if len(data) < min_size:
        return False, "Replay file truncated before CRC sections", details

    offset = 0
    try:
        header_size = _read_i32(data, offset)
    except struct.error:
        return False, "Unable to read header size for CRC validation", details

    if header_size <= 0:
        return False, f"Invalid header size {header_size} bytes", details

    offset += 4
    try:
        header_crc_expected = _read_u32(data, offset)
    except struct.error:
        return False, "Unable to read stored header CRC", details

    offset += 4
    header_end = offset + header_size
    if header_end > len(data):
        return False, "Replay file truncated within header section", details

    header_section = data[offset:header_end]
    header_crc_actual = _calc_replay_crc(header_section)

    versions: Dict[str, Any] = {}
    if len(header_section) >= 8:
        major = _read_i32(header_section, 0)
        minor = _read_i32(header_section, 4)
        versions = {"major": major, "minor": minor}
        if major > 865 and minor > 17 and len(header_section) >= 12:
            versions["net"] = _read_i32(header_section, 8)
        else:
            versions["net"] = None

    offset = header_end
    if len(data) < offset + 8:
        return False, "Replay file truncated before content CRC section", details

    content_size = _read_i32(data, offset)
    offset += 4
    if content_size < 0:
        return False, f"Invalid content size {content_size} bytes", details

    content_crc_expected = _read_u32(data, offset)
    offset += 4
    content_end = offset + content_size
    if content_end > len(data):
        return False, "Replay file truncated within content section", details

    content_section = data[offset:content_end]
    content_crc_actual = _calc_replay_crc(content_section)

    header_passed = header_crc_actual == header_crc_expected
    content_passed = content_crc_actual == content_crc_expected

    details["header"] = {
        "size": header_size,
        "expected": header_crc_expected,
        "actual": header_crc_actual,
        "passed": header_passed,
    }
    details["content"] = {
        "size": content_size,
        "expected": content_crc_expected,
        "actual": content_crc_actual,
        "passed": content_passed,
    }
    details["versions"] = versions

    if header_passed and content_passed:
        message = "Header and content CRC validation passed"
        return True, message, details

    if not header_passed:
        message = (
            "Header CRC mismatch: expected 0x"
            f"{header_crc_expected:08x}, got 0x{header_crc_actual:08x}"
        )
    else:
        message = (
            "Content CRC mismatch: expected 0x"
            f"{content_crc_expected:08x}, got 0x{content_crc_actual:08x}"
        )

    return False, message, details


def ingest_replay(path: Path) -> dict:
    """Main ingestion pipeline for a replay file.

    Args:
        path: Path to the replay file

    Returns:
        Dictionary containing ingestion results and metadata

    Raises:
        Various replay-specific exceptions for different error conditions
    """
    path_str = str(path)

    # Read file and get basic info
    data = read_replay_bytes(path)
    file_size = len(data)
    file_hash = file_sha256(path)

    # Validate bounds
    bounds_ok, bounds_msg = bounds_check(file_size)
    if not bounds_ok:
        if file_size < MIN_REPLAY_SIZE:
            raise FileTooSmallError(file_size, MIN_REPLAY_SIZE, path_str)
        else:
            raise FileTooLargeError(file_size, MAX_REPLAY_SIZE, path_str)

    # Check basic format
    format_ok, format_msg = basic_format_check(data)
    if not format_ok:
        raise InvalidReplayFormatError(path_str, format_msg)

    crc_ok, crc_msg, crc_details = crc_check_header(data)

    if not crc_ok:
        failing_section = "header"
        section_info = crc_details.get("header", {})
        if section_info.get("passed", True):
            failing_section = "content"
            section_info = crc_details.get("content", {})

        raise CRCValidationError(
            path_str,
            expected_crc=section_info.get("expected"),
            actual_crc=section_info.get("actual"),
            section=failing_section,
        )

    # Collect warnings for non-fatal issues (e.g., unusual versions)
    warnings = []
    header_versions = crc_details.get("versions", {})
    if header_versions:
        major = header_versions.get("major")
        minor = header_versions.get("minor")
        if major is not None and minor is not None and (major <= 0 or minor <= 0):
            warnings.append(
                f"Unexpected replay version detected (major={major}, minor={minor})"
            )

    return {
        "file_path": path_str,
        "sha256": file_hash,
        "size_bytes": file_size,
        "size_human": format_file_size(file_size),
        "bounds_check": {"passed": bounds_ok, "message": bounds_msg},
        "format_check": {"passed": format_ok, "message": format_msg},
        "crc_check": {
            "passed": crc_ok,
            "message": crc_msg,
            "details": crc_details,
        },
        "header_versions": header_versions,
        "warnings": warnings,
        "status": "success" if format_ok and bounds_ok else "degraded",
    }
