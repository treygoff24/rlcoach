# src/rlcoach/api/security.py
"""Security utilities for API input validation and sanitization."""

import re

# XSS-dangerous characters to escape or remove
XSS_PATTERN = re.compile(r'[<>"\'&]')

# Control characters (except newline, tab)
CONTROL_CHAR_PATTERN = re.compile(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]')

# Path traversal patterns
PATH_TRAVERSAL_PATTERN = re.compile(r'\.\.|[/\\]')


def sanitize_string(
    value: str,
    max_length: int = 255,
    allow_newlines: bool = False,
    strip_html: bool = True,
    preserve_formatting: bool = False,
) -> str:
    """Sanitize a user-provided string to prevent XSS and injection.

    Args:
        value: Raw user input
        max_length: Maximum allowed length
        allow_newlines: Whether to preserve newlines
        strip_html: Whether to escape HTML special characters
        preserve_formatting: Whether to preserve multiple spaces (for code/chat)

    Returns:
        Sanitized string safe for storage and display
    """
    if not value:
        return ""

    # Truncate to max length
    value = value[:max_length]

    # Remove control characters
    if allow_newlines:
        # Keep newlines and tabs
        value = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]', '', value)
    else:
        value = CONTROL_CHAR_PATTERN.sub('', value)
        value = value.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')

    # Escape or remove HTML special characters for XSS prevention
    if strip_html:
        value = value.replace('&', '&amp;')
        value = value.replace('<', '&lt;')
        value = value.replace('>', '&gt;')
        value = value.replace('"', '&quot;')
        value = value.replace("'", '&#x27;')

    # Collapse multiple spaces (skip for code/chat content to preserve formatting)
    if not preserve_formatting:
        value = re.sub(r' +', ' ', value)

    return value.strip()


def sanitize_filename(filename: str, max_length: int = 255) -> str:
    """Sanitize a filename to prevent path traversal and XSS.

    Args:
        filename: Raw filename from user
        max_length: Maximum allowed length

    Returns:
        Safe filename with only allowed characters
    """
    if not filename:
        return "unnamed.replay"

    # Remove path components (prevent traversal)
    filename = filename.replace('\\', '/').split('/')[-1]

    # Remove control characters and null bytes
    filename = CONTROL_CHAR_PATTERN.sub('', filename)

    # Replace dangerous characters with underscore
    # Allow: alphanumeric, dash, underscore, dot, space
    filename = re.sub(r'[^a-zA-Z0-9\-_. ]', '_', filename)

    # Collapse multiple underscores/spaces
    filename = re.sub(r'[_ ]+', '_', filename)

    # Remove leading/trailing dots and spaces (Windows safety)
    filename = filename.strip('. ')

    # Ensure it ends with .replay
    if not filename.lower().endswith('.replay'):
        # Remove any existing extension and add .replay
        if '.' in filename:
            filename = filename.rsplit('.', 1)[0]
        filename = f"{filename}.replay"

    # Truncate if needed (preserve extension)
    if len(filename) > max_length:
        name_part = filename[:-7]  # Remove .replay
        name_part = name_part[:max_length - 7]
        filename = f"{name_part}.replay"

    return filename or "unnamed.replay"


def sanitize_display_name(name: str, max_length: int = 100) -> str:
    """Sanitize a display name.

    Args:
        name: Raw display name
        max_length: Maximum allowed length

    Returns:
        Safe display name
    """
    return sanitize_string(name, max_length=max_length, allow_newlines=False)


def sanitize_note_content(content: str, max_length: int = 2000) -> str:
    """Sanitize note content (allows newlines).

    Args:
        content: Raw note content
        max_length: Maximum allowed length

    Returns:
        Safe note content
    """
    return sanitize_string(content, max_length=max_length, allow_newlines=True)
