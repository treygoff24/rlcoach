# RLCoach Full Parser And Analysis Vision Implementation Plan

**Goal:** Take RLCoach from its current diagnostics-first Rust frame bridge plus broad downstream inference to a fully integrated parser/normalization/events/analysis/reporting pipeline that matches the repo's maximal planned vision, is thoroughly tested, and is safe to iterate on.

**Architecture:** Keep the existing `boxcars`-backed Rust parser as the primary backend, but expand it from a high-quality frame telemetry bridge into a richer authoritative data source for header metadata, component state, demo context, tickmarks, and parser provenance. Preserve the Python normalization/events/analysis stack, but shift it to authoritative-first consumption where parser truth exists and keep derivative inference as a documented fallback. Touch authority is a deliberate decision gate in this plan: if `boxcars` can support a robust parser-authored touch stream, use it; otherwise formalize calibrated inference with explicit provenance rather than pretending authority exists. Close the loop with schema/report alignment, corpus-health regression gates, and targeted mechanic/event tests so the broad feature surface becomes maintainable.

**Tech Stack:** Rust (`boxcars`, `pyo3`, `cargo`, `maturin`), Python (`pytest`, dataclasses), existing RLCoach parser/normalize/events/analysis/report/schema modules.

---

## Orchestration Model

- The main agent is the orchestrator/maestro for the entire rollout. It owns branch strategy, task dispatch, dependency enforcement, patient subagent waits, cross-lane integration, review routing, commit choreography, and final gate decisions.
- Every worker prompt must include the task number, owned files, blocked-by list, invariants, exact verification commands, and an explicit instruction not to edit files outside the task's owned-file set.
- Every review prompt must begin with: `Load the clean-code skill first, then review this task diff against docs/plans/2026-04-07-rlcoach-full-parser-analysis-implementation.md. Findings first. Flag correctness issues, regression risk, avoidable complexity, naming/abstraction problems, and missing tests.`
- No implementation task is complete until its targeted verification passes, its assigned review subagent has completed a clean-code-first review, any blocking findings are resolved, and the orchestrator records the task commit SHA in the execution log.

## Step 0: Set Up The Feature Branch And Worktree Scaffold

**Execution subagent:** `fast_worker`  
**Review subagent:** none  
**Commit checkpoint:** none; bootstrap only

**Purpose:** Create the integration branch that the main agent will orchestrate from, then predefine the worktree pattern for later parallel lanes.

**Commands:**
1. `git fetch --all --prune`
2. `git checkout main`
3. `git pull --ff-only`
4. `git checkout -b feat/full-parser-analysis-vision`
5. When parallel tasks begin, create one child worktree branch per task from `feat/full-parser-analysis-vision`. Prefer `.worktrees/` if it already exists; otherwise use the repo's documented worktree location and make sure the chosen directory is ignored before creating worktrees.
6. Create or append an orchestrator log entry in `codex/logs/` capturing task dispatches, review outcomes, commits, and integration notes for this rollout.

**Verification plan:**
- `git status --short --branch` shows `feat/full-parser-analysis-vision`
- `git branch --show-current` returns `feat/full-parser-analysis-vision`
- `git worktree list` is ready to reflect child worktrees once parallel lanes start

**Branch hygiene note:** If branch protection blocks direct completion to `main`, the main agent should finish through the normal PR merge/delete flow rather than forcing a direct push.

## Review And Commit Cadence

- Sequential lanes: Tasks 0-5, 8, 11, and 13 run one at a time on the integration branch.
- Parallel lanes: Tasks 6, 7, 9, 10, and 12 each get a dedicated worktree, a dedicated worker, a dedicated clean-code-first review, and their own commit before integration.
- After each task commit, the orchestrator updates the rollout log with the task number, worker used, reviewer used, verification commands run, and resulting commit SHA.
- Phase reviews are mandatory at the following boundaries: after Tasks 1-3, after Tasks 4-5, after integration of Tasks 6/7/9/10/12, after Tasks 11-12, and before closing Task 13. Those phase reviews should use `review_guard`, and `review_guard` must also load `clean-code` first.

## Scope Summary

- Rust parser header contract reaches the planned metadata breadth.
- Rust parser network contract exposes richer authoritative state and event streams.
- Python normalization/types/report layers can carry the richer parser contract without losing provenance.
- Events prefer parser authority when present and retain current inference fallback when absent.
- Mechanics become authoritative-first where feasible and report surfaces fully reflect implemented mechanics.
- Tests cover parser contracts, normalization, event preference behavior, advanced mechanics, schema stability, and corpus/perf gates.
- Docs describe the real parser contract, backend posture, diagnostics behavior, and execution gates.

## Non-Goals

- Replacing `boxcars` immediately with a second backend.
- Rewriting every analyzer from scratch.
- Shipping cloud services or non-local dependencies.
- Building UI work that is unrelated to parser/analysis correctness.

## Global Invariants

- Always use `source .venv/bin/activate && ...` for Python commands.
- Preserve header-only degradation behavior with explicit diagnostics.
- Keep `boxcars` as the default backend unless a later decision gate explicitly changes that.
- Never remove downstream inference until parser-authoritative coverage and tests are in place.
- Treat schema/report contract changes and parser changes as coupled work.

## Appendix A: Canonical Parser-Analysis Gap Matrix

| Subsystem | Planned capability | Authoritative source target | Fallback allowed? | Primary owned files |
| --- | --- | --- | --- | --- |
| Header metadata | Emit full header contract (`playlist_id`, `map_name`, `team_size`, `engine_build`, `match_guid`, `overtime`, `mutators`, goals/highlights, player metadata) | Rust `boxcars` header parse via adapter | Yes, header-only defaults + warnings when values unavailable | `parsers/rlreplay_rust/src/lib.rs`, `src/rlcoach/parser/rust_adapter.py`, `src/rlcoach/parser/types.py` |
| Parser diagnostics and provenance | Stable parser diagnostics (`status`, `error_code`, `error_detail`, `frames_emitted`, `attempted_backends`) and scorecard/report provenance | Rust parse diagnostics + Python report consolidation | Yes, degrade to explicit unavailable/degraded diagnostics (never silent) | `parsers/rlreplay_rust/src/lib.rs`, `src/rlcoach/parser/rust_adapter.py`, `src/rlcoach/report.py`, `scripts/parser_corpus_health.py` |
| Frame/player authority | Rich frame state including ball/player telemetry, boost pad events, and explicit component-state booleans (`True`/`False`/`None`) | Rust network parse -> normalized `Frame`/`PlayerFrame` | Yes, maintain inferred/default state when parser omits a field | `parsers/rlreplay_rust/src/lib.rs`, `src/rlcoach/normalize.py`, `src/rlcoach/parser/types.py` |
| Parser event streams | Parser-auth event carriers on frames (`parser_touch_events`, `parser_demo_events`, `parser_tickmarks`, `parser_kickoff_markers`) | Rust-emitted event lists where feasible | Yes, empty authoritative lists + inference pipeline when authority absent | `parsers/rlreplay_rust/src/lib.rs`, `src/rlcoach/parser/types.py`, `src/rlcoach/normalize.py` |
| Normalization and parser-facing types | Dataclass/type layer preserves parser payload without lossy envelopes; schema remains compatible | `src/rlcoach/parser/types.py` + normalization bridge | Yes, optional fields with backwards-compatible defaults | `src/rlcoach/parser/types.py`, `src/rlcoach/normalize.py`, `schemas/replay_report.schema.json` |
| Events preference model | Goals/demos/kickoffs/touches consume parser authority first and inference second, with deterministic ordering | Event detectors consume parser lists from normalized frames | Yes, existing inference remains canonical fallback | `src/rlcoach/events/touches.py`, `src/rlcoach/events/demos.py`, `src/rlcoach/events/goals.py`, `src/rlcoach/events/kickoffs.py`, `src/rlcoach/events/timeline.py` |
| Advanced mechanics detection | Mechanics surface includes all implemented advanced mechanics families and parser-authoritative hints where available | Mechanics analyzer over normalized authoritative state/events | Yes, heuristic path preserved for missing parser authority | `src/rlcoach/analysis/mechanics.py`, `src/rlcoach/analysis/__init__.py` |
| Report and schema parity | Report output and schema definitions stay aligned for mechanics/events/provenance (including `skim_count` + `psycho_count`) | `report.py` schema-valid output contract | No silent drift; either surfaced or intentionally removed and documented | `src/rlcoach/report.py`, `schemas/replay_report.schema.json`, `tests/test_schema_validation.py` |
| Corpus/perf gates | Corpus-health + benchmark/smoke gates reflect real contract and preserve/raise network parse success | Parser corpus script + smoke/benchmark tests | Yes, with explicit baseline capture and quantitative comparison | `scripts/parser_corpus_health.py`, `tests/test_benchmarks.py`, `tests/parser/test_rust_adapter_smoke.py` |
| Docs and status artifacts | Public docs describe real backend posture, authority/fallback semantics, and verification commands | Docs sourced from implemented code/tests | No stale claims; docs must match executable commands | `docs/parser_adapter.md`, `docs/api.md`, `README.md`, `codex/docs/master_status.md`, `codex/docs/network-frames-integration-issue-report.md` |

## Delivery Checkpoints And Priority Tiers

### Tier 1: Must-Ship Foundation

- Checkpoint A: canonical contract freeze, Rust header parity, explicit `True/False/None` component-state semantics, parser/report provenance hardening, and the concrete `skim_count` / `psycho_count` surfacing bug fixed.
- Estimated effort: medium. This is the smallest high-value subset that materially improves correctness even if no new parser event streams ship.

### Tier 2: Parser-Auth Events Where Feasible

- Checkpoint B: parser-auth demo and tickmark/kickoff event lanes with normalized provenance-safe consumption.
- Checkpoint C: touch authority only if the feasibility spike proves `boxcars` exposes enough signal; otherwise ship a formal inference-backed touch contract with provenance and calibration tests.
- Estimated effort: medium to large, depending on `boxcars` constraints.

### Tier 3: Full Vision Closure

- Checkpoint D: authoritative-first mechanics wiring, advanced-mechanics regression coverage, corpus/perf/doc closure, and full end-to-end gates.
- Estimated effort: large. This is the full maximal-vision endpoint.

### Task 0: Freeze The Vision Contract Into A Single Canonical Gap Matrix

**Parallel:** no  
**Implementation subagent:** `product_analyst`  
**Review subagent:** `plan_checker` (must load `clean-code` first)  
**Commit checkpoint:** `docs(plan): freeze parser-analysis gap matrix`  
**Blocked by:** none  
**Owned files:** `docs/plans/2026-04-07-rlcoach-full-parser-analysis-implementation.md`, `MECHANICS_SPEC.md`, `MECHANICS_DETECTION.md`, `MECHANICS_IMPLEMENTATION_PLAN_v2.md`, `codex/Plans/2026-02-10-parser-refactor-update-plan.md`, `codex/Plans/rlcoach_implementation_plan.md`, `codex/Plans/missing-mechanics.md`  
**Invariants:** Do not change code; only consolidate the intended target state before implementation starts.  
**Out of scope:** Rewriting historical planning docs.

**Files:**
- Modify: `docs/plans/2026-04-07-rlcoach-full-parser-analysis-implementation.md`
- Read: `MECHANICS_SPEC.md`
- Read: `MECHANICS_DETECTION.md`
- Read: `MECHANICS_IMPLEMENTATION_PLAN_v2.md`
- Read: `codex/Plans/2026-02-10-parser-refactor-update-plan.md`
- Read: `codex/Plans/rlcoach_implementation_plan.md`
- Read: `codex/Plans/missing-mechanics.md`

**Step 1: Record the target contract in the plan**
Add a short appendix table with these columns:
- `Subsystem`
- `Planned capability`
- `Authoritative source target`
- `Fallback allowed?`
- `Primary owned files`

**Step 2: Validate the plan covers all major subsystems**
Required rows:
- header metadata
- parser diagnostics/provenance
- frame/player authority
- parser event streams
- normalization/types
- events preference model
- advanced mechanics detection
- report/schema parity
- corpus/perf gates
- docs/status artifacts

**Step 3: Re-read the table and verify nothing major is omitted**
Checklist:
- header breadth
- touch/demo/tickmark capture
- component-state semantics
- boost pad authority
- all advanced mechanics and report surfaces

**Verification plan:**
- Manual check: every major capability from the vision docs appears in the appendix table.

---

### Task 1: Lock The Target Parser Contract In Types And Schema

**Parallel:** no  
**Implementation subagent:** `heavy_worker`  
**Review subagent:** `reviewer` (must load `clean-code` first)  
**Commit checkpoint:** `feat(parser): lock richer parser contract in types and schema`  
**Blocked by:** Task 0  
**Owned files:** `src/rlcoach/parser/types.py`, `schemas/replay_report.schema.json`, `tests/test_parser_interface.py`, `tests/test_schema_validation.py`, `tests/test_schema_validation_hardening.py`  
**Invariants:** Backward compatibility remains possible through optional fields; existing reports should still validate unless intentionally tightened with matching tests.  
**Out of scope:** Rust parser emission details; this task defines the contract only.

**Files:**
- Modify: `src/rlcoach/parser/types.py`
- Modify: `schemas/replay_report.schema.json`
- Modify: `tests/test_parser_interface.py`
- Modify: `tests/test_schema_validation.py`
- Modify: `tests/test_schema_validation_hardening.py`

**Step 1: Write failing contract tests for the richer parser payload**
Add tests for:
- richer header coverage carried end-to-end from adapter output into the existing `Header` dataclass (`match_guid`, `overtime`, `mutators`)
- richer player authority fields (explicit optional booleans or new parser-state fields)
- explicit parser event payload containers on `Frame`:
  - `parser_touch_events: list[ParserTouchEvent]`
  - `parser_demo_events: list[ParserDemoEvent]`
  - `parser_tickmarks: list[ParserTickmarkEvent]`
  - `parser_kickoff_markers: list[ParserKickoffMarker]`
- report/schema support for all surfaced mechanics, including `skim_count` and `psycho_count`

```python
def test_network_frame_contract_supports_explicit_parser_event_lists():
    from rlcoach.parser.types import Frame
    fields = getattr(Frame, "__dataclass_fields__", {})
    assert "boost_pad_events" in fields
    assert "parser_touch_events" in fields
    assert "parser_demo_events" in fields
    assert "parser_tickmarks" in fields
    assert "parser_kickoff_markers" in fields
```

**Step 2: Run the targeted tests to confirm failure**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_parser_interface.py tests/test_schema_validation.py tests/test_schema_validation_hardening.py -q`  
Expected: FAIL on missing fields / missing schema properties.

**Step 3: Add the minimal type/schema scaffolding**
Implement:
- new parser event dataclasses in `types.py` with explicit, non-envelope shapes:
  - `ParserTouchEvent(timestamp, player_id, team, frame_index=None, source="parser")`
  - `ParserDemoEvent(timestamp, victim_id, attacker_id=None, victim_team=None, attacker_team=None, frame_index=None, source="parser")`
  - `ParserTickmarkEvent(timestamp, kind, frame_index=None, payload=None, source="parser")`
  - `ParserKickoffMarker(timestamp, phase, frame_index=None, source="parser")`
- optional `Frame` fields required to carry authoritative parser event/state data
- schema additions for all new report fields

**Step 4: Run the targeted tests to confirm pass**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_parser_interface.py tests/test_schema_validation.py tests/test_schema_validation_hardening.py -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_parser_interface.py tests/test_schema_validation.py tests/test_schema_validation_hardening.py -q`
- Secondary check: schema remains loadable by current report tests.

---

### Task 2: Expand Rust Header Extraction To Match The Broader Metadata Vision

**Parallel:** no  
**Implementation subagent:** `heavy_worker`  
**Review subagent:** `reviewer` (must load `clean-code` first)  
**Commit checkpoint:** `feat(parser): expand rust header metadata extraction`  
**Blocked by:** Task 1  
**Owned files:** `parsers/rlreplay_rust/src/lib.rs`, `src/rlcoach/parser/rust_adapter.py`, `tests/test_rust_adapter.py`, `tests/test_parser_interface.py`  
**Invariants:** Header parsing must remain header-only safe and degrade with explicit warnings rather than crashing.  
**Out of scope:** Network frame/event parsing.

**Files:**
- Modify: `parsers/rlreplay_rust/src/lib.rs`
- Modify: `src/rlcoach/parser/rust_adapter.py`
- Modify: `tests/test_rust_adapter.py`
- Modify: `tests/test_parser_interface.py`

**Step 1: Write failing tests for enriched header fields**
Cover:
- `engine_build`
- `match_guid`
- `overtime`
- `mutators`
- player metadata extraction continuity
- explicit end-to-end population from Rust output into the already-existing Python `Header` fields

```python
def test_rust_header_exposes_match_guid_overtime_and_mutators():
    header = get_adapter("rust").parse_header(Path("testing_replay.replay"))
    assert hasattr(header, "match_guid")
    assert hasattr(header, "overtime")
    assert isinstance(header.mutators, dict)
```

**Step 2: Run the targeted tests to confirm failure**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_rust_adapter.py tests/test_parser_interface.py -q`  
Expected: FAIL on missing or default-only metadata.

**Step 3: Extend `parse_header` and adapter conversion**
Implement Rust-side extraction for the additional header properties where present and adapt them into the existing `Header` dataclass. Do not treat this task as a Python type-definition lane; the gap is Rust-side emission plus adapter population.

**Step 4: Re-run tests to confirm pass**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_rust_adapter.py tests/test_parser_interface.py -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_rust_adapter.py tests/test_parser_interface.py -q`
- Secondary check: `source .venv/bin/activate && PYTHONPATH=src python -m rlcoach.cli analyze testing_replay.replay --adapter rust --out out`

---

### Task 3: Make Parser Component-State Authority Fully Explicit

**Parallel:** no  
**Implementation subagent:** `heavy_worker`  
**Review subagent:** `reviewer` (must load `clean-code` first)  
**Commit checkpoint:** `fix(normalize): preserve explicit parser component-state semantics`  
**Blocked by:** Tasks 1, 2  
**Owned files:** `parsers/rlreplay_rust/src/lib.rs`, `src/rlcoach/parser/types.py`, `src/rlcoach/normalize.py`, `tests/test_normalize.py`, `tests/test_analysis_new_modules.py`, `tests/test_rust_adapter.py`  
**Invariants:** `None` must continue to mean unavailable; explicit false must mean observed inactive state.  
**Out of scope:** Touch/demo/tickmark event streams.

**Files:**
- Modify: `parsers/rlreplay_rust/src/lib.rs`
- Modify: `src/rlcoach/parser/types.py`
- Modify: `src/rlcoach/normalize.py`
- Modify: `tests/test_normalize.py`
- Modify: `tests/test_analysis_new_modules.py`
- Modify: `tests/test_rust_adapter.py`

**Step 1: Write failing tests for `True/False/None` semantics**

```python
def test_normalize_preserves_explicit_false_component_flags():
    raw = [{
        "timestamp": 0.0,
        "ball": {"position": {}, "velocity": {}, "angular_velocity": {}},
        "players": [{
            "player_id": "player_0",
            "team": 0,
            "position": {"x": 0, "y": 0, "z": 17},
            "velocity": {"x": 0, "y": 0, "z": 0},
            "rotation": {"pitch": 0, "yaw": 0, "roll": 0},
            "boost_amount": 33,
            "is_jumping": False,
            "is_dodging": False,
            "is_double_jumping": False,
        }],
    }]
    frames = build_timeline(Header(players=[]), raw)
    assert frames[0].players[0].is_jumping is False
```

**Step 2: Run the targeted tests to confirm failure**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_normalize.py tests/test_analysis_new_modules.py tests/test_rust_adapter.py -q`  
Expected: FAIL because the bridge only emits `true`/`None`.

**Step 3: Update Rust emission and Python normalization**
Emit explicit false when the parser observed an inactive component state, and preserve it through `normalize.py`.

**Step 4: Re-run the targeted tests**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_normalize.py tests/test_analysis_new_modules.py tests/test_rust_adapter.py -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_normalize.py tests/test_analysis_new_modules.py tests/test_rust_adapter.py -q`
- Secondary check: inspect a sample raw frame dump to confirm inactive states are explicit booleans, not missing.

---

### Task 4: Decide And Implement The Touch Authority Path

**Parallel:** no  
**Implementation subagent:** `heavy_worker`  
**Review subagent:** `reviewer` (must load `clean-code` first)  
**Commit checkpoint:** Branch A `feat(events): add parser-auth touch authority`; Branch B `feat(events): formalize inferred touch provenance`  
**Blocked by:** Tasks 1, 3  
**Owned files:** `parsers/rlreplay_rust/src/lib.rs`, `src/rlcoach/parser/types.py`, `src/rlcoach/normalize.py`, `src/rlcoach/events/touches.py`, `tests/test_parser_interface.py`, `tests/test_normalize.py`, `tests/test_events.py`, `tests/test_events_calibration_synthetic.py`  
**Invariants:** Existing touch inference remains available as fallback when the parser does not emit touch events or when the feasibility spike proves parser-native touch authority is not robustly available.  
**Out of scope:** Demo and tickmark event streams.

**Files:**
- Modify: `parsers/rlreplay_rust/src/lib.rs`
- Modify: `src/rlcoach/parser/types.py`
- Modify: `src/rlcoach/normalize.py`
- Modify: `src/rlcoach/events/touches.py`
- Modify: `tests/test_parser_interface.py`
- Modify: `tests/test_normalize.py`
- Modify: `tests/test_events.py`
- Modify: `tests/test_events_calibration_synthetic.py`

**Step 1: Write failing contract and preference tests**
Add tests proving:
- parser frames can carry `parser_touch_events`
- normalized frames preserve them
- `detect_touches` prefers parser-auth touches when present
- fallback inference still produces touches with explicit provenance when parser touch events are absent

**Step 2: Run the targeted tests and a feasibility spike**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_parser_interface.py tests/test_normalize.py tests/test_events.py tests/test_events_calibration_synthetic.py -q`  
Expected: FAIL on missing parser touch structures and preference behavior.  
Then inspect `boxcars` support in `parsers/rlreplay_rust/src/lib.rs` and upstream docs/code to answer one question explicitly in the plan/task notes:
- Can Rust emit a robust touch event directly from replay data, or must touches remain inferred from frame telemetry?

**Step 3: Implement one of two explicit branches**
Branch A, if feasibility is confirmed:
- define `ParserTouchEvent`
- emit parser touch events from Rust
- normalize them
- make `detect_touches` authoritative-first with calibrated fallback inference

Branch B, if feasibility is not confirmed:
- keep the contract field available but allow it to be empty
- formalize `detect_touches` as the canonical touch layer
- add provenance on inferred touches so downstream consumers know touch authority is heuristic, not parser-native
- document that touch authority is intentionally inference-backed on current `boxcars`

**Step 4: Re-run tests to confirm pass**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_parser_interface.py tests/test_normalize.py tests/test_events.py tests/test_events_calibration_synthetic.py -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_parser_interface.py tests/test_normalize.py tests/test_events.py tests/test_events_calibration_synthetic.py -q`
- Secondary check: `source .venv/bin/activate && PYTHONPATH=src python -m rlcoach.cli analyze testing_replay.replay --adapter rust --out out`
- Decision gate: the task is only considered parser-auth complete if a direct touch stream is proven feasible; otherwise Branch B is the expected ship path.

---

### Task 5: Add Parser-Authoritative Demo And Tickmark/Event Streams

**Parallel:** no  
**Implementation subagent:** `heavy_worker`  
**Review subagent:** `reviewer` (must load `clean-code` first)  
**Commit checkpoint:** `feat(events): prefer parser demos and kickoff markers`  
**Blocked by:** Tasks 1, 3  
**Owned files:** `parsers/rlreplay_rust/src/lib.rs`, `src/rlcoach/parser/types.py`, `src/rlcoach/normalize.py`, `src/rlcoach/events/demos.py`, `src/rlcoach/events/goals.py`, `src/rlcoach/events/kickoffs.py`, `tests/test_parser_interface.py`, `tests/test_normalize.py`, `tests/test_events.py`  
**Invariants:** Current state-transition demo inference and kickoff/goal fallback behavior must remain available until parser authority proves stable.  
**Out of scope:** Mechanics implementation itself.

**Files:**
- Modify: `parsers/rlreplay_rust/src/lib.rs`
- Modify: `src/rlcoach/parser/types.py`
- Modify: `src/rlcoach/normalize.py`
- Modify: `src/rlcoach/events/demos.py`
- Modify: `src/rlcoach/events/goals.py`
- Modify: `src/rlcoach/events/kickoffs.py`
- Modify: `tests/test_parser_interface.py`
- Modify: `tests/test_normalize.py`
- Modify: `tests/test_events.py`

**Step 1: Write failing tests for parser-event preference**
Cover:
- parser demo events preferred over proximity-based attacker inference
- parser tickmark/kickoff markers consumed when present
- current inference preserved when parser events absent

**Step 2: Run the targeted tests to confirm failure**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_parser_interface.py tests/test_normalize.py tests/test_events.py -q`  
Expected: FAIL on missing parser event carriers and preference behavior.

**Step 3: Implement the minimal authoritative event path**
Emit explicit parser demo/tickmark/kickoff event lists, normalize them, and update events modules to use them first. Do not introduce an opaque `parser_events` envelope.

**Step 4: Re-run the targeted tests**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_parser_interface.py tests/test_normalize.py tests/test_events.py -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_parser_interface.py tests/test_normalize.py tests/test_events.py -q`
- Secondary check: inspect generated JSON `events.demos`, `events.goals`, and `events.kickoffs` for parser provenance behavior.

---

### Task 6: Finish Parser Authority For Boost, Player Identity, And Provenance

**Parallel:** yes  
**Implementation subagent:** `worker`  
**Review subagent:** `reviewer` (must load `clean-code` first)  
**Commit checkpoint:** `fix(report): harden parser provenance and identity coverage`  
**Blocked by:** Tasks 2, 3  
**Owned files:** `parsers/rlreplay_rust/src/lib.rs`, `src/rlcoach/parser/rust_adapter.py`, `src/rlcoach/report.py`, `tests/test_rust_adapter.py`, `tests/test_parser_interface.py`, `tests/test_report_end_to_end.py`  
**Invariants:** Existing scorecard/diagnostics fields remain present and machine-readable.  
**Out of scope:** New mechanics algorithms.

**Files:**
- Modify: `parsers/rlreplay_rust/src/lib.rs`
- Modify: `src/rlcoach/parser/rust_adapter.py`
- Modify: `src/rlcoach/report.py`
- Modify: `tests/test_rust_adapter.py`
- Modify: `tests/test_parser_interface.py`
- Modify: `tests/test_report_end_to_end.py`

**Step 1: Write failing tests for provenance completeness**
Cover:
- report quality includes parser diagnostics + attempted backends + scorecard
- player identity coverage remains stable
- parser meta remains deterministic on degraded and successful parses

**Step 2: Run the targeted tests to confirm failure**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_rust_adapter.py tests/test_parser_interface.py tests/test_report_end_to_end.py -q`  
Expected: FAIL on missing/partial provenance assertions.

**Step 3: Implement the minimal provenance hardening**
Normalize provenance/report fields and preserve current diagnostics-first posture.

**Step 4: Re-run the targeted tests**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_rust_adapter.py tests/test_parser_interface.py tests/test_report_end_to_end.py -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_rust_adapter.py tests/test_parser_interface.py tests/test_report_end_to_end.py -q`
- Secondary check: `source .venv/bin/activate && PYTHONPATH=src python scripts/parser_corpus_health.py --roots replays,Replay_files --json`

---

### Task 7: Fix Concrete Mechanics Surfacing Bugs And Align Output With The Implemented Mechanics Surface

**Parallel:** yes  
**Implementation subagent:** `worker`  
**Review subagent:** `reviewer` (must load `clean-code` first)  
**Commit checkpoint:** `fix(mechanics): surface skim and psycho counts`  
**Blocked by:** Tasks 1, 3  
**Owned files:** `src/rlcoach/analysis/mechanics.py`, `src/rlcoach/analysis/__init__.py`, `schemas/replay_report.schema.json`, `tests/test_analysis_mechanics_contract.py`, `tests/api/test_analysis.py`, `tests/test_schema_validation.py`  
**Invariants:** Existing mechanic counts must not regress silently; report/schema must match implementation exactly.  
**Out of scope:** Rust parser event emission.

**Files:**
- Modify: `src/rlcoach/analysis/mechanics.py`
- Modify: `src/rlcoach/analysis/__init__.py`
- Modify: `schemas/replay_report.schema.json`
- Create: `tests/test_analysis_mechanics_contract.py`
- Modify: `tests/api/test_analysis.py`
- Modify: `tests/test_schema_validation.py`

**Step 1: Write failing tests for output/report parity**
Cover:
- the concrete bug where `SKIM` and `PSYCHO` events are generated but `skim_count` and `psycho_count` are not surfaced in per-player output is fixed
- team mechanics include all intended advanced metrics or deliberately scoped subset with explicit schema/docs alignment
- totals stay consistent with event emission

**Step 2: Run the targeted tests to confirm failure**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_analysis_mechanics_contract.py tests/api/test_analysis.py tests/test_schema_validation.py -q`  
Expected: FAIL because report/schema and rollup are out of sync.

**Step 3: Implement the minimal parity fixes**
First fix the concrete `skim_count` / `psycho_count` rollup bug. Then update mechanics aggregation and schema/report consumers so every implemented mechanic is either surfaced or intentionally removed from schema.

**Step 4: Re-run the targeted tests**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_analysis_mechanics_contract.py tests/api/test_analysis.py tests/test_schema_validation.py -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_analysis_mechanics_contract.py tests/api/test_analysis.py tests/test_schema_validation.py -q`
- Secondary check: generated replay JSON shows the same mechanic families that the analyzer can emit as events.

---

### Task 8: Split Mechanics Into Authoritative-First And Fallback-Heuristic Paths

**Parallel:** no  
**Implementation subagent:** `heavy_worker`  
**Review subagent:** `reviewer` (must load `clean-code` first)  
**Commit checkpoint:** `refactor(mechanics): split authoritative and fallback paths`  
**Blocked by:** Tasks 4, 5, 7  
**Owned files:** `src/rlcoach/analysis/mechanics.py`, `src/rlcoach/parser/types.py`, `tests/test_analysis_new_modules.py`, `tests/test_parser_interface.py`  
**Invariants:** The analyzer must continue to work on older/header-degraded replays with fallback inference.  
**Out of scope:** Non-mechanics analyzers.

**Files:**
- Modify: `src/rlcoach/analysis/mechanics.py`
- Modify: `src/rlcoach/parser/types.py`
- Modify: `tests/test_analysis_new_modules.py`
- Modify: `tests/test_parser_interface.py`

**Step 1: Write failing preference tests**
Cover:
- fast aerial/flip reset/ceiling-touch-related logic prefer parser truth when present
- heuristics still fire when parser authority missing
- mixed-authority replays do not double-count
- touch-dependent mechanics behave correctly under whichever Task 4 branch shipped

**Step 2: Run the targeted tests to confirm failure**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_analysis_new_modules.py tests/test_parser_interface.py -q`  
Expected: FAIL on preference / double-count safeguards.

**Step 3: Refactor mechanics to authoritative-first**
Introduce helper paths for:
- parser-authoritative event consumption
- parser-authoritative state consumption
- heuristic fallback only when parser truth absent
- touch-dependent fallback logic that honors the Task 4 feasibility outcome without claiming false parser authority

**Step 4: Re-run the targeted tests**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_analysis_new_modules.py tests/test_parser_interface.py -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_analysis_new_modules.py tests/test_parser_interface.py -q`
- Secondary check: no duplicate mechanics when both parser events and heuristics describe the same play.

---

### Task 9: Build Dedicated Advanced Mechanics Regression Coverage

**Parallel:** yes  
**Implementation subagent:** `test_hardener`  
**Review subagent:** `reviewer` (must load `clean-code` first)  
**Commit checkpoint:** `test(mechanics): add advanced mechanics regression coverage`  
**Blocked by:** Tasks 7, 8  
**Owned files:** `tests/test_analysis_mechanics_advanced.py`, `tests/fixtures/builders.py`, `tests/goldens/synthetic_small.md`  
**Invariants:** Each advanced mechanic gets at least one positive test and one negative or anti-false-positive test.  
**Out of scope:** Parser header/event contracts.

**Files:**
- Create: `tests/test_analysis_mechanics_advanced.py`
- Modify: `tests/fixtures/builders.py`
- Modify: `tests/goldens/synthetic_small.md`

**Step 1: Write failing advanced-mechanics tests**
Add explicit tests for:
- fast aerial
- flip reset
- air roll
- dribble
- flick
- musty flick
- ceiling shot
- power slide
- ground pinch
- double touch
- redirect
- stall
- skim
- psycho

**Step 2: Run the targeted tests to confirm current gaps**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_analysis_mechanics_advanced.py -q`  
Expected: FAIL for missing coverage or mismatched outputs.

**Step 3: Add the minimal fixture-builder helpers and assertions**
Keep fixtures synthetic and deterministic.

**Step 4: Re-run the targeted tests**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_analysis_mechanics_advanced.py -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_analysis_mechanics_advanced.py -q`
- Secondary checks: no regression in existing mechanics counts.

---

### Task 10: Build Authoritative Event Preference Tests Across The Whole Event Layer

**Parallel:** yes  
**Implementation subagent:** `test_hardener`  
**Review subagent:** `reviewer` (must load `clean-code` first)  
**Commit checkpoint:** `test(events): cover authoritative event preference`  
**Blocked by:** Tasks 4, 5  
**Owned files:** `tests/test_events.py`, `tests/test_events_calibration_synthetic.py`, `src/rlcoach/events/timeline.py`, `src/rlcoach/events/__init__.py`  
**Invariants:** Timeline assembly stays chronological and deterministic.  
**Out of scope:** Mechanics rollups.

**Files:**
- Modify: `tests/test_events.py`
- Modify: `tests/test_events_calibration_synthetic.py`
- Modify: `src/rlcoach/events/timeline.py`
- Modify: `src/rlcoach/events/__init__.py`

**Step 1: Write failing end-to-end event preference tests**
Cover:
- parser touch events used first when Task 4 Branch A ships
- parser demo events used first
- parser kickoff/tickmark markers used first
- fallback inference still works when parser authority absent

**Step 2: Run the targeted tests to confirm failure**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_events.py tests/test_events_calibration_synthetic.py -q`  
Expected: FAIL on missing preference behavior.

**Step 3: Make timeline assembly provenance-safe**
Update event wiring only as needed to keep timeline deterministic.

**Step 4: Re-run the targeted tests**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_events.py tests/test_events_calibration_synthetic.py -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_events.py tests/test_events_calibration_synthetic.py -q`
- Secondary check: `events.timeline` remains non-empty and chronologically sorted on sample replays.

---

### Task 11: Reinforce Corpus-Health, Perf, And Real-Replay Gates

**Parallel:** no  
**Implementation subagent:** `performance_engineer`  
**Review subagent:** `review_guard` (must load `clean-code` first)  
**Commit checkpoint:** `chore(gates): refresh corpus health and parser smoke expectations`  
**Blocked by:** Tasks 4, 5, 6, 8, 9, 10  
**Owned files:** `scripts/parser_corpus_health.py`, `tests/test_benchmarks.py`, `tests/parser/test_rust_adapter_smoke.py`, `codex/docs/master_status.md`, `codex/docs/network-frames-integration-issue-report.md`  
**Invariants:** Corpus/perf gates must measure the real parser contract, not stale expectations.  
**Out of scope:** New feature development.

**Files:**
- Modify: `scripts/parser_corpus_health.py`
- Modify: `tests/test_benchmarks.py`
- Modify: `tests/parser/test_rust_adapter_smoke.py`
- Modify: `codex/docs/master_status.md`
- Modify: `codex/docs/network-frames-integration-issue-report.md`

**Step 1: Write failing gate tests and smoke expectations**
Cover:
- parser scorecard reflects the richer contract
- smoke tests assert richer fields/events where expected
- benchmark expectations remain explicit
- capture the pre-change corpus-health network success rate so the post-change quantitative gate has a real baseline

**Step 2: Run the targeted tests to confirm failure**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_benchmarks.py tests/parser/test_rust_adapter_smoke.py -q`  
Expected: FAIL on stale assumptions.  
Also run and save the current baseline before changing expectations:  
`source .venv/bin/activate && PYTHONPATH=src python scripts/parser_corpus_health.py --roots replays,Replay_files --json > /tmp/rlcoach-parser-corpus-baseline.json`

**Step 3: Update harnesses and docs**
Refresh:
- scorecard fields
- corpus-health summaries
- master status docs

**Step 4: Re-run the targeted tests and harness**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_benchmarks.py tests/parser/test_rust_adapter_smoke.py -q`  
Expected: PASS.  
Run: `source .venv/bin/activate && PYTHONPATH=src python scripts/parser_corpus_health.py --roots replays,Replay_files --json`  
Expected: valid JSON report with current diagnostics and success metrics.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_benchmarks.py tests/parser/test_rust_adapter_smoke.py -q`
- Secondary command: `source .venv/bin/activate && PYTHONPATH=src python scripts/parser_corpus_health.py --roots replays,Replay_files --json`

---

### Task 12: Restore Parser Documentation To Match Reality

**Parallel:** yes  
**Implementation subagent:** `docs_editor`  
**Review subagent:** `reviewer` (must load `clean-code` first)  
**Commit checkpoint:** `docs(parser): restore parser contract documentation`  
**Blocked by:** Tasks 2, 4, 5, 6, 11  
**Owned files:** `docs/parser_adapter.md`, `docs/api.md`, `README.md`, `tests/test_docs_parser_contract.py`  
**Invariants:** Docs must describe the real contract, fallback semantics, build commands, and verification flow.  
**Out of scope:** New feature code.

**Files:**
- Create: `docs/parser_adapter.md`
- Modify: `docs/api.md`
- Modify: `README.md`
- Create: `tests/test_docs_parser_contract.py`

**Step 1: Write failing docs assertions as an automated docs test**
Cover:
- build instructions exist
- parser contract documented
- diagnostics/fallback policy documented
- event authority/fallback policy documented, including the Task 4 touch-feasibility outcome
- sample commands are correct for the repo

**Step 2: Draft the docs**
Required sections in `docs/parser_adapter.md`:
- build and dev workflow
- current backend posture
- header contract
- network frame contract
- parser event streams
- diagnostics and degradation semantics
- test and corpus-health commands

**Step 3: Review the docs against the live commands**
Commands to include:
- `source .venv/bin/activate && PYTHONPATH=src pytest -q`
- `source .venv/bin/activate && cd parsers/rlreplay_rust && cargo test`
- `source .venv/bin/activate && cd parsers/rlreplay_rust && maturin develop`

**Step 4: Confirm the docs align with the implemented contract**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_docs_parser_contract.py -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_docs_parser_contract.py -q`
- Secondary check: manual diff review against the final parser/types/report contracts.

---

### Task 13: Run The Full Parser/Analysis Closure Gate

**Parallel:** no  
**Implementation subagent:** `review_guard`  
**Review subagent:** `review_guard` (must load `clean-code` first)  
**Commit checkpoint:** none unless the gate uncovers blocking regressions; if fixes are required, hand them back to the owning implementation subagent and commit them with a task-specific Conventional Commit before rerunning the gate  
**Blocked by:** Tasks 6, 7, 8, 9, 10, 11, 12  
**Owned files:** `parsers/rlreplay_rust/src/lib.rs`, `src/rlcoach/parser/types.py`, `src/rlcoach/parser/rust_adapter.py`, `src/rlcoach/normalize.py`, `src/rlcoach/events/__init__.py`, `src/rlcoach/analysis/__init__.py`, `src/rlcoach/analysis/mechanics.py`, `src/rlcoach/report.py`, `schemas/replay_report.schema.json`, `tests/...`, `docs/...`  
**Invariants:** This is verification only unless a blocking regression is found.  
**Out of scope:** New feature work after the gate starts.

**Files:**
- Verify: `parsers/rlreplay_rust/src/lib.rs`
- Verify: `src/rlcoach/parser/types.py`
- Verify: `src/rlcoach/parser/rust_adapter.py`
- Verify: `src/rlcoach/normalize.py`
- Verify: `src/rlcoach/events/...`
- Verify: `src/rlcoach/analysis/...`
- Verify: `src/rlcoach/report.py`
- Verify: `schemas/replay_report.schema.json`
- Verify: `tests/...`
- Verify: `docs/...`

**Step 1: Run focused parser + analysis tests**
Run:
```bash
source .venv/bin/activate && PYTHONPATH=src pytest \
  tests/test_rust_adapter.py \
  tests/parser/test_rust_adapter_smoke.py \
  tests/test_parser_interface.py \
  tests/test_normalize.py \
  tests/test_events.py \
  tests/test_events_calibration_synthetic.py \
  tests/test_analysis_mechanics_contract.py \
  tests/test_analysis_new_modules.py \
  tests/test_analysis_mechanics_advanced.py \
  tests/test_schema_validation.py \
  tests/test_schema_validation_hardening.py \
  tests/test_docs_parser_contract.py \
  tests/test_benchmarks.py -q
```
Expected: PASS.

**Step 2: Run the broader repo gate**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest -q`  
Expected: PASS.

**Step 3: Run Rust crate tests**
Run: `cd /Users/treygoff/Code/rlcoach/parsers/rlreplay_rust && cargo test`  
Expected: PASS.

**Step 4: Build the extension locally**
Run: `source /Users/treygoff/Code/rlcoach/.venv/bin/activate && cd /Users/treygoff/Code/rlcoach/parsers/rlreplay_rust && maturin develop`  
Expected: PASS.

**Step 4.5: Run a local import/build smoke check on the built extension**
Run: `source /Users/treygoff/Code/rlcoach/.venv/bin/activate && python -c "import platform, rlreplay_rust; print(platform.machine(), getattr(rlreplay_rust, '__file__', 'missing'))"`  
Expected: PASS with the active machine architecture and an importable built module path.

**Step 5: Run corpus-health and one end-to-end replay analysis**
Run: `source .venv/bin/activate && PYTHONPATH=src python scripts/parser_corpus_health.py --roots replays,Replay_files --json`  
Expected: valid JSON corpus summary.  
Run: `source .venv/bin/activate && PYTHONPATH=src python -m rlcoach.cli analyze testing_replay.replay --adapter rust --out out`  
Expected: JSON output with rich parser diagnostics, non-empty events, and advanced mechanics/report fields aligned with schema.

**Verification plan:**
- Primary command: full targeted pytest lane above
- Secondary commands: full pytest, `cargo test`, `maturin develop`, corpus-health, single replay analyze

---

## Parallelization Notes

- The main agent stays on `feat/full-parser-analysis-vision` as the integration branch for the whole rollout.
- When Tasks 6, 7, 9, 10, and 12 begin, create one dedicated child branch and worktree per task, for example `task-6-provenance`, `task-7-mechanics-parity`, `task-9-advanced-mechanics-tests`, `task-10-event-preference-tests`, and `task-12-parser-docs`.
- Each parallel lane must follow the same cadence: implement on owned files only, run task verification, request the assigned clean-code-first review, fix findings, commit on the child branch, then hand the resulting SHA back to the main agent for integration.
- The main agent should integrate parallel commits one lane at a time, rerun the relevant targeted verification after each integration, then run the phase-level `review_guard` pass before moving to Task 11.
- Tasks 6, 7, 9, 10, and 12 are the main parallel-safe lanes after the shared contracts in Tasks 1-5 are done.
- Do not parallelize Tasks 1-5 or Task 8 because they define and then refactor the core authority model.
- Tasks 2-5 should be executed sequentially even though some share the same upstream dependency, because they all touch the parser contract chokepoint in `lib.rs`, normalization, and parser-facing tests.
- Before parallel execution, validate owned-file separation for the parallel bundle only with:

```bash
source .venv/bin/activate && python - <<'PY'
from pathlib import Path

parallel_tasks = {"6", "7", "9", "10", "12"}
current_task = None
owned = {}

for raw_line in Path("docs/plans/2026-04-07-rlcoach-full-parser-analysis-implementation.md").read_text().splitlines():
    line = raw_line.strip()
    if line.startswith("### Task "):
        current_task = line.split(":", 1)[0].replace("### Task ", "").strip()
        continue
    if not line.startswith("**Owned files:**") or current_task not in parallel_tasks:
        continue
    payload = line.replace("**Owned files:**", "", 1).strip()
    for item in payload.split(","):
        path = item.strip().strip("`")
        if path:
            owned.setdefault(path, []).append(current_task)

duplicates = {path: tasks for path, tasks in owned.items() if len(tasks) > 1}
if duplicates:
    for path, tasks in sorted(duplicates.items()):
        print(f"{path}: Tasks {', '.join(tasks)}")
    raise SystemExit(1)
PY
```

Expected: no output. If output appears, reassign ownership before parallel execution.

## Exit Criteria

- Rust parser emits the planned authoritative metadata/state/event contract or explicitly documented equivalents, with touch authority either parser-authored or deliberately documented as inference-backed.
- Normalization preserves the richer contract without ambiguity, including explicit `True/False/None` component-state semantics.
- Events and mechanics are authoritative-first where parser truth exists, and no mixed-authority path double-counts.
- The concrete `skim_count` / `psycho_count` surfacing bug is fixed, and schema/report/docs all match the implemented mechanic surface with zero intentionally-unsurfaced fields left undocumented.
- Advanced mechanics coverage includes at least one positive and one anti-false-positive test per mechanic family.
- Focused parser/analysis/docs pytest lane passes.
- Full Python test suite passes.
- Rust crate tests pass.
- `maturin develop` passes and the local built module imports successfully on the active machine architecture.
- Corpus-health passes with network success rate greater than or equal to the recorded pre-change baseline, or at least `99.5%` if the baseline was already higher-confidence.
- Single-replay end-to-end analysis on `testing_replay.replay` produces schema-valid output with non-empty events and the expected parser diagnostics surface.
