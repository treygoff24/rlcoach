"""Smoke tests for rlcoach package."""

import subprocess
import sys
from importlib import import_module


def test_package_imports():
    """Test that the main package can be imported."""
    rlcoach = import_module("rlcoach")
    assert hasattr(rlcoach, "__version__")
    assert rlcoach.__version__ == "0.1.0"


def test_cli_module_imports():
    """Test that the CLI module can be imported."""
    cli = import_module("rlcoach.cli")
    assert hasattr(cli, "main")
    assert callable(cli.main)


def test_cli_version_flag():
    """Test that the CLI --version flag works."""
    result = subprocess.run(
        [sys.executable, "-m", "rlcoach.cli", "--version"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "rlcoach 0.1.0" in result.stdout


def test_cli_help_flag():
    """Test that the CLI --help flag works."""
    result = subprocess.run(
        [sys.executable, "-m", "rlcoach.cli", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "rlcoach" in result.stdout
    assert "Rocket League replay analysis" in result.stdout


def test_cli_main_function():
    """Test that the CLI main function returns 0."""
    cli = import_module("rlcoach.cli")

    # Mock sys.argv to avoid argparse trying to parse actual command line
    original_argv = sys.argv
    try:
        sys.argv = ["rlcoach"]
        result = cli.main()
        assert result == 0
    finally:
        sys.argv = original_argv
