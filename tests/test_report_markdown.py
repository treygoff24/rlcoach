"""Tests for the Markdown report composer."""

import json
from pathlib import Path

from rlcoach import report_markdown

FIXTURE_DIR = Path(__file__).parent / "goldens"


def _load_report(name: str) -> dict:
    return json.loads((FIXTURE_DIR / f"{name}.json").read_text())


def _load_markdown(name: str) -> str:
    return (FIXTURE_DIR / f"{name}.md").read_text()


def test_render_markdown_matches_golden_synthetic() -> None:
    report = _load_report("synthetic_small")
    expected = _load_markdown("synthetic_small")
    actual = report_markdown.render_markdown(report)
    assert actual == expected


def test_render_markdown_matches_golden_header_only() -> None:
    report = _load_report("header_only")
    expected = _load_markdown("header_only")
    actual = report_markdown.render_markdown(report)
    assert actual == expected


def test_render_markdown_handles_error_payload() -> None:
    error_report = {"error": "unreadable_replay_file", "details": "CRC mismatch"}
    markdown = report_markdown.render_markdown(error_report)
    assert "## Error Summary" in markdown
    assert "CRC mismatch" in markdown
    assert "unreadable_replay_file" in markdown
