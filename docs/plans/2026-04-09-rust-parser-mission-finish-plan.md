# RLCoach Rust Parser Mission Finish Plan

**Goal:** Close the remaining parser mission work to true done by finishing the last authoritative-parser gaps, aligning downstream normalization/events/mechanics/reporting behavior with the shipped contract, extending corpus-health to measure the final contract, and proving the whole surface with the mission validation gates.

**Architecture:** Treat Milestone 1 (`parser-contract`) as largely complete, not as open-ended future work. From here, the work is a controlled closeout: patch the remaining contract leaks in the Rust bridge, make downstream Python consumption explicitly parser-first where authority exists, add report/Markdown/corpus coverage for the finished contract, then refresh docs/status artifacts so validation and shipped docs describe the same reality.

**Tech Stack:** Rust (`boxcars`, `pyo3`, `cargo`, `maturin`), Python (`pytest`, RLCoach CLI/report pipeline), JSON schema validation, local corpus-health harness.

---

## Current Verified State

The live codebase already has more of the parser mission landed than the handoff note alone implies:

- Parser-facing dataclasses already carry `match_guid`, `overtime`, `mutators`, and per-frame parser event lists in [`src/rlcoach/parser/types.py`](/Users/treygoff/Code/rlcoach/src/rlcoach/parser/types.py).
- The Rust adapter already maps enriched header metadata in [`src/rlcoach/parser/rust_adapter.py`](/Users/treygoff/Code/rlcoach/src/rlcoach/parser/rust_adapter.py).
- The Rust bridge already emits `parser_touch_events`, `parser_demo_events`, and `parser_kickoff_markers` in [`parsers/rlreplay_rust/src/lib.rs`](/Users/treygoff/Code/rlcoach/parsers/rlreplay_rust/src/lib.rs).
- Normalization already preserves parser event lists in [`src/rlcoach/normalize.py`](/Users/treygoff/Code/rlcoach/src/rlcoach/normalize.py).
- Event detectors already prefer parser touches/demos/kickoff markers in [`src/rlcoach/events/touches.py`](/Users/treygoff/Code/rlcoach/src/rlcoach/events/touches.py), [`src/rlcoach/events/demos.py`](/Users/treygoff/Code/rlcoach/src/rlcoach/events/demos.py), and [`src/rlcoach/events/kickoffs.py`](/Users/treygoff/Code/rlcoach/src/rlcoach/events/kickoffs.py).
- JSON report quality already includes `network_diagnostics` and `scorecard` in [`src/rlcoach/report.py`](/Users/treygoff/Code/rlcoach/src/rlcoach/report.py).
- `skim_count` and `psycho_count` are already surfaced in mechanics/report/schema.

That means the remaining work is not “implement the whole parser vision.” It is “finish the real gaps, remove cross-surface drift, and validate all remaining assertions.”

## Live Gaps That Still Need Closure

These are the meaningful remaining gaps visible in the current code:

1. The Rust bridge still emits parser component-state flags only when they are `true`; it does not emit explicit `false` values, so the advertised `True` / `False` / `None` semantics are not actually closed.
2. The Rust bridge still emits an empty `parser_tickmarks` list, so one parser event carrier named in the contract is not yet real.
3. Parser demo events currently carry victim-side authority, but attacker attribution still falls back downstream unless the Rust bridge is expanded.
4. Markdown rendering does not yet surface the full parser diagnostics/scorecard richness that JSON already carries, so `report-md` parity is still weaker than the mission contract.
5. Corpus-health measures reliability and scorecard coverage, but it does not yet report parser event/provenance coverage or explicit invalid-root/prerequisite behavior required by the mission validation contract.
6. Status/docs drift remains: [`codex/docs/master_status.md`](/Users/treygoff/Code/rlcoach/codex/docs/master_status.md) is stale, and some handoff language still points at `codex/docs/parser_adapter.md` while the live tested doc is [`docs/parser_adapter.md`](/Users/treygoff/Code/rlcoach/docs/parser_adapter.md).
7. The working tree is currently dirty in [`src/rlcoach/normalize.py`](/Users/treygoff/Code/rlcoach/src/rlcoach/normalize.py). Any implementation pass must integrate with that change carefully and must not clobber it.

## Delivery Rules

- All Python commands must use `source .venv/bin/activate && ...`.
- Do not overwrite or revert the existing user change in [`src/rlcoach/normalize.py`](/Users/treygoff/Code/rlcoach/src/rlcoach/normalize.py); integrate on top of it.
- Keep the integration branch as `feat/full-parser-analysis-vision`.
- Prefer sequential execution for parser chokepoints (`lib.rs`, parser types, normalize, events, report). Parallelize only doc/corpus/test refresh once the core contract is stable.
- Every task closes with targeted tests first, then broader gates.

---

### Task 1: Freeze The Remaining Delta Against The Live Code

**Parallel:** no
**Blocked by:** none
**Owned files:** `docs/plans/2026-04-09-rust-parser-mission-finish-plan.md`, `codex/docs/2026-04-09-rust-parser-mission-handoff.md`
**Invariants:** Do not change production code in this task. Do not reopen already-complete Milestone 1 work.
**Out of scope:** Any Rust/Python implementation changes.

**Files:**
- Create: `docs/plans/2026-04-09-rust-parser-mission-finish-plan.md`
- Read: `codex/docs/2026-04-09-rust-parser-mission-handoff.md`

**Step 1: Record the live completion baseline**
Capture which Milestone 1 capabilities are already landed in code and which assertions are still pending in `validation-state.json`.

**Step 2: Record the true remaining finish gaps**
List the seven gaps above explicitly so future execution does not redo parser-contract work that is already complete.

**Step 3: Record the dirty-tree constraint**
Note that [`src/rlcoach/normalize.py`](/Users/treygoff/Code/rlcoach/src/rlcoach/normalize.py) is already modified in the working tree and must be merged-forward, not reset.

**Verification plan:**
- Manual check that this plan distinguishes “already landed” from “remaining.”

---

### Task 2: Close The Remaining Rust Contract Leaks

**Parallel:** no
**Blocked by:** Task 1
**Owned files:** `parsers/rlreplay_rust/src/lib.rs`, `src/rlcoach/parser/rust_adapter.py`, `tests/test_rust_adapter.py`, `tests/parser/test_rust_adapter_smoke.py`, `tests/test_parser_interface.py`
**Invariants:** Keep degraded/unavailable behavior explicit. Preserve already-working touch emission and kickoff marker behavior.
**Out of scope:** Markdown/corpus/docs updates.

**Files:**
- Modify: `parsers/rlreplay_rust/src/lib.rs`
- Modify: `src/rlcoach/parser/rust_adapter.py`
- Modify: `tests/test_rust_adapter.py`
- Modify: `tests/parser/test_rust_adapter_smoke.py`
- Modify: `tests/test_parser_interface.py`

**Step 1: Write failing tests for the remaining parser contract leaks**
Add focused tests for:
- explicit `False` emission for `is_jumping`, `is_dodging`, `is_double_jumping`
- non-empty / meaningful `parser_tickmarks` when the replay contains timeline markers
- richer demo authority if attacker attribution is made available
- deterministic `attempted_backends` / diagnostics continuity across success and degraded paths

**Step 2: Implement the minimal Rust changes**
In [`parsers/rlreplay_rust/src/lib.rs`](/Users/treygoff/Code/rlcoach/parsers/rlreplay_rust/src/lib.rs):
- emit explicit boolean `false` values for component-state flags when parser authority exists and the state is inactive
- replace the always-empty `parser_tickmarks` placeholder with real parser-derived markers where `boxcars` exposes them
- if feasible, enrich parser demo events with attacker-side data rather than only victim-side data

**Step 3: Rebuild and run the parser-focused gate**
Run:
```bash
source .venv/bin/activate && cd parsers/rlreplay_rust && cargo test
source .venv/bin/activate && cd parsers/rlreplay_rust && maturin develop
source .venv/bin/activate && PYTHONPATH=src pytest -q tests/test_rust_adapter.py tests/parser/test_rust_adapter_smoke.py tests/test_parser_interface.py
```

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest -q tests/test_rust_adapter.py tests/parser/test_rust_adapter_smoke.py tests/test_parser_interface.py`
- Secondary check: `source .venv/bin/activate && PYTHONPATH=src python -m rlcoach.cli analyze testing_replay.replay --adapter rust --out /tmp/rlcoach-rust-contract --pretty`

---

### Task 3: Finish Downstream Parser-First Consumption

**Parallel:** no
**Blocked by:** Task 2
**Owned files:** `src/rlcoach/normalize.py`, `src/rlcoach/events/touches.py`, `src/rlcoach/events/demos.py`, `src/rlcoach/events/kickoffs.py`, `tests/test_normalize.py`, `tests/test_events.py`, `tests/test_events_calibration_synthetic.py`
**Invariants:** Preserve current fallback inference behavior when parser authority is missing. Do not duplicate parser and heuristic events.
**Out of scope:** Mechanics aggregation and Markdown rendering.

**Files:**
- Modify: `src/rlcoach/normalize.py`
- Modify: `src/rlcoach/events/touches.py`
- Modify: `src/rlcoach/events/demos.py`
- Modify: `src/rlcoach/events/kickoffs.py`
- Modify: `tests/test_normalize.py`
- Modify: `tests/test_events.py`
- Modify: `tests/test_events_calibration_synthetic.py`

**Step 1: Merge-forward the dirty normalize work**
Read the existing working-tree diff in [`src/rlcoach/normalize.py`](/Users/treygoff/Code/rlcoach/src/rlcoach/normalize.py) and integrate the new changes on top of it instead of reverting anything.

**Step 2: Thread the last parser authority paths**
Ensure downstream code:
- preserves explicit `False` component-state flags end-to-end
- consumes real `parser_tickmarks` where present
- uses richer parser demo data if Task 2 adds attacker attribution
- keeps parser-first, no-double-count semantics for touches/demos/kickoffs

**Step 3: Ratchet regression coverage**
Extend tests for:
- timestamp shifting on parser event lists
- parser-first event preference with no duplicate event counts
- repeated-run statelessness when authoritative events exist

**Step 4: Run focused downstream gates**
Run:
```bash
source .venv/bin/activate && PYTHONPATH=src pytest -q tests/test_normalize.py tests/test_events.py tests/test_events_calibration_synthetic.py
```

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest -q tests/test_normalize.py tests/test_events.py tests/test_events_calibration_synthetic.py`
- Secondary check: inspect `events.touches`, `events.demos`, and `events.kickoffs` in a real `analyze` output for parser `source` and no duplicate counts.

---

### Task 4: Close Mechanics Full-Vision Parity

**Parallel:** no
**Blocked by:** Task 3
**Owned files:** `src/rlcoach/analysis/mechanics.py`, `src/rlcoach/analysis/__init__.py`, `tests/test_analysis_mechanics_contract.py`, `tests/test_analysis_mechanics_advanced.py`, `tests/test_analysis_new_modules.py`
**Invariants:** Keep current mechanic keys stable in schema/report output. No arithmetic regressions in `total_mechanics` or team rollups.
**Out of scope:** Corpus/docs updates.

**Files:**
- Modify: `src/rlcoach/analysis/mechanics.py`
- Modify: `src/rlcoach/analysis/__init__.py`
- Modify: `tests/test_analysis_mechanics_contract.py`
- Modify: `tests/test_analysis_mechanics_advanced.py`
- Modify: `tests/test_analysis_new_modules.py`

**Step 1: Write failing parity tests**
Cover the handoff’s remaining mechanics expectations:
- parser-authoritative state is preferred when present
- jump/flip counts remain logically consistent
- team-level mechanics aggregation matches per-player totals
- advanced mechanic families stay surfaced even at zero counts

**Step 2: Refactor mechanics to authoritative-first where truth exists**
Use parser component-state truth and parser-auth events where available, while preserving heuristic fallback when the parser contract is nullable.

**Step 3: Run mechanics-focused gates**
Run:
```bash
source .venv/bin/activate && PYTHONPATH=src pytest -q tests/test_analysis_mechanics_contract.py tests/test_analysis_mechanics_advanced.py tests/test_analysis_new_modules.py
```

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest -q tests/test_analysis_mechanics_contract.py tests/test_analysis_mechanics_advanced.py tests/test_analysis_new_modules.py`
- Secondary check: inspect `analysis.per_team.*.mechanics` and `analysis.per_player.*.mechanics` in real output for arithmetic consistency.

---

### Task 5: Bring JSON And Markdown Report Surfaces Into Full Parity

**Parallel:** no
**Blocked by:** Task 4
**Owned files:** `src/rlcoach/report.py`, `src/rlcoach/report_markdown.py`, `tests/test_report_end_to_end.py`, `tests/test_report_markdown.py`, `tests/goldens/header_only.md`, `tests/goldens/synthetic_small.md`, `codex/docs/json-report-markdown-mapping.md`
**Invariants:** JSON schema validity must not regress. `report-md` must continue writing paired `.json` and `.md` artifacts atomically.
**Out of scope:** Corpus-health summary changes.

**Files:**
- Modify: `src/rlcoach/report.py`
- Modify: `src/rlcoach/report_markdown.py`
- Modify: `tests/test_report_end_to_end.py`
- Modify: `tests/test_report_markdown.py`
- Modify: `tests/goldens/header_only.md`
- Modify: `tests/goldens/synthetic_small.md`
- Modify: `codex/docs/json-report-markdown-mapping.md`

**Step 1: Write failing Markdown/report parity tests**
Add tests proving Markdown reflects:
- parser `network_diagnostics`
- parser `scorecard`
- degraded/unavailable parser context
- advanced mechanics coverage already present in JSON

**Step 2: Update Markdown composition**
Extend [`src/rlcoach/report_markdown.py`](/Users/treygoff/Code/rlcoach/src/rlcoach/report_markdown.py) so the dossier explicitly includes the parser-quality details the validation contract expects, not just adapter/header flags.

**Step 3: Refresh goldens and mapping docs**
Update the golden Markdown fixtures and the JSON-to-Markdown mapping so the Markdown surface is intentionally lossless relative to the report contract.

**Step 4: Run report-focused gates**
Run:
```bash
source .venv/bin/activate && PYTHONPATH=src pytest -q tests/test_report_end_to_end.py tests/test_report_markdown.py tests/test_schema_validation.py tests/test_schema_validation_hardening.py
source .venv/bin/activate && PYTHONPATH=src python -m rlcoach.cli report-md testing_replay.replay --adapter rust --out /tmp/rlcoach-report-md --pretty
```

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest -q tests/test_report_end_to_end.py tests/test_report_markdown.py tests/test_schema_validation.py tests/test_schema_validation_hardening.py`
- Secondary check: compare `/tmp/rlcoach-report-md/testing_replay.json` and `/tmp/rlcoach-report-md/testing_replay.md` for parser diagnostics/mechanics parity.

---

### Task 6: Extend Corpus-Health To Measure The Final Contract

**Parallel:** yes
**Blocked by:** Task 5
**Owned files:** `scripts/parser_corpus_health.py`, `tests/test_benchmarks.py`, `tests/parser/test_rust_adapter_smoke.py`
**Invariants:** Preserve the existing reliability metrics and summary shape; only extend it in a backward-compatible way.
**Out of scope:** README/status prose refresh.

**Files:**
- Modify: `scripts/parser_corpus_health.py`
- Modify: `tests/test_benchmarks.py`
- Modify: `tests/parser/test_rust_adapter_smoke.py`

**Step 1: Write failing corpus tests**
Add tests for:
- parser event/provenance coverage metrics
- explicit invalid-root / no-replays-found behavior
- consistency between scorecard-style metrics and corpus summary fields

**Step 2: Extend the script**
Teach [`scripts/parser_corpus_health.py`](/Users/treygoff/Code/rlcoach/scripts/parser_corpus_health.py) to measure:
- coverage of parser touch/demo/kickoff/tickmark emission
- prevalence of parser-vs-inferred provenance in emitted event surfaces where observable
- explicit discovery/prerequisite failures instead of silent empty success when roots are invalid

**Step 3: Capture and compare the real corpus summary**
Run:
```bash
source .venv/bin/activate && PYTHONPATH=src python scripts/parser_corpus_health.py --roots replays,Replay_files --json > /tmp/rlcoach-parser-corpus.json
```
Verify the extended summary still preserves at least the mission reliability floor (`network_success_rate >= 0.995`) unless the corpus itself has changed.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest -q tests/test_benchmarks.py tests/parser/test_rust_adapter_smoke.py`
- Secondary command: `source .venv/bin/activate && PYTHONPATH=src python scripts/parser_corpus_health.py --roots replays,Replay_files --json`

---

### Task 7: Refresh Docs And Status Artifacts To Match Shipped Reality

**Parallel:** yes
**Blocked by:** Tasks 5-6
**Owned files:** `docs/parser_adapter.md`, `docs/api.md`, `README.md`, `codex/docs/master_status.md`, `codex/docs/network-frames-integration-issue.md`, `tests/test_docs_parser_contract.py`
**Invariants:** Docs must describe current behavior, not wishlists. Keep `docs/parser_adapter.md` as the tested canonical contract path.
**Out of scope:** Code changes outside small doc-test adjustments.

**Files:**
- Modify: `docs/parser_adapter.md`
- Modify: `docs/api.md`
- Modify: `README.md`
- Modify: `codex/docs/master_status.md`
- Modify: `codex/docs/network-frames-integration-issue.md`
- Modify: `tests/test_docs_parser_contract.py`

**Step 1: Write failing doc tests where needed**
Tighten doc checks so they validate:
- the canonical parser doc path is `docs/parser_adapter.md`
- docs mention diagnostics-first behavior, scorecard/corpus gates, and parser event semantics as current behavior
- stale counts / status claims in README/master status are corrected

**Step 2: Refresh the prose**
Update all listed docs so they agree on:
- current parser posture
- current corpus reliability snapshot
- current validation commands
- what is shipped vs still intentionally out of scope

**Step 3: Run doc gates**
Run:
```bash
source .venv/bin/activate && PYTHONPATH=src pytest -q tests/test_docs_parser_contract.py
```

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest -q tests/test_docs_parser_contract.py`
- Secondary check: `rg -n "future work|stub|not implemented|553 tests|388 tests|261 tests" README.md docs codex/docs`

---

### Task 8: Execute The Mission Validation Matrix And Mark Assertions

**Parallel:** no
**Blocked by:** Tasks 6-7
**Owned files:** `~/.factory/missions/316e30d3-4db6-4f1d-aba2-07992a5608a9/validation-state.json`, `codex/logs/2026-04-09-rust-parser-mission-closeout.md`
**Invariants:** Do not mark an assertion passed without command evidence. Keep absolute dates and command outputs in the log.
**Out of scope:** New feature work.

**Files:**
- Modify: `~/.factory/missions/316e30d3-4db6-4f1d-aba2-07992a5608a9/validation-state.json`
- Create: `codex/logs/2026-04-09-rust-parser-mission-closeout.md`

**Step 1: Run the targeted parser-analysis lane**
Run:
```bash
source .venv/bin/activate && PYTHONPATH=src pytest -q \
  tests/test_rust_adapter.py \
  tests/parser/test_rust_adapter_smoke.py \
  tests/test_parser_interface.py \
  tests/test_normalize.py \
  tests/test_events.py \
  tests/test_events_calibration_synthetic.py \
  tests/test_analysis_mechanics_contract.py \
  tests/test_analysis_mechanics_advanced.py \
  tests/test_report_end_to_end.py \
  tests/test_report_markdown.py \
  tests/test_schema_validation.py \
  tests/test_schema_validation_hardening.py \
  tests/test_docs_parser_contract.py \
  tests/test_benchmarks.py
```

**Step 2: Run the full local quality gates**
Run:
```bash
source .venv/bin/activate && cd parsers/rlreplay_rust && cargo test
source .venv/bin/activate && cd parsers/rlreplay_rust && maturin develop
source .venv/bin/activate && PYTHONPATH=src pytest -q
source .venv/bin/activate && ruff check src/ tests/
source .venv/bin/activate && black --check src/ tests/
```

**Step 3: Run end-to-end CLI and corpus validation**
Run:
```bash
source .venv/bin/activate && PYTHONPATH=src python scripts/parser_corpus_health.py --roots replays,Replay_files --json
source .venv/bin/activate && PYTHONPATH=src python -m rlcoach.cli analyze testing_replay.replay --adapter rust --out /tmp/rlcoach-analyze-final --pretty
source .venv/bin/activate && PYTHONPATH=src python -m rlcoach.cli report-md testing_replay.replay --adapter rust --out /tmp/rlcoach-report-final --pretty
```

**Step 4: Update validation-state and log evidence**
Mark every satisfied `VAL-*` assertion in `validation-state.json` and record evidence in `codex/logs/2026-04-09-rust-parser-mission-closeout.md`.

**Verification plan:**
- Primary command set: all commands above
- Exit condition: no pending assertion remains without an explicit reason

---

## Recommended Execution Order

1. Task 1
2. Task 2
3. Task 3
4. Task 4
5. Task 5
6. Tasks 6 and 7 in parallel
7. Task 8

## Exit Criteria

The mission is only complete when all of the following are simultaneously true:

- Rust parser authority no longer leaks on tri-state flags and event carriers.
- Downstream normalization/events/mechanics are parser-first where truth exists and fallback-only where truth does not.
- `report-md` reflects the same parser diagnostics/provenance/mechanics contract as JSON.
- Corpus-health measures reliability plus final-contract event/provenance coverage.
- `docs/parser_adapter.md`, `README.md`, `docs/api.md`, and `codex/docs/master_status.md` all describe current behavior rather than future work.
- The remaining assertions in `validation-state.json` are updated from `pending` to `passed` based on real command evidence.
- Full local gates pass:
```bash
source .venv/bin/activate && cd parsers/rlreplay_rust && cargo test
source .venv/bin/activate && cd parsers/rlreplay_rust && maturin develop
source .venv/bin/activate && PYTHONPATH=src pytest -q
source .venv/bin/activate && ruff check src/ tests/
source .venv/bin/activate && black --check src/ tests/
source .venv/bin/activate && PYTHONPATH=src python scripts/parser_corpus_health.py --roots replays,Replay_files --json
source .venv/bin/activate && PYTHONPATH=src python -m rlcoach.cli analyze testing_replay.replay --adapter rust --out /tmp/rlcoach-analyze-final --pretty
source .venv/bin/activate && PYTHONPATH=src python -m rlcoach.cli report-md testing_replay.replay --adapter rust --out /tmp/rlcoach-report-final --pretty
```
