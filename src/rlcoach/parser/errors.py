"""Custom exceptions for parser layer."""

from ..errors import RLCoachError


class ParserError(RLCoachError):
    """Base exception for all parser-related errors."""

    def __init__(self, message: str, path: str = None, details: dict = None):
        base_details = {"path": path} if path else {}
        if details:
            base_details.update(details)
        super().__init__(message, base_details)


class HeaderParseError(ParserError):
    """Raised when header parsing fails."""

    def __init__(self, path: str, reason: str = None):
        base_message = f"Failed to parse header from replay: {path}"
        if reason:
            message = f"{base_message} ({reason})"
        else:
            message = base_message

        details = {
            "path": path,
            "reason": reason,
            "suggested_action": (
                "Check if the file is a valid .replay file or if it may be corrupted"
            ),
        }
        super().__init__(message, path, details)


class NetworkParseError(ParserError):
    """Raised when network frame parsing fails."""

    def __init__(self, path: str, reason: str = None):
        base_message = f"Failed to parse network frames from replay: {path}"
        if reason:
            message = f"{base_message} ({reason})"
        else:
            message = base_message

        details = {
            "path": path,
            "reason": reason,
            "suggested_action": (
                "This may be due to replay format changes. "
                "Header-only parsing may still be available."
            ),
        }
        super().__init__(message, path, details)


class AdapterNotFoundError(ParserError):
    """Raised when a requested parser adapter is not found."""

    def __init__(self, adapter_name: str, available_adapters: list = None):
        available = available_adapters or []
        if available:
            available_list = ", ".join(available)
            message = (
                f"Parser adapter not found: {adapter_name}. "
                f"Available: {available_list}"
            )
        else:
            message = f"Parser adapter not found: {adapter_name}"

        details = {
            "adapter_name": adapter_name,
            "available_adapters": available,
            "suggested_action": f"Use one of the available adapters: {available}",
        }
        super().__init__(message, details=details)
