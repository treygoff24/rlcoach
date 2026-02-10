"""rlcoach: All-local Rocket League replay analysis tool for coaching."""

import importlib

from .schema import validate_report, validate_report_file
from .version import get_package_version

__version__ = get_package_version()
__author__ = "rlcoach contributors"
__description__ = "All-local Rocket League replay analysis tool for coaching"

__all__ = ["validate_report", "validate_report_file"]


def __getattr__(name: str):
    """Lazily expose optional top-level subpackages."""
    if name == "api":
        return importlib.import_module("rlcoach.api")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
