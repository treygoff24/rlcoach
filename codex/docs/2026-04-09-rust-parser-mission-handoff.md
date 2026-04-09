# Rust Parser Mission Handoff

Date: 2026-04-09
Repo: `/Users/treygoff/Code/rlcoach`
Branch: `feat/full-parser-analysis-vision`
Mission dir: `/Users/treygoff/.factory/missions/316e30d3-4db6-4f1d-aba2-07992a5608a9`

## Why this document exists

The Factory mission runner became unreliable due to repeated worker-launch failures (`Droid process exited unexpectedly (exit code 0)`) after the parser-contract milestone was completed. This document is the full resumable handoff so the mission can be continued in another environment/session without reconstructing context from logs.

## Executive summary

This mission was created to finish the Rust parser to the repo's fullest parser vision by synthesizing the strongest available planning/spec documents instead of following a single weaker source.

The mission is not complete yet.

What is complete:
- Mission planning and decomposition are done.
- Validation contract and assertion tracking are done.
- Repo-side Factory mission infrastructure is in place.
- Milestone 1 (`parser-contract`) is complete and effectively validated.
- Several real parser-contract bugs were fixed and validated.

What remains:
- Normalization/event threading for parser authority.
- Mechanics full-vision parity.
- `report-md` parity and error-contract closure.
- Corpus-health final contract closure.
- Parser docs/status/API updates.
- Final cross-surface gates.

## Canonical definition of done

The mission definition of done was synthesized from these sources:
- `docs/plans/2026-04-07-rlcoach-full-parser-analysis-vision.md`
- `docs/plans/2026-04-07-rlcoach-full-parser-analysis-implementation.md`
- `codex/Plans/2026-02-10-parser-refactor-update-plan.md`
- `codex/Plans/rlcoach_implementation_plan.md`
- `MECHANICS_SPEC.md`
- `MECHANICS_IMPLEMENTATION_PLAN_v2.md`

The synthesized completion target is:
1. Complete the Rust parser contract for healthy, degraded, null-adapter, and unreadable-input modes.
2. Preserve parser diagnostics/provenance explicitly in shipped outputs.
3. Surface expanded header metadata and parser-authored event carriers.
4. Thread parser authority through normalization and event detection so downstream outputs become parser-first with clear provenance and no double-counting.
5. Finish advanced mechanics parity and keep mechanics arithmetic/logical consistency.
6. Ensure JSON report, Markdown report, schema, and CLI behavior all agree.
7. Extend corpus-health so it measures the final parser contract, including degraded/error/event/provenance coverage.
8. Update docs so shipped parser behavior is described as current reality, not future work.
9. Pass full local quality gates plus corpus-health verification.

## Mission structure

### Milestone 1 — `parser-contract`
Goal: freeze the parser contract, complete core Rust CLI/runtime modes, emit authoritative parser event carriers, and validate the CLI analyze surface.

### Milestone 2 — `normalize-events`
Goal: thread parser authority through normalization and event detection so final analyze output is parser-first, provenance-visible, internally consistent, and stateless across reruns.

### Milestone 3 — `mechanics`
Goal: finish mechanics full-vision parity, including advanced mechanics families, team-level rollups, arithmetic consistency, and jump/flip logic.

### Milestone 4 — `report-corpus`
Goal: align `report-md`, JSON/schema, and corpus-health with the completed parser contract.

### Milestone 5 — `docs-lockdown`
Goal: update parser docs/status/API docs and run final cross-surface validation gates.

## Validation contract

The authoritative contract lives at:
- `~/.factory/missions/316e30d3-4db6-4f1d-aba2-07992a5608a9/validation-contract.md`

It contains 39 assertions across these areas:

### CLI Analyze
- Healthy success path and schema validity
- Diagnostics/provenance visibility
- Expanded header metadata
- Error contract for unreadable input
- Header-only degraded contract
- Null-adapter degraded contract
- Referential integrity across players/teams/summaries
- Timeline ordering and event consistency
- Repeated-run statelessness
- Parser-authority provenance and no-double-counting
- Explicit degraded parser states
- Observable touch-authority outcome
- Advanced mechanics families and arithmetic consistency

### CLI Report Markdown
- Paired JSON + Markdown output
- Schema-valid JSON artifact
- Markdown parity with completed parser/report surface
- Explicit degraded behavior
- JSON/Markdown content alignment
- Error behavior for unreadable input
- Advanced mechanics visible in Markdown

### Corpus Health
- Machine-readable JSON summary
- Reliability floor >= 99.5% network success
- Explicit degraded/error reporting
- Usable parser coverage, not just raw parse attempts
- Event/provenance coverage metrics after completion
- Explicit invalid-root/prerequisite behavior

### Contract / Docs
- Parser docs describe shipped behavior
- Docs no longer describe completed work as future work
- Parser doc checks still pass

### Cross-surface
- `analyze` and `report-md` agree on diagnostics/provenance
- CLI outputs agree with corpus-health degraded classifications
- Full local quality gates pass
- End-to-end CLI output remains consumable after completion

## Current validation-state snapshot

Validation state file:
- `~/.factory/missions/316e30d3-4db6-4f1d-aba2-07992a5608a9/validation-state.json`

Current state:
- Passed: 7 assertions
- Pending: 32 assertions
- Failed: 0
- Blocked: 0

Passed assertions:
- `VAL-ANALYZE-001`
- `VAL-ANALYZE-002`
- `VAL-ANALYZE-003`
- `VAL-ANALYZE-004`
- `VAL-ANALYZE-004B`
- `VAL-ANALYZE-004C`
- `VAL-ANALYZE-004D`

These correspond to the validated parser-contract analyze-surface milestone.

## Mission artifacts already created

### Mission-dir artifacts
Under `~/.factory/missions/316e30d3-4db6-4f1d-aba2-07992a5608a9/`:
- `mission.md`
- `validation-contract.md`
- `validation-state.json`
- `features.json`
- `AGENTS.md`
- `progress_log.jsonl`

### Repo-side `.factory` artifacts
Under `/Users/treygoff/Code/rlcoach/.factory/`:
- `services.yaml`
- `init.sh`
- `library/architecture.md`
- `library/environment.md`
- `library/user-testing.md`
- `skills/rust-parser-worker/SKILL.md`
- `skills/python-parser-worker/SKILL.md`
- `skills/parser-release-worker/SKILL.md`
- `validation/parser-contract/scrutiny/...`
- `validation/parser-contract/user-testing/...`

## Commands and environment assumptions

These were the effective local commands discovered and used during the mission.

### Critical environment rule
All Python commands must use the project venv:

```bash
source .venv/bin/activate && <command>
```

### Primary commands

```bash
source .venv/bin/activate && PYTHONPATH=src pytest -q
source .venv/bin/activate && PYTHONPATH=src pytest -q tests/test_rust_adapter.py tests/parser/test_rust_adapter_smoke.py tests/test_parser_interface.py
source .venv/bin/activate && ruff check src/ tests/
source .venv/bin/activate && black --check src/ tests/
source .venv/bin/activate && PYTHONPATH=src python scripts/parser_corpus_health.py --roots replays,Replay_files --json
source .venv/bin/activate && PYTHONPATH=src python -m rlcoach.cli analyze testing_replay.replay --adapter rust --out /tmp/out --pretty
source .venv/bin/activate && PYTHONPATH=src python -m rlcoach.cli report-md testing_replay.replay --adapter rust --out /tmp/out --pretty
source .venv/bin/activate && cd parsers/rlreplay_rust && cargo test
source .venv/bin/activate && cd parsers/rlreplay_rust && maturin develop
```

### Important environment notes
- Docker was unavailable and intentionally not required for this mission.
- The mission was structured to avoid local service/process dependencies.
- `make rust-dev` was considered brittle because the venv pip path behaved unexpectedly; direct `maturin develop` was reliable and should be preferred.
- Dry-run and validator observations indicated ~16 logical CPUs and ~64 GiB RAM; 4 concurrent validators was considered safe.

## Completed work and outcomes

### 1. Mission scaffold and planning
Commit:
- `de16738 chore(factory): scaffold rust parser mission artifacts`

This created the execution mission and repo-side `.factory` scaffolding.

Important caveat:
- Scrutiny later flagged `freeze-parser-contract-foundation` because its handoff cited `de16738`, but that commit only contains mission scaffolding, not parser/schema/test code. This was treated as a non-code provenance/handoff problem rather than a product defect.

### 2. CLI/runtime contract milestone work
Commit:
- `758c817 fix(kickoffs): use BACK role instead of UNKNOWN for parser markers`

What happened:
- This unblocked schema-valid healthy Rust analyze output by replacing invalid kickoff marker role `UNKNOWN` with `BACK`.
- It was later found to be semantically insufficient and was superseded by a real role-inference fix.

### 3. Authoritative parser touch emission
Commit:
- `fb77725 feat(parser): emit authoritative touch events from Rust parser`

What landed:
- Real Rust touch detection emitting `parser_touch_events` with `source='parser'` provenance.
- This made the touch-authority decision explicit at the parser-facing layer.

### 4. Pre-existing Black drift fix
Commit:
- `4ab219a style: apply black formatting to three test files with pre-existing drift`

Why it mattered:
- Scrutiny could not proceed until `black --check src/ tests/` passed.
- This change was a scope expansion approved to unblock milestone scrutiny.

### 5. Scrutiny-guidance updates
Commit:
- `477c643 chore(factory): record parser scrutiny follow-ups`

What changed:
- Preserved scrutiny findings.
- Tightened `rust-parser-worker` guidance so pre-satisfied features must be escalated honestly, downstream fixes can be made when necessary, and behavioral fixes require regression tests.

### 6. Rust touch debounce bug fix
Functional commit:
- `c5d7360 fix(parser): emit repeated touches after debounce window instead of suppressing`

Follow-up style commit recorded in mission history:
- `ce14781 style: fix line-too-long in test_rust_adapter.py`

What was fixed:
- Subsequent valid touches from the same actor were being suppressed after the first touch.
- Regression test added: `test_parser_touch_events_collected_across_replay` in `tests/test_rust_adapter.py`.

### 7. Real kickoff role inference fix
Commit:
- `bacbab1 fix(parser): infer kickoff roles from positions instead of hardcoding BACK`

What was fixed:
- `_kickoffs_from_parser_markers()` now infers GO/CHEAT/WING/BACK from positions instead of hardcoding `BACK`.
- Regression test added: `test_parser_kickoff_markers_infer_roles_from_positions` in `tests/test_events.py`.

### 8. Scrutiny synthesis update and override
Commits:
- `3991dda chore(factory): update parser-contract scrutiny synthesis`
- `1469205 chore(factory): override parser contract scrutiny blocker`

Meaning:
- Round-2 scrutiny re-reviewed the real product fixes successfully.
- The only remaining blocker was the non-code provenance issue on the pre-satisfied foundation feature.
- That blocker was explicitly overridden with rationale in `.factory/validation/parser-contract/scrutiny/synthesis.json`.

### 9. Parser-contract user testing
Commit:
- `4982fa1 test(parser-contract): record user testing validation`

What happened:
- Real CLI-based user testing was run for the parser-contract analyze assertions.
- It found a real failure in `VAL-ANALYZE-004C`.

### 10. Header-only no-network leakage fix
Commit:
- `9bac88b fix(parser): prevent network-derived goal leakage in header-only mode`

What was fixed:
- `analyze --header-only` was still emitting goal/timeline events even when `parsed_network_data=false` and `frames_emitted=0`.
- `src/rlcoach/events/goals.py` gained header-only behavior.
- `src/rlcoach/report.py` was updated so header-only/no-network runs do not imply real network-derived analysis.
- Regression added: `test_header_only_no_network_no_goal_leakage` in `tests/test_report_end_to_end.py`.

### 11. Parser-contract user-testing rerun
Commit:
- `64dd5ca test(parser-contract): record header-only rerun`

Outcome:
- The only previously failing assertion (`VAL-ANALYZE-004C`) passed on rerun.
- Parser-contract user testing became effectively clear.

## Parser-contract milestone status

### Practical status
`parser-contract` is complete enough to treat as done.

### Why
- Validators pass.
- The real runtime defects found by scrutiny/user-testing were fixed.
- The only remaining scrutiny blocker was an implementation-handoff provenance issue for a pre-satisfied feature, not a runtime/schema/behavior defect.
- User-testing round 2 passed.
- Validation-state records the parser-contract analyze assertions as passed.

### Repo-side validation artifacts to inspect
- `.factory/validation/parser-contract/scrutiny/synthesis.json`
- `.factory/validation/parser-contract/scrutiny/synthesis.round1.json`
- `.factory/validation/parser-contract/scrutiny/reviews/*.json`
- `.factory/validation/parser-contract/user-testing/synthesis.json`
- `.factory/validation/parser-contract/user-testing/flows/*.json`

## Remaining feature plan in execution order

The current `features.json` says the next pending feature is:

### Next feature
#### `thread-parser-authority-through-normalize-and-events`
Milestone: `normalize-events`
Skill: `python-parser-worker`

Intent:
- Make analyze output parser-first and provenance-visible through the Python normalization/event layers.
- Preserve referential integrity.
- Preserve timeline ordering.
- Prevent double-counting.
- Keep degraded parser state explicit.
- Make repeated runs stateless.
- Make the touch-authority contract observable in shipped analyze output.

Assertions owned by this feature:
- `VAL-ANALYZE-004E`
- `VAL-ANALYZE-004F`
- `VAL-ANALYZE-004G`
- `VAL-ANALYZE-005`
- `VAL-ANALYZE-006`
- `VAL-ANALYZE-007`
- `VAL-ANALYZE-008`
- `VAL-ANALYZE-011`

Verification plan:
```bash
source .venv/bin/activate && PYTHONPATH=src pytest -q tests/test_normalize.py tests/test_events.py tests/test_events_calibration_synthetic.py tests/test_parser_interface.py
source .venv/bin/activate && PYTHONPATH=src python -m rlcoach.cli analyze testing_replay.replay --adapter rust --out /tmp/rlcoach-m2-analyze --pretty
```
Manual follow-up:
- Rerun the same analyze command twice and inspect provenance, timeline ordering, and event consistency.

### Remaining later features
1. `finish-mechanics-full-vision-parity`
2. `align-report-md-json-and-error-contracts`
3. `extend-corpus-health-to-final-parser-contract`
4. `update-parser-contract-status-and-api-docs`
5. `finalize-cross-surface-parser-gates`

## Current blocker: mission runner instability

The mission stopped not because of product-code failure, but because worker launch repeatedly failed on the next feature.

Observed runner error:
- `Worker process exited unexpectedly: Droid process exited unexpectedly (exit code 0)`

Most recent failed worker sessions for the next feature:
- `0a1eb73b-5d02-4961-9f67-07118df13daf`
- `3d34ac1f-1a7b-4e37-a02a-bff42f276be9`

This happened after parser-contract user-testing had already passed.

## Important repo state right now

Current `git status --short` at handoff time:
```bash
M src/rlcoach/normalize.py
```

Important note:
- `src/rlcoach/normalize.py` is modified right now, but this document does not audit that diff.
- Treat that file as an unknown external/incomplete change that must be reviewed before resuming implementation.
- Do not assume it is mission-approved or complete.

Current recent git history:
```text
64dd5ca test(parser-contract): record header-only rerun
9bac88b fix(parser): prevent network-derived goal leakage in header-only mode
4982fa1 test(parser-contract): record user testing validation
1469205 chore(factory): override parser contract scrutiny blocker
3991dda chore(factory): update parser-contract scrutiny synthesis
bacbab1 fix(parser): infer kickoff roles from positions instead of hardcoding BACK
ce14781 style: fix line-too-long in test_rust_adapter.py
c5d7360 fix(parser): emit repeated touches after debounce window instead of suppressing
477c643 chore(factory): record parser scrutiny follow-ups
4ab219a style: apply black formatting to three test files with pre-existing drift
fb77725 feat(parser): emit authoritative touch events from Rust parser
758c817 fix(kickoffs): use BACK role instead of UNKNOWN for parser markers
```

## Recommended resume procedure

If resuming outside Factory mission runner, do this first:

1. Review `src/rlcoach/normalize.py` diff.
2. Re-read these files:
   - `~/.factory/missions/316e30d3-4db6-4f1d-aba2-07992a5608a9/features.json`
   - `~/.factory/missions/316e30d3-4db6-4f1d-aba2-07992a5608a9/validation-contract.md`
   - `~/.factory/missions/316e30d3-4db6-4f1d-aba2-07992a5608a9/validation-state.json`
   - `.factory/library/architecture.md`
   - `.factory/library/user-testing.md`
3. Start with `thread-parser-authority-through-normalize-and-events`.
4. Preserve the existing assertion ownership in `features.json` unless intentionally restructuring the mission.
5. Continue milestone-by-milestone in the existing order.
6. After each milestone, rerun scrutiny and user-testing against the milestone’s owned assertions.

## Recommended resume procedure inside Factory mission runner

If trying Factory again:
1. Confirm Droid/factoryd stability before starting workers.
2. Re-open the mission and inspect `progress_log.jsonl`.
3. Verify `features.json` still has `thread-parser-authority-through-normalize-and-events` as the top pending feature.
4. Inspect `src/rlcoach/normalize.py` before launching a worker.
5. Prefer direct `maturin develop` over `make rust-dev`.
6. Expect the parser-contract milestone to remain sealed/done; continue with `normalize-events`.

## Known non-product issues encountered during mission

1. Worker-launch instability in Droid/factoryd.
2. Docker unavailable locally, but the mission does not require it.
3. `make rust-dev` brittle; direct `maturin develop` works.
4. Pre-existing Black drift originally blocked scrutiny but was fixed in-scope.
5. The foundation feature had a handoff/commit provenance problem, but not a missing product-code problem.

## Files most likely to matter next

### Core implementation surfaces
- `src/rlcoach/normalize.py`
- `src/rlcoach/events/`
- `src/rlcoach/report.py`
- `src/rlcoach/events/goals.py`
- `src/rlcoach/events/kickoffs.py`
- `parsers/rlreplay_rust/src/lib.rs`
- `tests/test_normalize.py`
- `tests/test_events.py`
- `tests/test_events_calibration_synthetic.py`
- `tests/test_rust_adapter.py`
- `tests/test_report_end_to_end.py`

### Mission/state surfaces
- `~/.factory/missions/316e30d3-4db6-4f1d-aba2-07992a5608a9/features.json`
- `~/.factory/missions/316e30d3-4db6-4f1d-aba2-07992a5608a9/validation-contract.md`
- `~/.factory/missions/316e30d3-4db6-4f1d-aba2-07992a5608a9/validation-state.json`
- `~/.factory/missions/316e30d3-4db6-4f1d-aba2-07992a5608a9/progress_log.jsonl`
- `.factory/validation/parser-contract/scrutiny/synthesis.json`
- `.factory/validation/parser-contract/user-testing/synthesis.json`

## Minimal next-action checklist

If someone picks this up immediately, the shortest correct next sequence is:

1. Review `git diff -- src/rlcoach/normalize.py`.
2. Implement/finish `thread-parser-authority-through-normalize-and-events`.
3. Run the feature’s targeted pytest commands.
4. Run real CLI `analyze` checks with Rust adapter and repeated reruns.
5. Update mission state if continuing under Factory.
6. Proceed to mechanics milestone.

## Bottom line

The parser-contract milestone is substantially complete and validated. The mission is currently blocked by orchestration/runtime instability, not by an unresolved parser-contract defect. The next real product step is to finish parser-authority threading through normalization and events, starting with a careful review of the current `src/rlcoach/normalize.py` modification.
