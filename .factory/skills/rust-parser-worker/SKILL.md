---
name: rust-parser-worker
description: Implements and verifies Rust parser contract, adapter integration, and parser-facing reliability work.
---

# Rust Parser Worker

NOTE: Startup and cleanup are handled by `worker-base`. This skill defines the WORK PROCEDURE.

## When to Use This Skill

Use this skill for features that primarily change:
- `parsers/rlreplay_rust/`
- `src/rlcoach/parser/`
- parser contract dataclasses or adapter integration
- parser-focused smoke/integration coverage
- corpus-health plumbing tied directly to parser outputs

## Required Skills

None.

## Work Procedure

1. Read the assigned feature, `mission.md`, mission `AGENTS.md`, and `.factory/library/architecture.md` before editing anything.
2. Inspect the owned parser files and surrounding tests to match existing patterns. Do not edit outside the feature’s owned-file scope unless the feature uncovers a small, directly-caused downstream parser-contract bug that must be fixed for correctness.
3. If the assigned feature's expected behavior is already satisfied by pre-existing code, do not attach an unrelated commit or claim new implementation work. Return to the orchestrator immediately with explicit evidence that the feature is pre-satisfied and identify the existing code/tests that already satisfy it.
4. Write or extend failing tests first for the parser contract you are changing. Favor targeted parser interface, adapter, smoke, or corpus-health tests.
5. Run the targeted failing tests to verify the red state.
6. Implement the minimal Rust/parser/adapter changes needed to satisfy the feature while preserving diagnostics-first degraded behavior.
7. If a parser-contract bug first surfaces in a small downstream file outside the normal owned scope (for example event shaping code), you may fix it in the same feature only when the downstream change is tightly coupled, clearly explained in the handoff, and covered by a targeted regression test. Escalate to the orchestrator if the downstream change is non-trivial.
8. For any bug fix discovered via manual CLI validation or behavioral observation, add a targeted regression test for that exact bug surface before marking the feature complete.
9. Run the feature’s targeted verification commands. For Rust-facing work, this usually includes `cargo test` and parser-focused pytest.
10. If the feature affects installation/importability, run `maturin develop` and verify the extension imports.
11. Perform one manual CLI sanity check when the feature changes observable parser behavior (for example `python -m rlcoach.cli analyze ... --adapter rust`).
12. Do not leave broad refactors, speculative cleanup, or unrelated warning fixes mixed into the feature.
13. In the handoff, report exact commands, exact observations, any out-of-scope downstream edits, and any remaining parser decision gates or fallback semantics.

## Example Handoff

```json
{
  "salientSummary": "Completed the Rust parser header/diagnostics expansion and wired the new fields through the Python adapter. cargo test, maturin develop, and targeted parser pytest all passed, and a manual CLI analyze run showed the new diagnostics fields in the output quality block.",
  "whatWasImplemented": "Extended the Rust parser payload to emit the required header metadata and stable diagnostics fields, updated the Python adapter mapping, and added parser interface + smoke coverage so the richer contract is now exercised end-to-end.",
  "whatWasLeftUndone": "Touch-authority feasibility remains for a later feature; this session did not change downstream event preference logic.",
  "verification": {
    "commandsRun": [
      {
        "command": "source .venv/bin/activate && cd parsers/rlreplay_rust && cargo test",
        "exitCode": 0,
        "observation": "Rust crate tests passed; warnings were unchanged and non-blocking."
      },
      {
        "command": "source .venv/bin/activate && cd parsers/rlreplay_rust && maturin develop",
        "exitCode": 0,
        "observation": "Extension rebuilt and imported successfully in the active venv."
      },
      {
        "command": "source .venv/bin/activate && PYTHONPATH=src pytest -q tests/test_rust_adapter.py tests/parser/test_rust_adapter_smoke.py tests/test_parser_interface.py",
        "exitCode": 0,
        "observation": "Parser contract and smoke coverage passed with the new metadata fields present."
      }
    ],
    "interactiveChecks": [
      {
        "action": "Ran `python -m rlcoach.cli analyze testing_replay.replay --adapter rust --out /tmp/rlcoach-parser-check --pretty` and inspected the quality block.",
        "observed": "Command succeeded and the JSON contained explicit parser diagnostics with status and frames_emitted fields."
      }
    ]
  },
  "tests": {
    "added": [
      {
        "file": "tests/test_rust_adapter.py",
        "cases": [
          {
            "name": "test_parse_header_exposes_match_guid_overtime_and_mutators",
            "verifies": "Rust header metadata is mapped into the Python header contract."
          }
        ]
      }
    ]
  },
  "discoveredIssues": [
    {
      "severity": "medium",
      "description": "The convenience `make rust-dev` path still depends on pip availability in the venv; direct `maturin develop` remains the reliable validation path.",
      "suggestedFix": "Keep using direct maturin commands in mission validation guidance unless the environment setup is repaired in a dedicated feature."
    }
  ]
}
```

## When to Return to Orchestrator

- The required parser behavior depends on a mission-level decision gate (especially touch authority) that the feature cannot resolve alone.
- Rust parser changes require broader downstream contract changes beyond the owned files.
- The extension cannot be built/imported in the environment and the issue is not local to the feature.
- Corpus-health or smoke validation exposes a broader reliability regression that needs re-planning.
