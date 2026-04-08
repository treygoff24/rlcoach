---
name: python-parser-worker
description: Implements and verifies normalization, events, mechanics, report, schema, and docs work for the parser mission.
---

# Python Parser Worker

NOTE: Startup and cleanup are handled by `worker-base`. This skill defines the WORK PROCEDURE.

## When to Use This Skill

Use this skill for features that primarily change:
- `src/rlcoach/normalize.py`
- `src/rlcoach/events/`
- `src/rlcoach/analysis/`
- `src/rlcoach/report.py`
- `schemas/`
- parser-facing docs and tests tied to those surfaces

## Required Skills

None.

## Work Procedure

1. Read the assigned feature, `mission.md`, mission `AGENTS.md`, and `.factory/library/architecture.md` before editing.
2. Inspect adjacent code and tests to preserve existing style and data-shape conventions.
3. Add failing tests first for the exact observable behavior in scope. Prefer focused tests over broad suite-first runs.
4. Run the targeted tests to confirm failure.
5. Implement the smallest change set that makes the new parser behavior visible at the JSON/Markdown/schema boundary.
6. If the feature changes event preference logic, verify parser-first behavior and no double-counting with targeted tests and one CLI/report sanity run.
7. If the feature changes mechanics/report/schema output, verify key presence, arithmetic consistency, and JSON↔Markdown parity.
8. Run the feature’s targeted verification commands, then rerun any touched contract/doc tests.
9. Report exact file-level behavior changes, commands, and remaining risks in the handoff.

## Example Handoff

```json
{
  "salientSummary": "Completed the authoritative-first event threading feature across normalization and event detectors. Targeted tests passed, and a manual analyze/report-md sanity check showed parser event provenance flowing into both JSON and Markdown outputs without duplicate events.",
  "whatWasImplemented": "Updated normalization to preserve parser-authored event carriers and explicit component-state semantics, switched touches/demos/kickoffs to parser-first consumption with fallback provenance, and added focused tests covering no-double-counting and degraded fallback behavior.",
  "whatWasLeftUndone": "Corpus-health coverage metrics for the new event provenance remain for a later milestone; this feature only changed the runtime event/report surfaces.",
  "verification": {
    "commandsRun": [
      {
        "command": "source .venv/bin/activate && PYTHONPATH=src pytest -q tests/test_normalize.py tests/test_events.py tests/test_events_calibration_synthetic.py",
        "exitCode": 0,
        "observation": "Normalization and parser-first event preference tests passed, including no-double-counting scenarios."
      },
      {
        "command": "source .venv/bin/activate && PYTHONPATH=src pytest -q tests/test_schema_validation.py tests/test_report_end_to_end.py",
        "exitCode": 0,
        "observation": "Report/schema checks passed with the updated event provenance fields."
      }
    ],
    "interactiveChecks": [
      {
        "action": "Ran `python -m rlcoach.cli report-md testing_replay.replay --adapter rust --out /tmp/rlcoach-report-check --pretty` and compared JSON vs Markdown event/provenance output.",
        "observed": "Both outputs succeeded and showed consistent parser diagnostics and event provenance."
      }
    ]
  },
  "tests": {
    "added": [
      {
        "file": "tests/test_events.py",
        "cases": [
          {
            "name": "test_parser_authority_is_preferred_without_double_counting",
            "verifies": "Parser-authored events outrank heuristic duplicates and preserve source visibility."
          }
        ]
      }
    ]
  },
  "discoveredIssues": []
}
```

## When to Return to Orchestrator

- The feature uncovers a parser-layer contract ambiguity that must be resolved before Python-side work can be considered correct.
- The owned files cannot satisfy the requested behavior without expanding scope into Rust parser work or mission-level docs decisions.
- Validation reveals broad pre-existing formatter/lint/test failures unrelated to the feature that block trustworthy verification.
