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


def test_readme_and_api_reference_parser_contract_doc():
    readme = _read("README.md")
    api_doc = _read("docs/api.md")

    assert "docs/parser_adapter.md" in readme
    assert "parser_adapter.md" in api_doc
