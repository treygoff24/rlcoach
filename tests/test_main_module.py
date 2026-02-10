"""Tests for package module entrypoint."""

import runpy


def test_main_module_invokes_cli_main(monkeypatch):
    called = {"count": 0}

    def fake_main():
        called["count"] += 1
        return 0

    monkeypatch.setattr("rlcoach.cli.main", fake_main)
    runpy.run_module("rlcoach.__main__", run_name="__main__")
    assert called["count"] == 1
