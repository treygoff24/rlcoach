"""Command-line interface for rlcoach."""

import argparse
import sys

from . import __version__


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="rlcoach",
        description="All-local Rocket League replay analysis tool for coaching",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"rlcoach {__version__}",
    )

    parser.parse_args()

    # Currently just a stub - future functionality will be added here
    print("rlcoach CLI - ready for implementation")
    return 0


if __name__ == "__main__":
    sys.exit(main())
