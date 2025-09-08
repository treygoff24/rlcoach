"""Command-line interface for rlcoach."""

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .errors import RLCoachError
from .ingest import ingest_replay


def handle_ingest_command(args) -> int:
    """Handle the ingest subcommand.

    Args:
        args: Parsed command line arguments

    Returns:
        Exit code (0 for success, 1 for error)
    """
    replay_path = Path(args.replay_file)

    try:
        result = ingest_replay(replay_path)

        if args.json:
            # Output machine-readable JSON
            print(json.dumps(result, indent=2))
        else:
            # Output human-readable format
            print(f"Ingestion Results for: {result['file_path']}")
            print(f"SHA256: {result['sha256']}")
            print(f"Size: {result['size_human']} ({result['size_bytes']:,} bytes)")
            print(f"Bounds Check: {result['bounds_check']['message']}")
            print(f"Format Check: {result['format_check']['message']}")
            print(f"CRC Check: {result['crc_check']['message']}")

            if result["warnings"]:
                print("\nWarnings:")
                for warning in result["warnings"]:
                    print(f"  - {warning}")

            print(f"\nStatus: {result['status'].upper()}")

        return 0

    except RLCoachError as e:
        if args.json:
            error_result = {
                "error": {
                    "type": type(e).__name__,
                    "message": str(e),
                    "details": getattr(e, "details", {}),
                },
                "status": "error",
            }
            print(json.dumps(error_result, indent=2))
        else:
            print(f"Error: {e}", file=sys.stderr)
            if hasattr(e, "details") and "suggested_action" in e.details:
                print(f"Suggestion: {e.details['suggested_action']}", file=sys.stderr)

        return 1

    except Exception as e:
        if args.json:
            error_result = {
                "error": {
                    "type": "UnexpectedError",
                    "message": f"Unexpected error: {str(e)}",
                    "details": {},
                },
                "status": "error",
            }
            print(json.dumps(error_result, indent=2))
        else:
            print(f"Unexpected error: {e}", file=sys.stderr)

        return 1


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

    # Create subparsers for different commands
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Ingest subcommand
    ingest_parser = subparsers.add_parser(
        "ingest", help="Ingest and validate a Rocket League replay file"
    )
    ingest_parser.add_argument(
        "replay_file", type=str, help="Path to the .replay file to ingest"
    )
    ingest_parser.add_argument(
        "--json",
        action="store_true",
        help="Output results in machine-readable JSON format",
    )

    args = parser.parse_args()

    # Route to appropriate handler
    if args.command == "ingest":
        return handle_ingest_command(args)
    else:
        # No subcommand provided, show help
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
