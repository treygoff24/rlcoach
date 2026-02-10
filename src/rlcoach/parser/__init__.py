"""Parser module for Rocket League replay files.

This module provides a pluggable interface for parsing replay files with
support for different parsing backends. The default implementation uses
a null adapter that provides header-only fallback functionality.

Example usage:
    from rlcoach.parser import get_adapter

    # Get the default null adapter
    adapter = get_adapter()

    # Parse header information
    header = adapter.parse_header(Path("replay.replay"))

    # Attempt to parse network frames (may return None)
    frames = adapter.parse_network(Path("replay.replay"))
"""

from __future__ import annotations

from typing import Any

from .errors import (
    AdapterNotFoundError,
    HeaderParseError,
    NetworkParseError,
    ParserError,
)
from .interface import ParserAdapter
from .null_adapter import NullAdapter
from .rust_adapter import RustAdapter
from .types import Header, NetworkDiagnostics, NetworkFrames, PlayerInfo

# Registry of available parser adapters
_ADAPTER_REGISTRY: dict[str, type[ParserAdapter]] = {
    "null": NullAdapter,
    "rust": RustAdapter,
}

# Default adapter name
_DEFAULT_ADAPTER = "null"


def get_adapter(name: str = _DEFAULT_ADAPTER, **adapter_kwargs: Any) -> ParserAdapter:
    """Get a parser adapter by name.

    Args:
        name: Name of the adapter to retrieve. Defaults to "null".
        **adapter_kwargs: Optional adapter-specific constructor arguments.

    Returns:
        Instance of the requested parser adapter

    Raises:
        AdapterNotFoundError: If the requested adapter is not found

    Example:
        adapter = get_adapter("null")
        header = adapter.parse_header(Path("replay.replay"))
    """
    if name not in _ADAPTER_REGISTRY:
        available = list(_ADAPTER_REGISTRY.keys())
        raise AdapterNotFoundError(name, available)

    adapter_class = _ADAPTER_REGISTRY[name]
    return adapter_class(**adapter_kwargs)


def list_adapters() -> list[str]:
    """List all available parser adapter names.

    Returns:
        List of available adapter names

    Example:
        adapters = list_adapters()
        print(f"Available adapters: {adapters}")
    """
    return list(_ADAPTER_REGISTRY.keys())


def register_adapter(name: str, adapter_class: type[ParserAdapter]) -> None:
    """Register a new parser adapter.

    This function allows third-party adapters to be registered with the
    parser system. The adapter class must implement the ParserAdapter interface.

    Args:
        name: Name to register the adapter under
        adapter_class: Class that implements ParserAdapter interface

    Raises:
        TypeError: If adapter_class doesn't implement ParserAdapter
        ValueError: If name is already registered

    Example:
        register_adapter("custom", MyCustomAdapter)
        adapter = get_adapter("custom")
    """
    if name in _ADAPTER_REGISTRY:
        raise ValueError(f"Adapter '{name}' is already registered")

    if not issubclass(adapter_class, ParserAdapter):
        raise TypeError(
            f"Adapter class must inherit from ParserAdapter, got {adapter_class}"
        )

    _ADAPTER_REGISTRY[name] = adapter_class


# Export public API
__all__ = [
    # Core types
    "Header",
    "NetworkDiagnostics",
    "NetworkFrames",
    "PlayerInfo",
    # Interface
    "ParserAdapter",
    # Functions
    "get_adapter",
    "list_adapters",
    "register_adapter",
    # Exceptions
    "ParserError",
    "HeaderParseError",
    "NetworkParseError",
    "AdapterNotFoundError",
]
