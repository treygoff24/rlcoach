"""rlcoach: All-local Rocket League replay analysis tool for coaching."""

from .schema import validate_report, validate_report_file

__version__ = "0.1.0"
__author__ = "rlcoach contributors"
__description__ = "All-local Rocket League replay analysis tool for coaching"

__all__ = ["validate_report", "validate_report_file"]
