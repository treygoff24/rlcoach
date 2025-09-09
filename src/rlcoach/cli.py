"""Command-line interface for rlcoach."""

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .errors import RLCoachError
from .ingest import ingest_replay
from .report import generate_report, write_report_atomically


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

    # Analyze subcommand
    analyze_parser = subparsers.add_parser(
        "analyze", help="Analyze a Rocket League replay and write JSON report"
    )
    analyze_parser.add_argument("replay_file", type=str, help="Path to the .replay file")
    analyze_parser.add_argument(
        "--header-only",
        action="store_true",
        help="Use header-only mode (no network parsing)",
    )
    analyze_parser.add_argument(
        "--out",
        type=str,
        default="out",
        help="Directory to write report into (default: out)",
    )
    analyze_parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output",
    )

    args = parser.parse_args()

    # Route to appropriate handler
    if args.command == "ingest":
        return handle_ingest_command(args)
    elif args.command == "analyze":
        # Generate report and write to output directory
        replay_path = Path(args.replay_file)
        report = generate_report(replay_path, header_only=args.header_only)

        # Determine output file path
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / (replay_path.stem + ".json")

        # If error report, still write JSON but signal non-zero exit
        is_error = "error" in report

        # Validate before writing (for clarity in dev/test); skip if error payload
        if not is_error:
            try:
                from .schema import validate_report

                validate_report(report)
            except Exception as e:
                print(f"Validation failed: {e}", file=sys.stderr)
                return 1

        write_report_atomically(report, out_file, pretty=args.pretty)

        # Print path for convenience
        print(str(out_file))
        return 0 if not is_error else 1
    else:
        # No subcommand provided, show help
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
