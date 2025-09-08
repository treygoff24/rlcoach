"""File ingestion and validation for Rocket League replay files."""

import hashlib
from pathlib import Path

from .errors import (
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


def crc_check_header(data: bytes) -> tuple[bool, str]:
    """Stub CRC validation for replay header.

    This is a placeholder implementation. Full CRC validation will be
    implemented when the parser is added in a later ticket.

    Args:
        data: Raw file bytes

    Returns:
        Tuple of (check_passed, message)
    """
    # For now, just return success with a note that this is not implemented
    # Real implementation would parse header structure and validate CRC

    if len(data) < 100:
        return False, "File too short for CRC validation"

    # Placeholder: assume CRC is valid for properly formatted files
    format_ok, format_msg = basic_format_check(data)
    if format_ok:
        return (
            True,
            "CRC check not yet implemented (assumed valid for well-formed replay)",
        )
    else:
        return False, f"Cannot validate CRC: {format_msg}"


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

    # Check CRC (stub implementation)
    crc_ok, crc_msg = crc_check_header(data)

    # Collect warnings for non-fatal issues
    warnings = []
    if not crc_ok:
        warnings.append(f"CRC validation issue: {crc_msg}")

    return {
        "file_path": path_str,
        "sha256": file_hash,
        "size_bytes": file_size,
        "size_human": format_file_size(file_size),
        "bounds_check": {"passed": bounds_ok, "message": bounds_msg},
        "format_check": {"passed": format_ok, "message": format_msg},
        "crc_check": {"passed": crc_ok, "message": crc_msg},
        "warnings": warnings,
        "status": "success" if format_ok and bounds_ok else "degraded",
    }
