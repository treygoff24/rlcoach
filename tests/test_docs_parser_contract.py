"""Docs contract checks for parser adapter behavior."""

from __future__ import annotations

from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_parser_adapter_doc_contains_required_sections_and_commands():
    content = _read("docs/parser_adapter.md")

    required_sections = [
        "## Build And Dev Workflow",
        "## Current Backend Posture",
        "## Header Contract",
        "## Network Frame Contract",
        "## Parser Event Streams",
        "## Diagnostics And Degradation Semantics",
        "## Test And Corpus-Health Commands",
    ]
    for section in required_sections:
        assert section in content

    required_commands = [
        "source .venv/bin/activate && PYTHONPATH=src pytest -q",
        "source .venv/bin/activate && cd parsers/rlreplay_rust && cargo test",
        "source .venv/bin/activate && cd parsers/rlreplay_rust && maturin develop",
        (
            "source .venv/bin/activate && PYTHONPATH=src python "
            "scripts/parser_corpus_health.py --roots replays,Replay_files --json"
        ),
    ]
    for command in required_commands:
        assert command in content

    required_current_behavior_terms = [
        "docs/parser_adapter.md",
        "network_diagnostics",
        "scorecard",
        "parser_event_coverage",
        "event_provenance",
        "parser_touch_events",
        "parser_demo_events",
        "parser_tickmarks",
        "parser_kickoff_markers",
    ]
    for term in required_current_behavior_terms:
        assert term in content

    required_terms = [
        "scorecard",
        "parser_event_coverage",
        "event_provenance",
        "scorecard_coverage",
        "True",
        "False",
        "None",
    ]
    for term in required_terms:
        assert term in content


def test_readme_and_api_reference_parser_contract_doc():
    readme = _read("README.md")
    api_doc = _read("docs/api.md")

    assert "docs/parser_adapter.md" in readme
    assert "parser_adapter.md" in api_doc

    stale_test_counts = ["553 tests", "388 tests", "261 tests"]
    for stale_count in stale_test_counts:
        assert stale_count not in readme

    current_readme_terms = [
        "diagnostics-first",
        "parser event/provenance coverage",
        "scorecard coverage",
    ]
    for term in current_readme_terms:
        assert term in readme


def test_master_status_tracks_current_parser_contract_snapshot():
    master_status = _read("codex/docs/master_status.md")
    network_issue = _read("codex/docs/network-frames-integration-issue.md")

    for content in (master_status, network_issue):
        assert "2026-04-09" in content
        assert "docs/parser_adapter.md" in content
        assert "parser_event_coverage" in content
        assert "event_provenance" in content
        assert "scorecard_coverage" in content


def test_status_docs_reference_current_parser_contract_and_no_stale_counts():
    docs = {
        "README.md": _read("README.md"),
        "docs/api.md": _read("docs/api.md"),
        "docs/parser_adapter.md": _read("docs/parser_adapter.md"),
        "codex/docs/master_status.md": _read("codex/docs/master_status.md"),
        "codex/docs/network-frames-integration-issue.md": _read(
            "codex/docs/network-frames-integration-issue.md"
        ),
    }

    for content in docs.values():
        assert "codex/docs/parser_adapter.md" not in content

    assert "**Last updated:** 2026-04-09" in docs["codex/docs/master_status.md"]

    stale_test_count_claims = ["553 tests", "388 tests", "261 tests"]
    for path, content in docs.items():
        for claim in stale_test_count_claims:
            assert claim not in content, f"{path} still contains {claim}"

    required_current_behavior = [
        "diagnostics-first",
        "parser event",
        "scorecard",
        "corpus",
    ]
    combined = "\n".join(docs.values()).lower()
    for phrase in required_current_behavior:
        assert phrase in combined
