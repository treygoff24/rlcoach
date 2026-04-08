---
name: parser-release-worker
description: Finalizes parser mission docs, reliability surfaces, and full quality-gate verification.
---

# Parser Release Worker

NOTE: Startup and cleanup are handled by `worker-base`. This skill defines the WORK PROCEDURE.

## When to Use This Skill

Use this skill for features that primarily change:
- corpus-health reporting and release-facing validation surfaces
- parser contract/status/API documentation
- final report/schema parity fixes
- final quality-gate or readiness work for the parser mission

## Required Skills

None.

## Work Procedure

1. Read the assigned feature, mission `AGENTS.md`, `.factory/library/user-testing.md`, and `.factory/library/architecture.md` before touching files.
2. Confirm the exact validation contract assertions this feature fulfills and work backward from those observable outcomes.
3. If editing docs, keep them tightly aligned with shipped behavior and validation commands. Remove stale “future/stub” claims only when the behavior is actually implemented.
4. If editing corpus-health/reporting, verify JSON summary shape and CLI/report behavior with real commands instead of relying only on static tests.
5. Run the feature’s targeted verification commands first, then any broader gate the feature explicitly requires.
6. When full-gate verification is in scope, report every command separately with exit code and concrete observation; do not summarize “all passed” without evidence.
7. If pre-existing failures remain outside the feature’s scope, surface them explicitly in the handoff instead of hiding them.

## Example Handoff

```json
{
  "salientSummary": "Completed the parser release-lock feature by updating parser contract docs, aligning corpus-health coverage metrics with the shipped parser contract, and rerunning the full parser gate set. The runtime CLI surfaces and docs now describe the same behavior.",
  "whatWasImplemented": "Updated the parser contract/status docs to match the completed Rust parser behavior, extended corpus-health to report the final event/provenance coverage metrics, and verified the mission’s required release gates including CLI analyze/report-md, cargo test, parser-focused pytest, full pytest, lint/format checks, and corpus-health.",
  "whatWasLeftUndone": "None.",
  "verification": {
    "commandsRun": [
      {
        "command": "source .venv/bin/activate && cd parsers/rlreplay_rust && cargo test",
        "exitCode": 0,
        "observation": "Rust parser crate tests passed."
      },
      {
        "command": "source .venv/bin/activate && cd parsers/rlreplay_rust && maturin develop",
        "exitCode": 0,
        "observation": "Rust extension rebuilt successfully."
      },
      {
        "command": "source .venv/bin/activate && PYTHONPATH=src pytest -q",
        "exitCode": 0,
        "observation": "Full Python suite passed after the final parser/report/doc updates."
      },
      {
        "command": "source .venv/bin/activate && ruff check src/ tests/",
        "exitCode": 0,
        "observation": "Lint passed cleanly."
      },
      {
        "command": "source .venv/bin/activate && black --check src/ tests/",
        "exitCode": 0,
        "observation": "Formatter check passed without diffs."
      },
      {
        "command": "source .venv/bin/activate && PYTHONPATH=src python scripts/parser_corpus_health.py --roots replays,Replay_files --json",
        "exitCode": 0,
        "observation": "Corpus-health summary remained at or above the mission floor and included the new event/provenance coverage metrics."
      }
    ],
    "interactiveChecks": [
      {
        "action": "Ran both `analyze` and `report-md` on `testing_replay.replay` with the Rust adapter and compared diagnostics across outputs.",
        "observed": "JSON and Markdown outputs were both generated successfully and reflected the same parser diagnostics/provenance state."
      }
    ]
  },
  "tests": {
    "added": [
      {
        "file": "tests/test_docs_parser_contract.py",
        "cases": [
          {
            "name": "test_parser_docs_describe_final_contract",
            "verifies": "Parser docs mention the shipped authoritative/fallback contract and validation commands."
          }
        ]
      }
    ]
  },
  "discoveredIssues": [
    {
      "severity": "low",
      "description": "The environment still prefers direct `maturin develop` over `make rust-dev` because pip availability in the venv is brittle.",
      "suggestedFix": "Keep the direct maturin path in docs/services guidance unless environment bootstrap is repaired separately."
    }
  ]
}
```

## When to Return to Orchestrator

- Full-gate verification is blocked by unrelated pre-existing failures that need scope decisions.
- Corpus-health floors or final CLI outputs regress in ways that suggest broader architectural issues.
- Documentation truth would require claiming behavior that is not yet actually implemented.
