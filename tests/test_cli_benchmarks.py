# tests/test_cli_benchmarks.py
import pytest
import json
from pathlib import Path
from unittest.mock import patch
from rlcoach.cli import main
from rlcoach.db.session import reset_engine


@pytest.fixture(autouse=True)
def reset_db():
    yield
    reset_engine()


def test_benchmarks_import_success(tmp_path, capsys):
    db_path = tmp_path / "data" / "rlcoach.db"
    config_path = tmp_path / "config.toml"
    config_path.write_text(f'''
[identity]
platform_ids = ["steam:123"]

[paths]
watch_folder = "~/Replays"
data_dir = "{tmp_path / "data"}"
reports_dir = "{tmp_path / "reports"}"
''')

    benchmark_file = tmp_path / "benchmarks.json"
    benchmark_file.write_text(json.dumps({
        "metadata": {"source": "test"},
        "benchmarks": [
            {"metric": "bcpm", "playlist": "DOUBLES", "rank_tier": "GC1", "median": 380}
        ]
    }))

    with patch("rlcoach.cli.get_default_config_path", return_value=config_path):
        exit_code = main(["benchmarks", "import", str(benchmark_file)])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "imported" in captured.out.lower() or "1" in captured.out


def test_benchmarks_list_shows_data(tmp_path, capsys):
    db_path = tmp_path / "data" / "rlcoach.db"
    config_path = tmp_path / "config.toml"
    config_path.write_text(f'''
[identity]
platform_ids = ["steam:123"]

[paths]
watch_folder = "~/Replays"
data_dir = "{tmp_path / "data"}"
reports_dir = "{tmp_path / "reports"}"
''')

    benchmark_file = tmp_path / "benchmarks.json"
    benchmark_file.write_text(json.dumps({
        "metadata": {"source": "test"},
        "benchmarks": [
            {"metric": "bcpm", "playlist": "DOUBLES", "rank_tier": "GC1", "median": 380}
        ]
    }))

    with patch("rlcoach.cli.get_default_config_path", return_value=config_path):
        # First import
        main(["benchmarks", "import", str(benchmark_file)])
        # Then list
        exit_code = main(["benchmarks", "list"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "bcpm" in captured.out or "DOUBLES" in captured.out or "GC1" in captured.out
