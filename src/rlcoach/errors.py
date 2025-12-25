"""Custom exceptions for rlcoach with structured error information."""


class RLCoachError(Exception):
    """Base exception for all rlcoach errors.

    Provides structured error information with actionable messages.
    """

    def __init__(self, message: str, details: dict = None):
        super().__init__(message)
        self.details = details or {}


class ReplayFileNotFoundError(RLCoachError):
    """Raised when a replay file cannot be found."""

    def __init__(self, path: str):
        message = f"Replay file not found: {path}"
        details = {
            "path": path,
            "suggested_action": "Verify the file path exists and is accessible",
        }
        super().__init__(message, details)


class FileTooLargeError(RLCoachError):
    """Raised when a file exceeds size bounds."""

    def __init__(self, size_bytes: int, max_size_bytes: int, path: str = None):
        size_mb = size_bytes / (1024 * 1024)
        max_size_mb = max_size_bytes / (1024 * 1024)

        if size_bytes < 1000:  # Too small case
            message = f"File too small: {size_bytes} bytes is below minimum replay size"
            suggested_action = "Check if the file is corrupted or incomplete"
        else:  # Too large case
            message = (
                f"File too large: {size_mb:.1f} MB exceeds maximum "
                f"of {max_size_mb:.1f} MB"
            )
            suggested_action = (
                "Consider checking if file is corrupted or use a different replay"
            )

        details = {
            "size_bytes": size_bytes,
            "max_size_bytes": max_size_bytes,
            "path": path,
            "suggested_action": suggested_action,
        }
        super().__init__(message, details)


class FileTooSmallError(RLCoachError):
    """Raised when a file is below minimum size bounds."""

    def __init__(self, size_bytes: int, min_size_bytes: int, path: str = None):
        message = (
            f"File too small: {size_bytes} bytes is below minimum "
            f"of {min_size_bytes} bytes"
        )
        details = {
            "size_bytes": size_bytes,
            "min_size_bytes": min_size_bytes,
            "path": path,
            "suggested_action": "Check if the file is corrupted or incomplete",
        }
        super().__init__(message, details)


class InvalidReplayFormatError(RLCoachError):
    """Raised when a file doesn't appear to be a valid Rocket League replay."""

    def __init__(self, path: str, reason: str = None):
        base_message = f"Invalid replay format: {path}"
        if reason:
            message = f"{base_message} ({reason})"
        else:
            message = base_message

        details = {
            "path": path,
            "reason": reason,
            "suggested_action": (
                "Ensure the file is a valid .replay file from Rocket League"
            ),
        }
        super().__init__(message, details)


class CRCValidationError(RLCoachError):
    """Raised when CRC validation fails for a replay file."""

    def __init__(
        self,
        path: str,
        expected_crc: int | None = None,
        actual_crc: int | None = None,
        section: str = "header",
    ):
        message = f"CRC validation failed for {section} section: {path}"
        details = {
            "path": path,
            "section": section,
            "expected_crc": (
                f"0x{expected_crc:08x}" if expected_crc is not None else None
            ),
            "actual_crc": f"0x{actual_crc:08x}" if actual_crc is not None else None,
            "suggested_action": (
                "The replay file may be corrupted. Try re-downloading or "
                "use a different file"
            ),
        }
        super().__init__(message, details)


class ReplayIOError(RLCoachError):
    """Raised when there's an I/O error reading a replay file."""

    def __init__(self, path: str, original_error: Exception):
        message = f"I/O error reading replay: {path} ({str(original_error)})"
        details = {
            "path": path,
            "original_error": str(original_error),
            "error_type": type(original_error).__name__,
            "suggested_action": "Check file permissions and disk space",
        }
        super().__init__(message, details)
