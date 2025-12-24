# tests/test_cli_refactor.py
import pytest
from rlcoach.cli import main


def test_main_with_argv_version(capsys):
    """main() should accept argv parameter for testability."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "rlcoach" in captured.out


def test_main_with_argv_help(capsys):
    """main() should show help with no args."""
    exit_code = main([])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "usage" in captured.out.lower() or "help" in captured.out.lower()
