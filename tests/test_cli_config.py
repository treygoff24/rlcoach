# tests/test_cli_config.py
import pytest
from pathlib import Path
from unittest.mock import patch
from rlcoach.cli import main


def test_config_init_creates_template(tmp_path, capsys):
    config_path = tmp_path / "config.toml"

    with patch("rlcoach.cli.get_default_config_path", return_value=config_path):
        exit_code = main(["config", "--init"])

    assert exit_code == 0
    assert config_path.exists()
    content = config_path.read_text()
    assert "[identity]" in content
    assert "[paths]" in content
    assert "[preferences]" in content
    assert "timezone" in content


def test_config_validate_valid(tmp_path, capsys):
    config_path = tmp_path / "config.toml"
    config_path.write_text('''
[identity]
platform_ids = ["steam:76561198012345678"]

[paths]
watch_folder = "~/Replays"
data_dir = "~/.rlcoach/data"
reports_dir = "~/.rlcoach/reports"

[preferences]
target_rank = "GC1"
timezone = "America/Los_Angeles"
''')

    with patch("rlcoach.cli.get_default_config_path", return_value=config_path):
        exit_code = main(["config", "--validate"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "valid" in captured.out.lower()


def test_config_validate_invalid_shows_error(tmp_path, capsys):
    config_path = tmp_path / "config.toml"
    config_path.write_text('''
[identity]
# No platform_ids or display_names!

[paths]
watch_folder = "~/Replays"
data_dir = "~/.rlcoach/data"
reports_dir = "~/.rlcoach/reports"
''')

    with patch("rlcoach.cli.get_default_config_path", return_value=config_path):
        exit_code = main(["config", "--validate"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "error" in captured.out.lower() or "identity" in captured.out.lower()


def test_config_missing_prevents_startup(tmp_path, capsys):
    """Missing config should give clear error message."""
    config_path = tmp_path / "nonexistent.toml"

    with patch("rlcoach.cli.get_default_config_path", return_value=config_path):
        exit_code = main(["config", "--validate"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "not found" in captured.out.lower() or "error" in captured.out.lower()
