"""Command-line interface for rlcoach."""

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .config import ConfigError, IdentityConfig, get_default_config_path, load_config
from .config_templates import CONFIG_TEMPLATE
from .errors import RLCoachError
from .identity import PlayerIdentityResolver
from .ingest import ingest_replay
from .report import generate_report, write_report_atomically
from .report_markdown import write_markdown


def check_exclusion(report: dict) -> str | None:
    """Check if a report should be excluded based on config.

    Returns the excluded player's display name if excluded, None otherwise.
    """
    config_path = get_default_config_path()
    try:
        config = load_config(config_path)
        config.validate()
    except (ConfigError, FileNotFoundError):
        # No config = no exclusion rules
        return None
    except Exception:
        # Malformed config (TOML decode error, etc.) - best-effort, don't crash
        return None

    if not config.identity.excluded_names:
        return None

    resolver = PlayerIdentityResolver(config.identity)
    players = report.get("players", [])

    # Check if "me" is found via display_names - if so, not excluded
    me = resolver.find_me(players)
    if me is not None:
        return None

    # Check if playing on an excluded account
    for player in players:
        display_name = player.get("display_name", "")
        if resolver.should_exclude(display_name):
            return display_name

    return None


def _load_identity_config() -> IdentityConfig | None:
    config_path = get_default_config_path()
    try:
        config = load_config(config_path)
        config.validate()
    except (ConfigError, FileNotFoundError):
        return None
    except Exception:
        return None
    return config.identity


def handle_ingest_watch(args) -> int:
    """Handle ingest --watch mode."""
    import signal

    from .pipeline import IngestionStatus, process_replay_file
    from .watcher import ReplayWatcher

    # Load config
    config_path = get_default_config_path()
    try:
        config = load_config(config_path)
        config.validate()
    except ConfigError as e:
        print(f"Configuration error: {e}")
        return 1
    except FileNotFoundError:
        print(f"Config file not found: {config_path}")
        print("Run 'rlcoach config --init' to create one.")
        return 1

    watch_dir = config.paths.watch_folder
    if not watch_dir.exists():
        print(f"Watch folder does not exist: {watch_dir}")
        return 1

    # Track stats
    stats = {"success": 0, "duplicate": 0, "excluded": 0, "error": 0}

    def process_callback(path: Path) -> None:
        result = process_replay_file(path, config)
        if result.status == IngestionStatus.SUCCESS:
            stats["success"] += 1
            print(f"✓ {path.name} -> {result.replay_id}")
        elif result.status == IngestionStatus.DUPLICATE:
            stats["duplicate"] += 1
            print(f"⊘ {path.name} (duplicate)")
        elif result.status == IngestionStatus.EXCLUDED:
            stats["excluded"] += 1
            print(f"⊘ {path.name} (excluded)")
        else:
            stats["error"] += 1
            print(f"✗ {path.name}: {result.error}")

    print(f"Watching {watch_dir} for new replays...")
    print("Press Ctrl+C to stop")
    print()

    watcher = ReplayWatcher(
        watch_dir=watch_dir,
        callback=process_callback,
        poll_interval=2.0,
        stability_seconds=2.0,
        process_existing=args.process_existing,
    )

    # Handle Ctrl+C gracefully
    stop_requested = False

    def signal_handler(sig, frame):
        nonlocal stop_requested
        if stop_requested:
            # Force exit on second Ctrl+C
            sys.exit(1)
        stop_requested = True
        print("\nStopping watcher...")
        watcher.stop()

    signal.signal(signal.SIGINT, signal_handler)

    watcher.start()

    # Block until stop is requested
    try:
        while not stop_requested:
            import time

            time.sleep(0.5)
    except KeyboardInterrupt:
        pass

    watcher.stop()

    print()
    print(
        "Processed: "
        f"{stats['success']} new, {stats['duplicate']} duplicate, "
        f"{stats['error']} errors"
    )
    return 0


def handle_ingest_command(args) -> int:
    """Handle the ingest subcommand.

    Args:
        args: Parsed command line arguments

    Returns:
        Exit code (0 for success, 1 for error)
    """
    # Check for watch mode
    if args.watch:
        return handle_ingest_watch(args)

    # Require replay_file for non-watch mode
    if not args.replay_file:
        print("Error: replay_file is required when not using --watch")
        return 1

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


def handle_config_command(args) -> int:
    """Handle the config subcommand."""
    config_path = get_default_config_path()

    if args.init:
        if config_path.exists() and not args.force:
            print(f"Config already exists at {config_path}")
            print("Use --force to overwrite")
            return 1

        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(CONFIG_TEMPLATE)
        print(f"Created config template at {config_path}")
        print("Edit this file with your player info before running RLCoach.")
        return 0

    if args.validate:
        try:
            config = load_config(config_path)
            config.validate()
            print(f"Configuration is valid: {config_path}")
            print(f"  Platform IDs: {len(config.identity.platform_ids)}")
            print(f"  Display names: {len(config.identity.display_names)}")
            print(f"  Target rank: {config.preferences.target_rank}")
            print(f"  Timezone: {config.preferences.timezone or '(system default)'}")
            return 0
        except ConfigError as e:
            print(f"Configuration error: {e}")
            return 1
        except FileNotFoundError:
            print(f"Config file not found: {config_path}")
            print("Run 'rlcoach config --init' to create one.")
            return 1
        except Exception as e:
            print(f"Error loading config: {e}")
            return 1

    if args.show:
        try:
            print(config_path.read_text())
            return 0
        except FileNotFoundError:
            print(f"Config file not found: {config_path}")
            return 1

    print("Use --init, --validate, or --show")
    return 1


def handle_benchmarks_command(args) -> int:
    """Handle the benchmarks subcommand."""
    from .benchmarks import BenchmarkValidationError, import_benchmarks
    from .db.models import Benchmark
    from .db.session import create_session, init_db

    # Load config to get db path
    config_path = get_default_config_path()
    try:
        config = load_config(config_path)
    except ConfigError as e:
        print(f"Configuration error: {e}")
        return 1
    except FileNotFoundError:
        print(f"Config file not found: {config_path}")
        print("Run 'rlcoach config --init' to create one.")
        return 1

    # Initialize database
    init_db(config.db_path)

    if args.benchmarks_command == "import":
        file_path = Path(args.file)
        if not file_path.exists():
            print(f"Benchmark file not found: {file_path}")
            return 1

        try:
            count = import_benchmarks(file_path, replace=args.replace)
            print(f"Imported {count} benchmarks from {file_path}")
            return 0
        except BenchmarkValidationError as e:
            print(f"Validation error: {e}")
            return 1
        except Exception as e:
            print(f"Error importing benchmarks: {e}")
            return 1

    elif args.benchmarks_command == "list":
        session = create_session()
        try:
            query = session.query(Benchmark)
            if args.metric:
                query = query.filter(Benchmark.metric == args.metric)
            if args.playlist:
                query = query.filter(Benchmark.playlist == args.playlist)
            if args.rank:
                query = query.filter(Benchmark.rank_tier == args.rank)

            benchmarks = query.order_by(Benchmark.metric, Benchmark.rank_tier).all()

            if not benchmarks:
                print(
                    "No benchmarks found. Use 'rlcoach benchmarks import <file>' "
                    "to add some."
                )
                return 0

            print(
                f"{'Metric':<20} {'Playlist':<10} {'Rank':<6} "
                f"{'Median':>10} {'Source':<20}"
            )
            print("-" * 70)
            for b in benchmarks:
                print(
                    f"{b.metric:<20} {b.playlist:<10} {b.rank_tier:<6} "
                    f"{b.median_value:>10.1f} {b.source:<20}"
                )
            print(f"\nTotal: {len(benchmarks)} benchmarks")
            return 0
        finally:
            session.close()

    print("Use 'benchmarks import <file>' or 'benchmarks list'")
    return 1


def main(argv: list[str] | None = None) -> int:
    """Main CLI entry point.

    Args:
        argv: Command line arguments. If None, uses sys.argv[1:].
    """
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
        "replay_file", type=str, nargs="?", help="Path to the .replay file to ingest"
    )
    ingest_parser.add_argument(
        "--json",
        action="store_true",
        help="Output results in machine-readable JSON format",
    )
    ingest_parser.add_argument(
        "--watch",
        action="store_true",
        help="Watch configured folder for new replay files",
    )
    ingest_parser.add_argument(
        "--process-existing",
        action="store_true",
        dest="process_existing",
        help="Process existing files when starting watch mode",
    )

    # Analyze subcommand
    analyze_parser = subparsers.add_parser(
        "analyze", help="Analyze a Rocket League replay and write JSON report"
    )
    analyze_parser.add_argument(
        "replay_file", type=str, help="Path to the .replay file"
    )
    analyze_parser.add_argument(
        "--header-only",
        action="store_true",
        help="Use header-only mode (no network parsing)",
    )
    analyze_parser.add_argument(
        "--adapter",
        type=str,
        choices=["rust", "null"],
        default="rust",
        help="Parser adapter to use (default: rust)",
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
    analyze_parser.add_argument(
        "--ignore-exclusion",
        action="store_true",
        dest="ignore_exclusion",
        help="Process replay even if playing on an excluded account",
    )

    report_md_parser = subparsers.add_parser(
        "report-md",
        help="Analyze a replay and emit both JSON and Markdown dossiers",
    )
    report_md_parser.add_argument(
        "replay_file", type=str, help="Path to the .replay file"
    )
    report_md_parser.add_argument(
        "--header-only",
        action="store_true",
        help="Use header-only mode (no network parsing)",
    )
    report_md_parser.add_argument(
        "--adapter",
        type=str,
        choices=["rust", "null"],
        default="rust",
        help="Parser adapter to use (default: rust)",
    )
    report_md_parser.add_argument(
        "--out",
        type=str,
        default="out",
        help="Directory where JSON and Markdown reports will be written (default: out)",
    )
    report_md_parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output",
    )
    report_md_parser.add_argument(
        "--ignore-exclusion",
        action="store_true",
        dest="ignore_exclusion",
        help="Process replay even if playing on an excluded account",
    )

    # Config subcommand
    config_parser = subparsers.add_parser("config", help="Manage RLCoach configuration")
    config_parser.add_argument(
        "--init", action="store_true", help="Create template config file"
    )
    config_parser.add_argument(
        "--validate", action="store_true", help="Validate current config"
    )
    config_parser.add_argument(
        "--show", action="store_true", help="Display current config"
    )
    config_parser.add_argument(
        "--force", action="store_true", help="Force overwrite existing config"
    )

    # Benchmarks subcommand
    benchmarks_parser = subparsers.add_parser(
        "benchmarks", help="Manage benchmark data"
    )
    benchmarks_subparsers = benchmarks_parser.add_subparsers(
        dest="benchmarks_command", help="Benchmark commands"
    )

    # benchmarks import
    benchmarks_import = benchmarks_subparsers.add_parser(
        "import", help="Import benchmarks from JSON file"
    )
    benchmarks_import.add_argument("file", type=str, help="Path to benchmark JSON file")
    benchmarks_import.add_argument(
        "--replace", action="store_true", help="Replace all existing benchmarks"
    )

    # benchmarks list
    benchmarks_list = benchmarks_subparsers.add_parser("list", help="List benchmarks")
    benchmarks_list.add_argument("--metric", type=str, help="Filter by metric name")
    benchmarks_list.add_argument("--playlist", type=str, help="Filter by playlist")
    benchmarks_list.add_argument("--rank", type=str, help="Filter by rank tier")

    # Serve subcommand
    serve_parser = subparsers.add_parser("serve", help="Start the API server")
    serve_parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)",
    )
    serve_parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind to (default: 8000)",
    )

    args = parser.parse_args(argv)

    # Route to appropriate handler
    if args.command == "ingest":
        return handle_ingest_command(args)
    elif args.command == "analyze":
        # Generate report and write to output directory
        replay_path = Path(args.replay_file)
        identity_config = _load_identity_config()
        report = generate_report(
            replay_path,
            header_only=args.header_only,
            adapter_name=args.adapter,
            identity_config=identity_config,
        )

        # Check exclusion unless --ignore-exclusion is set
        if not args.ignore_exclusion and "error" not in report:
            excluded_name = check_exclusion(report)
            if excluded_name:
                print(f"⊘ Skipped (excluded account: {excluded_name})")
                print("Use --ignore-exclusion to process anyway")
                return 0

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
    elif args.command == "report-md":
        replay_path = Path(args.replay_file)
        identity_config = _load_identity_config()
        report = generate_report(
            replay_path,
            header_only=args.header_only,
            adapter_name=args.adapter,
            identity_config=identity_config,
        )

        # Check exclusion unless --ignore-exclusion is set
        if not args.ignore_exclusion and "error" not in report:
            excluded_name = check_exclusion(report)
            if excluded_name:
                print(f"⊘ Skipped (excluded account: {excluded_name})")
                print("Use --ignore-exclusion to process anyway")
                return 0

        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        json_path = out_dir / (replay_path.stem + ".json")
        markdown_path = out_dir / (replay_path.stem + ".md")

        is_error = "error" in report

        if not is_error:
            try:
                from .schema import validate_report

                validate_report(report)
            except Exception as e:
                print(f"Validation failed: {e}", file=sys.stderr)
                return 1

        write_report_atomically(report, json_path, pretty=args.pretty)
        write_markdown(report, markdown_path)

        print(f"JSON: {json_path}")
        print(f"Markdown: {markdown_path}")
        return 0 if not is_error else 1
    elif args.command == "config":
        return handle_config_command(args)
    elif args.command == "benchmarks":
        return handle_benchmarks_command(args)
    elif args.command == "serve":
        return handle_serve_command(args)
    else:
        # No subcommand provided, show help
        parser.print_help()
        return 0


def handle_serve_command(args) -> int:
    """Handle the serve subcommand."""
    import uvicorn

    from .api import create_app

    # Load and validate config first
    config_path = get_default_config_path()
    try:
        config = load_config(config_path)
        config.validate()
    except ConfigError as e:
        print(f"Configuration error: {e}")
        return 1
    except FileNotFoundError:
        print(f"Config file not found: {config_path}")
        print("Run 'rlcoach config --init' to create one.")
        return 1

    host = args.host
    port = args.port

    print(f"Starting RLCoach API server at http://{host}:{port}")
    print("Press Ctrl+C to stop")

    app = create_app()
    uvicorn.run(app, host=host, port=port, log_level="info")

    return 0


if __name__ == "__main__":
    sys.exit(main())
