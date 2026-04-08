# RLCoach Full Parser And Analysis Vision Implementation Plan

**Goal:** Deliver the full RLCoach parser and coaching-analysis vision by extending the Rust parser into a richer authoritative replay source, wiring those authoritative signals through normalization, events, mechanics, and reporting, and locking the result down with unit, corpus, and end-to-end verification.

**Architecture:** Keep the current diagnostics-first `boxcars` + `pyo3` Rust core as the authoritative replay-state source, but expand its contract in two directions: richer header extraction and richer network semantics. Continue to normalize everything into typed Python dataclasses, prefer authoritative parser data whenever available, and preserve heuristic fallbacks only where the parser contract is intentionally nullable or unavailable.

**Tech Stack:** Rust (`boxcars`, `pyo3`, `maturin`), Python (`pytest`, `jsonschema`, dataclasses), existing RLCoach parser/normalize/events/analysis/report pipeline, Makefile gates (`make test`, `make lint`, `make fmt`).

---

## Target End State

“Built, tested, and working” for this effort means all of the following are true at the same time:

1. The Rust parser emits complete high-value header metadata:
   - playlist, map, team size, scores, goals, highlights
   - engine build, match GUID, overtime, mutators
   - player identity metadata, camera settings, and loadout data when present
2. The Rust parser emits authoritative network outputs:
   - frame-level ball/car state
   - authoritative `is_jumping`, `is_dodging`, `is_double_jumping` with full `True/False/None` semantics
   - authoritative sparse event streams for touches, demos/explosions, kickoff/tickmark markers, and boost pad events
   - frame provenance/debug metadata and diagnostics with attempted backend reporting
3. The Python pipeline preserves and consumes those authoritative signals:
   - normalize carries them into typed structures without dropping fidelity
   - events prefer authoritative streams before falling back to inference
   - mechanics prefers authoritative flags and authoritative touches where available
4. The report/schema surface reflects the full mechanics/event model:
   - advanced mechanics are exposed in per-player and team outputs
   - schema matches actual output
   - Markdown/JSON report generation remains valid
5. The verification story is strong:
   - focused unit tests for every new parser contract
   - focused tests for every authoritative-event consumer
   - targeted advanced-mechanics tests
   - parser smoke/integration tests
   - corpus-health and benchmark checks
   - `make test` and `make lint` pass

---

## Phase Ordering

- Phase 0: Freeze the contract and docs path first.
- Phase 1: Complete the Rust parser contract.
- Phase 2: Thread the authoritative data through Python types/normalization.
- Phase 3: Switch events and mechanics to prefer parser authority.
- Phase 4: Expand report/schema surfaces and validation.
- Phase 5: Ratchet tests, corpus health, and documentation until the result is operationally trustworthy.

---

### Task 0: Freeze The Canonical Parser Contract And Docs Location

**Parallel:** no  
**Blocked by:** none  
**Owned files:** `src/rlcoach/parser/types.py`, `tests/test_parser_interface.py`, `tests/test_schema_validation.py`, `schemas/replay_report.schema.json`, `codex/docs/parser_adapter.md`  
**Invariants:** Do not break the existing `Header`, `PlayerFrame`, `Frame`, or `NetworkFrames` import paths. Do not remove degraded-mode diagnostics.  
**Out of scope:** Rust implementation details, event-detection logic, mechanics thresholds.

**Files:**
- Create: `codex/docs/parser_adapter.md`
- Modify: `src/rlcoach/parser/types.py`
- Modify: `tests/test_parser_interface.py`
- Modify: `tests/test_schema_validation.py`
- Modify: `schemas/replay_report.schema.json`

**Step 1: Write the failing test**
```python
def test_network_frames_support_authoritative_events_contract():
    from rlcoach.parser.types import NetworkFrames

    fields = getattr(NetworkFrames, "__dataclass_fields__", {})
    assert "authoritative_events" in fields
```

**Step 2: Run test to verify it fails**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_parser_interface.py::test_network_frames_support_authoritative_events_contract -q`  
Expected: FAIL because `authoritative_events` is not present.

**Step 3: Write minimal implementation**
```python
@dataclass(frozen=True)
class AuthoritativeEvents:
    touches: list = field(default_factory=list)
    demos: list = field(default_factory=list)
    kickoffs: list = field(default_factory=list)
    tickmarks: list = field(default_factory=list)

@dataclass(frozen=True)
class NetworkFrames:
    ...
    authoritative_events: AuthoritativeEvents | None = None
```

**Step 4: Extend schema/docs to match**  
Document the canonical parser contract in `codex/docs/parser_adapter.md`, including:
- header fields
- frame fields
- authoritative sparse event streams
- diagnostics fields
- degraded/unavailable behavior

**Step 5: Run tests to verify pass**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_parser_interface.py tests/test_schema_validation.py -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_parser_interface.py tests/test_schema_validation.py -q`
- Secondary checks: `source .venv/bin/activate && python -m json.tool schemas/replay_report.schema.json >/dev/null`

---

### Task 1: Complete Rust Header Extraction To Match The Planned Metadata Contract

**Parallel:** no  
**Blocked by:** Task 0  
**Owned files:** `parsers/rlreplay_rust/src/lib.rs`, `src/rlcoach/parser/rust_adapter.py`, `tests/test_rust_adapter.py`, `tests/test_report_end_to_end.py`  
**Invariants:** Preserve existing header keys and fallback behavior. Continue to emit `parsed_with_rust_core`.  
**Out of scope:** Network-frame event streams, mechanics logic.

**Files:**
- Modify: `parsers/rlreplay_rust/src/lib.rs`
- Modify: `src/rlcoach/parser/rust_adapter.py`
- Modify: `tests/test_rust_adapter.py`
- Modify: `tests/test_report_end_to_end.py`

**Step 1: Write the failing test**
```python
def test_parse_header_exposes_match_guid_overtime_and_mutators():
    adapter = RustAdapter()
    header = adapter.parse_header(SAMPLE_REPLAY)
    assert hasattr(header, "match_guid")
    assert hasattr(header, "overtime")
    assert hasattr(header, "mutators")
```

**Step 2: Run test to verify it fails**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_rust_adapter.py::test_parse_header_exposes_match_guid_overtime_and_mutators -q`  
Expected: FAIL because the Rust header payload does not yet populate the full contract.

**Step 3: Write minimal implementation**
```rust
if let Some(p) = find_prop(&properties, "MatchGUID") {
    if let Some(s) = p.as_string() {
        header.set_item("match_guid", s)?;
    }
}
```

**Step 4: Update adapter mapping**
```python
return Header(
    ...,
    match_guid=d.get("match_guid"),
    overtime=d.get("overtime"),
    mutators=d.get("mutators", {}),
)
```

**Step 5: Run focused tests**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_rust_adapter.py tests/test_report_end_to_end.py -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_rust_adapter.py tests/test_report_end_to_end.py -q`
- Secondary checks: `source .venv/bin/activate && PYTHONPATH=src python -m rlcoach.cli analyze testing_replay.replay --adapter rust --out /tmp/rlcoach-header-check`

---

### Task 2: Make Component-State Flags Fully Authoritative

**Parallel:** no  
**Blocked by:** Task 0  
**Owned files:** `parsers/rlreplay_rust/src/lib.rs`, `src/rlcoach/parser/types.py`, `src/rlcoach/normalize.py`, `tests/test_normalize.py`, `tests/test_analysis_new_modules.py`  
**Invariants:** `None` must still mean “unavailable”, not “false”. Existing mechanics fallback behavior must continue to work.  
**Out of scope:** Touch/demo/kickoff event streams.

**Files:**
- Modify: `parsers/rlreplay_rust/src/lib.rs`
- Modify: `src/rlcoach/parser/types.py`
- Modify: `src/rlcoach/normalize.py`
- Modify: `tests/test_normalize.py`
- Modify: `tests/test_analysis_new_modules.py`

**Step 1: Write the failing test**
```python
def test_normalize_preserves_explicit_false_component_flags():
    raw = [{
        "timestamp": 0.0,
        "ball": {...},
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
    frames = build_timeline(header, raw)
    assert frames[0].players[0].is_jumping is False
```

**Step 2: Run test to verify it fails**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_normalize.py::test_normalize_preserves_explicit_false_component_flags -q`  
Expected: FAIL because the Rust-side contract and/or normalization path does not currently preserve explicit false-state semantics.

**Step 3: Write minimal implementation**
```rust
p.set_item("is_jumping", observed_jump_state)?;
p.set_item("is_dodging", observed_dodge_state)?;
p.set_item("is_double_jumping", observed_double_jump_state)?;
```

**Step 4: Update authoritative-preference tests**
```python
def test_mechanics_prefers_authoritative_false_over_derivative_spike():
    ...
    assert result["per_player"]["player_0"]["jump_count"] == 0
```

**Step 5: Run focused tests**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_normalize.py tests/test_analysis_new_modules.py -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_normalize.py tests/test_analysis_new_modules.py -q`
- Secondary checks: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_parser_interface.py::test_network_diagnostics_contract_is_documented_and_typed -q`

---

### Task 3: Add Authoritative Touch Events To The Rust Parser

**Parallel:** no  
**Blocked by:** Tasks 0-2  
**Owned files:** `parsers/rlreplay_rust/src/lib.rs`, `src/rlcoach/parser/types.py`, `src/rlcoach/parser/rust_adapter.py`, `tests/parser/test_rust_adapter_smoke.py`, `tests/test_parser_interface.py`  
**Invariants:** Do not regress existing frame emission. Do not encode touch semantics only in frame-local ad hoc dicts; use the canonical parser contract from Task 0.  
**Out of scope:** Python event-detector preference logic.

**Files:**
- Modify: `parsers/rlreplay_rust/src/lib.rs`
- Modify: `src/rlcoach/parser/types.py`
- Modify: `src/rlcoach/parser/rust_adapter.py`
- Modify: `tests/parser/test_rust_adapter_smoke.py`
- Modify: `tests/test_parser_interface.py`

**Step 1: Write the failing test**
```python
def test_parse_network_exposes_authoritative_touches_collection():
    adapter = RustAdapter()
    nf = adapter.parse_network(SAMPLE_REPLAY)
    assert nf is not None
    assert nf.authoritative_events is not None
    assert hasattr(nf.authoritative_events, "touches")
```

**Step 2: Run test to verify it fails**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_parser_interface.py::test_parse_network_exposes_authoritative_touches_collection -q`  
Expected: FAIL because `authoritative_events.touches` is not populated yet.

**Step 3: Write minimal implementation**
```rust
let touch = PyDict::new(py);
touch.set_item("timestamp", nf.time as f64)?;
touch.set_item("player_id", format!("player_{}", idx))?;
touch.set_item("ball_speed", ball_speed)?;
touches.append(touch)?;
```

**Step 4: Thread through adapter**
```python
return NetworkFrames(
    frame_count=len(frames),
    sample_rate=hz,
    frames=frames,
    authoritative_events=AuthoritativeEvents(touches=touches, ...),
)
```

**Step 5: Run focused tests**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/parser/test_rust_adapter_smoke.py tests/test_parser_interface.py -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/parser/test_rust_adapter_smoke.py tests/test_parser_interface.py -q`
- Secondary checks: `source .venv/bin/activate && PYTHONPATH=src python -m rlcoach.cli analyze testing_replay.replay --adapter rust --out /tmp/rlcoach-touch-check`

---

### Task 4: Add Authoritative Demo And Explosion Events To The Rust Parser

**Parallel:** no  
**Blocked by:** Tasks 0-2  
**Owned files:** `parsers/rlreplay_rust/src/lib.rs`, `src/rlcoach/parser/types.py`, `src/rlcoach/parser/rust_adapter.py`, `tests/parser/test_rust_adapter_smoke.py`, `tests/test_parser_interface.py`  
**Invariants:** Preserve `is_demolished` frame-state booleans even after adding sparse demo events.  
**Out of scope:** Python demo-detector preference logic.

**Files:**
- Modify: `parsers/rlreplay_rust/src/lib.rs`
- Modify: `src/rlcoach/parser/types.py`
- Modify: `src/rlcoach/parser/rust_adapter.py`
- Modify: `tests/parser/test_rust_adapter_smoke.py`
- Modify: `tests/test_parser_interface.py`

**Step 1: Write the failing test**
```python
def test_parse_network_exposes_authoritative_demo_events_collection():
    adapter = RustAdapter()
    nf = adapter.parse_network(SAMPLE_REPLAY)
    assert nf is not None
    assert nf.authoritative_events is not None
    assert hasattr(nf.authoritative_events, "demos")
```

**Step 2: Run test to verify it fails**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_parser_interface.py::test_parse_network_exposes_authoritative_demo_events_collection -q`  
Expected: FAIL.

**Step 3: Write minimal implementation**
```rust
let demo = PyDict::new(py);
demo.set_item("timestamp", nf.time as f64)?;
demo.set_item("victim_actor_id", victim)?;
demo.set_item("attacker_actor_id", attacker)?;
demos.append(demo)?;
```

**Step 4: Run focused tests**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/parser/test_rust_adapter_smoke.py tests/test_parser_interface.py -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/parser/test_rust_adapter_smoke.py tests/test_parser_interface.py -q`
- Secondary checks: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_rust_adapter.py -q`

---

### Task 5: Add Authoritative Kickoff And Tickmark Streams To The Rust Parser

**Parallel:** no  
**Blocked by:** Tasks 0-2  
**Owned files:** `parsers/rlreplay_rust/src/lib.rs`, `src/rlcoach/parser/types.py`, `src/rlcoach/parser/rust_adapter.py`, `tests/parser/test_rust_adapter_smoke.py`, `tests/test_parser_interface.py`  
**Invariants:** Do not break current frame timestamps or sample-rate measurement.  
**Out of scope:** Python kickoff-detector preference logic.

**Files:**
- Modify: `parsers/rlreplay_rust/src/lib.rs`
- Modify: `src/rlcoach/parser/types.py`
- Modify: `src/rlcoach/parser/rust_adapter.py`
- Modify: `tests/parser/test_rust_adapter_smoke.py`
- Modify: `tests/test_parser_interface.py`

**Step 1: Write the failing test**
```python
def test_parse_network_exposes_tickmarks_and_kickoff_markers():
    adapter = RustAdapter()
    nf = adapter.parse_network(SAMPLE_REPLAY)
    assert nf is not None
    assert nf.authoritative_events is not None
    assert hasattr(nf.authoritative_events, "tickmarks")
    assert hasattr(nf.authoritative_events, "kickoffs")
```

**Step 2: Run test to verify it fails**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_parser_interface.py::test_parse_network_exposes_tickmarks_and_kickoff_markers -q`  
Expected: FAIL.

**Step 3: Write minimal implementation**
```rust
let tick = PyDict::new(py);
tick.set_item("frame", frame_idx)?;
tick.set_item("timestamp", nf.time as f64)?;
tickmarks.append(tick)?;
```

**Step 4: Run focused tests**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/parser/test_rust_adapter_smoke.py tests/test_parser_interface.py -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/parser/test_rust_adapter_smoke.py tests/test_parser_interface.py -q`
- Secondary checks: `source .venv/bin/activate && PYTHONPATH=src python -m rlcoach.cli analyze testing_replay.replay --adapter rust --out /tmp/rlcoach-kickoff-check`

---

### Task 6: Carry Authoritative Event Streams Through Python Types And Normalization

**Parallel:** no  
**Blocked by:** Tasks 3-5  
**Owned files:** `src/rlcoach/parser/types.py`, `src/rlcoach/parser/rust_adapter.py`, `src/rlcoach/normalize.py`, `tests/test_normalize.py`, `tests/test_parser_interface.py`  
**Invariants:** Existing `build_timeline(header, frames)` callers must continue to work. Header-only behavior must remain valid.  
**Out of scope:** Event-detector preference changes.

**Files:**
- Modify: `src/rlcoach/parser/types.py`
- Modify: `src/rlcoach/parser/rust_adapter.py`
- Modify: `src/rlcoach/normalize.py`
- Modify: `tests/test_normalize.py`
- Modify: `tests/test_parser_interface.py`

**Step 1: Write the failing test**
```python
def test_build_timeline_preserves_authoritative_event_payloads():
    nf = NetworkFrames(
        frame_count=1,
        sample_rate=30.0,
        frames=[...],
        authoritative_events=AuthoritativeEvents(
            touches=[{"timestamp": 0.1, "player_id": "player_0"}],
            demos=[],
            kickoffs=[],
            tickmarks=[],
        ),
    )
    normalized = build_normalized_frames(header, nf.frames)
    assert normalized
```

**Step 2: Run test to verify it fails**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_normalize.py::test_build_timeline_preserves_authoritative_event_payloads -q`  
Expected: FAIL because authoritative events are not yet threaded through or attached anywhere in the normalized layer.

**Step 3: Write minimal implementation**
```python
@dataclass(frozen=True)
class Frame:
    ...
    authoritative_touches: list = field(default_factory=list)
```

**Step 4: Run focused tests**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_normalize.py tests/test_parser_interface.py -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_normalize.py tests/test_parser_interface.py -q`
- Secondary checks: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_report_end_to_end.py -q`

---

### Task 7: Prefer Authoritative Touches In Events And Challenge Detection

**Parallel:** no  
**Blocked by:** Task 6  
**Owned files:** `src/rlcoach/events/touches.py`, `src/rlcoach/events/challenges.py`, `src/rlcoach/report.py`, `tests/test_events.py`, `tests/test_events_calibration_synthetic.py`, `tests/test_analysis_challenges.py`  
**Invariants:** Heuristic touch inference must remain as a fallback when authoritative touches are absent.  
**Out of scope:** Demo/kickoff preference logic.

**Files:**
- Modify: `src/rlcoach/events/touches.py`
- Modify: `src/rlcoach/events/challenges.py`
- Modify: `src/rlcoach/report.py`
- Modify: `tests/test_events.py`
- Modify: `tests/test_events_calibration_synthetic.py`
- Modify: `tests/test_analysis_challenges.py`

**Step 1: Write the failing test**
```python
def test_detect_touches_prefers_authoritative_touch_stream():
    frames = build_frames_with_authoritative_touch(...)
    touches = detect_touches(frames)
    assert len(touches) == 1
    assert touches[0].player_id == "player_0"
```

**Step 2: Run test to verify it fails**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_events.py::test_detect_touches_prefers_authoritative_touch_stream -q`  
Expected: FAIL because `detect_touches` still infers from proximity only.

**Step 3: Write minimal implementation**
```python
if _frames_have_authoritative_touches(frames):
    return _touches_from_authoritative_stream(frames)
```

**Step 4: Run focused tests**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_events.py tests/test_events_calibration_synthetic.py tests/test_analysis_challenges.py -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_events.py tests/test_events_calibration_synthetic.py tests/test_analysis_challenges.py -q`
- Secondary checks: `source .venv/bin/activate && PYTHONPATH=src pytest tests/api/test_analysis.py -q`

---

### Task 8: Prefer Authoritative Demo And Kickoff Streams In Event Detection

**Parallel:** no  
**Blocked by:** Task 6  
**Owned files:** `src/rlcoach/events/demos.py`, `src/rlcoach/events/kickoffs.py`, `src/rlcoach/report.py`, `tests/test_events.py`, `tests/test_analysis_kickoffs.py`, `tests/test_report_end_to_end.py`  
**Invariants:** Preserve heuristic fallback for replays where parser event streams are unavailable.  
**Out of scope:** Mechanics logic.

**Files:**
- Modify: `src/rlcoach/events/demos.py`
- Modify: `src/rlcoach/events/kickoffs.py`
- Modify: `src/rlcoach/report.py`
- Modify: `tests/test_events.py`
- Modify: `tests/test_analysis_kickoffs.py`
- Modify: `tests/test_report_end_to_end.py`

**Step 1: Write the failing test**
```python
def test_detect_demos_prefers_authoritative_demo_stream():
    frames = build_frames_with_authoritative_demo(...)
    demos = detect_demos(frames)
    assert len(demos) == 1
```

**Step 2: Run test to verify it fails**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_events.py::test_detect_demos_prefers_authoritative_demo_stream -q`  
Expected: FAIL because `detect_demos` still reconstructs from state transitions only.

**Step 3: Write minimal implementation**
```python
if _frames_have_authoritative_demos(frames):
    return _demos_from_authoritative_stream(frames)
```

**Step 4: Run focused tests**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_events.py tests/test_analysis_kickoffs.py tests/test_report_end_to_end.py -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_events.py tests/test_analysis_kickoffs.py tests/test_report_end_to_end.py -q`
- Secondary checks: `source .venv/bin/activate && PYTHONPATH=src pytest tests/api/test_analysis.py -q`

---

### Task 9: Shift Mechanics Detection Toward Authoritative Touch And Flag Inputs

**Parallel:** no  
**Blocked by:** Tasks 2, 6, 7  
**Owned files:** `src/rlcoach/analysis/mechanics.py`, `tests/test_analysis_new_modules.py`, `tests/fixtures/builders.py`  
**Invariants:** Preserve the current advanced mechanics set and keep heuristic fallback when authoritative inputs are missing.  
**Out of scope:** Report/schema rollups.

**Files:**
- Modify: `src/rlcoach/analysis/mechanics.py`
- Modify: `tests/test_analysis_new_modules.py`
- Modify: `tests/fixtures/builders.py`

**Step 1: Write the failing test**
```python
def test_flip_reset_prefers_authoritative_touch_over_proximity_only():
    frames = build_flip_reset_sequence(authoritative_touch=True)
    result = analyze_mechanics(frames)
    assert result["per_player"]["player_0"]["flip_reset_count"] == 1
```

**Step 2: Run test to verify it fails**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_analysis_new_modules.py::test_flip_reset_prefers_authoritative_touch_over_proximity_only -q`  
Expected: FAIL because mechanics still uses frame-physics inference only.

**Step 3: Write minimal implementation**
```python
touches = _authoritative_touches_for_player(frame, player_id)
if touches:
    ball_touched = True
```

**Step 4: Expand authoritative-driven tests for**
- fast aerial
- flip reset
- dribble/flick
- double touch
- redirect
- ceiling shot with authoritative touch timing

**Step 5: Run focused tests**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_analysis_new_modules.py -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_analysis_new_modules.py -q`
- Secondary checks: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_analysis_kickoffs.py tests/test_analysis_challenges.py -q`

---

### Task 10: Finish Mechanics Rollups And Schema So The Full Mechanics Set Surfaces Correctly

**Parallel:** no  
**Blocked by:** Task 9  
**Owned files:** `src/rlcoach/analysis/mechanics.py`, `src/rlcoach/analysis/__init__.py`, `schemas/replay_report.schema.json`, `tests/test_schema_validation.py`, `tests/test_report_end_to_end.py`  
**Invariants:** Do not remove existing mechanics counts or rename existing schema keys.  
**Out of scope:** Rust parser internals.

**Files:**
- Modify: `src/rlcoach/analysis/mechanics.py`
- Modify: `src/rlcoach/analysis/__init__.py`
- Modify: `schemas/replay_report.schema.json`
- Modify: `tests/test_schema_validation.py`
- Modify: `tests/test_report_end_to_end.py`

**Step 1: Write the failing test**
```python
def test_mechanics_rollup_includes_skim_and_psycho_counts():
    result = analyze_mechanics(frames_with_skim_and_psycho())
    player = result["per_player"]["player_0"]
    assert player["skim_count"] == 1
    assert player["psycho_count"] == 1
```

**Step 2: Run test to verify it fails**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_analysis_new_modules.py::test_mechanics_rollup_includes_skim_and_psycho_counts -q`  
Expected: FAIL because the rollup omits those fields today.

**Step 3: Write minimal implementation**
```python
"skim_count": counts.get("skim", 0),
"psycho_count": counts.get("psycho", 0),
```

**Step 4: Expand team mechanics**
```python
return {
    "total_wavedashes": ...,
    "total_fast_aerials": ...,
    "total_flip_resets": ...,
    "total_dribbles": ...,
    ...
}
```

**Step 5: Run focused tests**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_analysis_new_modules.py tests/test_schema_validation.py tests/test_report_end_to_end.py -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_analysis_new_modules.py tests/test_schema_validation.py tests/test_report_end_to_end.py -q`
- Secondary checks: `source .venv/bin/activate && PYTHONPATH=src python -m rlcoach.cli report-md testing_replay.replay --out /tmp/rlcoach-md-check --pretty`

---

### Task 11: Ratchet Corpus Health, Benchmarking, And Real Replay Regression Gates

**Parallel:** no  
**Blocked by:** Tasks 1-10  
**Owned files:** `scripts/parser_corpus_health.py`, `tests/test_benchmarks.py`, `tests/parser/test_rust_adapter_smoke.py`, `tests/test_report_end_to_end.py`, `codex/docs/master_status.md`, `codex/logs/2026-04-07-parser-full-vision-baseline.md`  
**Invariants:** Keep the diagnostics-first scorecard behavior. Do not remove degraded-mode reporting.  
**Out of scope:** New feature implementation.

**Files:**
- Modify: `scripts/parser_corpus_health.py`
- Modify: `tests/test_benchmarks.py`
- Modify: `tests/parser/test_rust_adapter_smoke.py`
- Modify: `tests/test_report_end_to_end.py`
- Modify: `codex/docs/master_status.md`
- Create: `codex/logs/2026-04-07-parser-full-vision-baseline.md`

**Step 1: Write the failing test**
```python
def test_parser_corpus_health_reports_authoritative_event_coverage():
    result = build_health_report(sample_results)
    assert "touch_stream_coverage" in result
    assert "demo_stream_coverage" in result
```

**Step 2: Run test to verify it fails**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_benchmarks.py::test_parser_corpus_health_reports_authoritative_event_coverage -q`  
Expected: FAIL.

**Step 3: Write minimal implementation**
```python
report["touch_stream_coverage"] = ...
report["demo_stream_coverage"] = ...
report["kickoff_stream_coverage"] = ...
```

**Step 4: Run corpus/perf checks**  
Run: `source .venv/bin/activate && PYTHONPATH=src python scripts/parser_corpus_health.py --roots replays,Replay_files --json`  
Expected: JSON output with coverage for network parse plus authoritative event streams.

**Step 5: Run focused regression suite**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/parser/test_rust_adapter_smoke.py tests/test_benchmarks.py tests/test_report_end_to_end.py -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/parser/test_rust_adapter_smoke.py tests/test_benchmarks.py tests/test_report_end_to_end.py -q`
- Secondary checks: `source .venv/bin/activate && PYTHONPATH=src python scripts/parser_corpus_health.py --roots replays,Replay_files --json`

---

### Task 12: Finish Documentation, Examples, And Operator Runbooks

**Parallel:** yes  
**Blocked by:** Tasks 1-11  
**Owned files:** `codex/docs/parser_adapter.md`, `README.md`, `codex/docs/master_status.md`, `docs/api.md`  
**Invariants:** Documentation must match the implemented contract exactly.  
**Out of scope:** New feature code.

**Files:**
- Modify: `codex/docs/parser_adapter.md`
- Modify: `README.md`
- Modify: `codex/docs/master_status.md`
- Modify: `docs/api.md`

**Step 1: Write the failing doc check**
```python
def test_docs_reference_parse_network_with_diagnostics_contract():
    text = Path("codex/docs/parser_adapter.md").read_text()
    assert "authoritative_events" in text
    assert "touches" in text
    assert "demos" in text
```

**Step 2: Run test to verify it fails**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_parser_interface.py::test_docs_reference_parse_network_with_diagnostics_contract -q`  
Expected: FAIL until docs are updated or the doc-check test is created.

**Step 3: Write minimal implementation**
```markdown
## Network Contract
- frames
- diagnostics
- authoritative_events
```

**Step 4: Run focused tests**  
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_parser_interface.py -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_parser_interface.py -q`
- Secondary checks: `source .venv/bin/activate && python -m rlcoach.cli --help`

---

### Task 13: Run Full Gates And Lock The Release Checklist

**Parallel:** no  
**Blocked by:** Tasks 0-12  
**Owned files:** `Makefile`, `codex/docs/master_status.md`, `codex/logs/2026-04-07-parser-full-vision-baseline.md`  
**Invariants:** No TODO-grade completion claims without green gates.  
**Out of scope:** New feature work.

**Files:**
- Modify: `codex/docs/master_status.md`
- Modify: `codex/logs/2026-04-07-parser-full-vision-baseline.md`

**Step 1: Run focused subsystem suites**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/parser/test_rust_adapter_smoke.py tests/test_rust_adapter.py tests/test_parser_interface.py tests/test_normalize.py tests/test_events.py tests/test_events_calibration_synthetic.py tests/test_analysis_new_modules.py tests/test_report_end_to_end.py tests/test_schema_validation.py tests/test_schema_validation_hardening.py tests/test_benchmarks.py -q`  
Expected: PASS.

**Step 2: Run repo gates**
Run: `make test`  
Expected: PASS.

**Step 3: Run lint gate**
Run: `make lint`  
Expected: PASS.

**Step 4: Optional formatting pass if needed**
Run: `make fmt`  
Expected: no diffs after formatter rerun.

**Step 5: Build/install Rust extension from clean source**
Run: `make rust-dev`  
Expected: PASS with importable `rlreplay_rust`.

**Step 6: Record final operational checklist**
- parser diagnostics green
- corpus-health coverage acceptable
- advanced mechanics surfaced in report schema
- docs updated
- tests green

**Verification plan:**
- Primary command: `make test`
- Secondary checks: `make lint`, `make rust-dev`

---

## Parallelization Notes

- `Task 12` is the only task marked `Parallel: yes`; it is safe to run in parallel only after Tasks 1-11 are merged or effectively complete because it depends on the finalized contract.
- All Rust parser tasks are intentionally serialized because they overlap heavily in `parsers/rlreplay_rust/src/lib.rs`, `src/rlcoach/parser/types.py`, and `src/rlcoach/parser/rust_adapter.py`.
- All event-preference tasks are intentionally serialized because they overlap in report integration and end-to-end tests.

---

## Owned Files Validation

Run after any edits to this plan if you intend to split execution into tickets:

```bash
rg '\*\*Owned files:\*\*' docs/plans/2026-04-07-rlcoach-full-parser-analysis-vision.md \
  | sed 's/.*\*\*Owned files:\*\* *//' \
  | tr ',' '\n' \
  | sed 's/`//g' \
  | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' \
  | rg -v '^$' \
  | sort \
  | uniq -d
```

Expected: no output for any tasks you intend to execute in parallel.

---

## Recommended Execution Order

1. Task 0
2. Task 1
3. Task 2
4. Tasks 3-5
5. Task 6
6. Tasks 7-8
7. Task 9
8. Task 10
9. Task 11
10. Task 12
11. Task 13

---

## Handoff Options

1. Execute sequentially in this session.
2. Split into implementation tickets after Task 0 if you want multiple worktrees.
3. Ask for a plan review pass before execution to tighten any task boundaries or verification commands.
