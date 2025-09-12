"""rlcoach: All-local Rocket League replay analysis tool for coaching."""

from .schema import validate_report, validate_report_file
from .version import get_package_version

__version__ = get_package_version()
__author__ = "rlcoach contributors"
__description__ = "All-local Rocket League replay analysis tool for coaching"

__all__ = ["validate_report", "validate_report_file"]
