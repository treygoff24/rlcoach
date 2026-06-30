# RLCoach Parser Full Vision Implementation Plan

**Goal:** Build the parser, normalization, events, analysis, schema, and report surfaces all the way to the full intended RLCoach vision so the Rust parser is authoritative where it should be, the downstream analysis is complete, and the entire stack is tested and working end to end.

**Architecture:** Keep the current Rust `boxcars` + Python adapter architecture, but upgrade it from a strong frame-telemetry bridge into a richer authoritative replay signal pipeline. The implementation should move high-confidence state and event capture into Rust, preserve those contracts through typed Python normalization, then simplify downstream event/mechanics inference to prefer authoritative parser data and only fall back to heuristics when replay data is truly unavailable.

**Tech Stack:** Rust (`boxcars`, `pyo3`), Python (`pytest`, dataclasses, jsonschema), existing RLCoach parser/normalize/events/analysis/report modules, local replay corpus + synthetic fixtures.

---

## Definition of Done

The project reaches the intended end-state only when all of the following are true:

1. The Rust parser emits a documented, typed, diagnostics-first contract for:
   - header metadata
   - per-frame ball/car state
   - authoritative component-state flags
   - parser-authored touch events
   - parser-authored demo events
   - parser-authored kickoff/tickmark markers
   - parser-authored boost pad events
   - parser provenance / degradation metadata
2. `normalize.py` converts every parser-authored signal into typed Python dataclasses without lossy shape drift.
3. Event detectors prefer parser-authored events first and only fall back to heuristics when the parser lacks that signal for a given replay.
4. `analysis/mechanics.py` uses authoritative parser signals where available for mechanic classification and still degrades gracefully when only frame telemetry exists.
5. The replay report schema and report generation surface the full advanced mechanics set and authoritative parser diagnostics.
6. Targeted tests, golden tests, corpus-health checks, and focused end-to-end runs all pass under the venv.
7. The resulting docs describe the real parser contract, fallback behavior, and verification workflow.

---

## Task 0: Freeze the Current Baseline and Turn It into Explicit Gates

**Parallel:** no  
**Blocked by:** none  
**Owned files:** `tests/parser/test_rust_adapter_smoke.py`, `tests/test_parser_interface.py`, `tests/test_report_end_to_end.py`, `tests/test_benchmarks.py`, `codex/logs/2026-04-07-parser-full-vision-baseline.md`  
**Invariants:** Do not change production behavior in this task; only add baseline checks and record evidence.  
**Out of scope:** New parser features.

**Files:**
- Modify: `tests/parser/test_rust_adapter_smoke.py`
- Modify: `tests/test_parser_interface.py`
- Modify: `tests/test_report_end_to_end.py`
- Modify: `tests/test_benchmarks.py`
- Create: `codex/logs/2026-04-07-parser-full-vision-baseline.md`

**Step 1: Write the failing tests**
```python
def test_rust_parser_contract_baseline_includes_parser_meta_and_pad_events():
    adapter = get_adapter("rust")
    network = adapter.parse_network(Path("testing_replay.replay"))
    assert network is not None
    assert network.frames
    frame = network.frames[0]
    assert "_parser_meta" in frame
    assert "boost_pad_events" in frame


def test_report_baseline_surfaces_network_scorecard_and_diagnostics():
    report = generate_report(Path("testing_replay.replay"), adapter_name="rust")
    parser = report["quality"]["parser"]
    assert "network_diagnostics" in parser
    assert "scorecard" in parser
```

**Step 2: Run tests to verify the baseline shape**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/parser/test_rust_adapter_smoke.py tests/test_parser_interface.py tests/test_report_end_to_end.py -q`  
Expected: PASS or a narrowly-scoped FAIL that documents current contract drift.

**Step 3: Record live baseline evidence**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/parser/test_rust_adapter_smoke.py tests/test_parser_interface.py tests/test_analysis_new_modules.py -q`  
Expected: PASS, with command output summarized in `codex/logs/2026-04-07-parser-full-vision-baseline.md`.

**Step 4: Add corpus-health assertions for parser-scorecard expectations**
```python
def test_parser_corpus_health_includes_authority_fields(tmp_path):
    result = run_parser_corpus_health(tmp_path)
    assert "network_success_rate" in result
    assert "top_error_codes" in result
```

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/parser/test_rust_adapter_smoke.py tests/test_parser_interface.py tests/test_report_end_to_end.py tests/test_benchmarks.py -q`
- Secondary checks: `source .venv/bin/activate && PYTHONPATH=src python scripts/parser_corpus_health.py --roots replays,Replay_files --json`

---

## Task 1: Complete the Rust Header Contract

**Parallel:** no  
**Blocked by:** Task 0  
**Owned files:** `parsers/rlreplay_rust/src/lib.rs`, `src/rlcoach/parser/rust_adapter.py`, `src/rlcoach/parser/types.py`, `tests/test_rust_adapter.py`, `tests/test_parser_interface.py`, `tests/test_report_end_to_end.py`  
**Invariants:** Existing header fields must remain backward-compatible; missing values must degrade to `None`, not crash.  
**Out of scope:** Network frame/event extraction.

**Files:**
- Modify: `parsers/rlreplay_rust/src/lib.rs`
- Modify: `src/rlcoach/parser/rust_adapter.py`
- Modify: `src/rlcoach/parser/types.py`
- Modify: `tests/test_rust_adapter.py`
- Modify: `tests/test_parser_interface.py`
- Modify: `tests/test_report_end_to_end.py`

**Step 1: Write the failing tests**
```python
def test_rust_header_exposes_extended_metadata():
    header = get_adapter("rust").parse_header(Path("testing_replay.replay"))
    assert hasattr(header, "engine_build")
    assert hasattr(header, "match_guid")
    assert hasattr(header, "overtime")
    assert hasattr(header, "mutators")
```

**Step 2: Run test to verify current failure shape**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_rust_adapter.py::test_rust_header_exposes_extended_metadata -q`  
Expected: FAIL if any field remains unpopulated or incorrectly normalized.

**Step 3: Write minimal implementation**
```rust
// parsers/rlreplay_rust/src/lib.rs
header.set_item("engine_build", build_version)?;
header.set_item("match_guid", match_guid_or_none)?;
header.set_item("overtime", overtime_or_none)?;
header.set_item("mutators", mutators_dict)?;
```

```python
# src/rlcoach/parser/rust_adapter.py
return Header(
    ...,
    engine_build=d.get("engine_build"),
    match_guid=d.get("match_guid"),
    overtime=d.get("overtime"),
    mutators=d.get("mutators", {}) or {},
)
```

**Step 4: Run test to verify it passes**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_rust_adapter.py::test_rust_header_exposes_extended_metadata -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_rust_adapter.py tests/test_parser_interface.py::test_parse_real_replay_file tests/test_report_end_to_end.py -q`
- Secondary checks: `source .venv/bin/activate && PYTHONPATH=src python -m rlcoach.cli report-md testing_replay.replay --out /tmp/rlcoach-plan-check --pretty`

---

## Task 2: Upgrade the Rust Frame Contract to Full Authoritative State

**Parallel:** no  
**Blocked by:** Task 1  
**Owned files:** `parsers/rlreplay_rust/src/lib.rs`, `src/rlcoach/parser/types.py`, `src/rlcoach/parser/rust_adapter.py`, `src/rlcoach/normalize.py`, `tests/test_rust_adapter.py`, `tests/test_normalize.py`, `tests/test_parser_interface.py`  
**Invariants:** Existing frame fields stay valid; new fields must be optional and degradable.  
**Out of scope:** Parser-authored events.

**Files:**
- Modify: `parsers/rlreplay_rust/src/lib.rs`
- Modify: `src/rlcoach/parser/types.py`
- Modify: `src/rlcoach/parser/rust_adapter.py`
- Modify: `src/rlcoach/normalize.py`
- Modify: `tests/test_rust_adapter.py`
- Modify: `tests/test_normalize.py`
- Modify: `tests/test_parser_interface.py`

**Step 1: Write the failing tests**
```python
def test_component_state_flags_are_true_false_none_not_just_positive_pulses():
    network = get_adapter("rust").parse_network(Path("testing_replay.replay"))
    sample = network.frames[0]["players"][0]
    assert "is_jumping" in sample
    assert "is_dodging" in sample
    assert "is_double_jumping" in sample
    assert sample["is_jumping"] in {True, False, None}


def test_normalize_preserves_extended_frame_state():
    frames = build_timeline(header, raw_frames)
    player = frames[0].players[0]
    assert hasattr(player, "is_jumping")
    assert hasattr(player, "is_dodging")
    assert hasattr(player, "is_double_jumping")
```

**Step 2: Run tests to verify failure**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_rust_adapter.py::test_component_state_flags_are_true_false_none_not_just_positive_pulses tests/test_normalize.py::test_normalize_preserves_component_state_flags -q`  
Expected: FAIL on missing `False` semantics or missing typed propagation.

**Step 3: Write minimal implementation**
```rust
// parsers/rlreplay_rust/src/lib.rs
p.set_item("is_jumping", observed_jump_state)?;
p.set_item("is_dodging", observed_dodge_state)?;
p.set_item("is_double_jumping", observed_double_jump_state)?;
```

```python
# src/rlcoach/parser/types.py
class PlayerFrame:
    ...
    is_jumping: bool | None = None
    is_dodging: bool | None = None
    is_double_jumping: bool | None = None
```

**Step 4: Run tests to verify pass**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_rust_adapter.py tests/test_normalize.py tests/test_parser_interface.py -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_rust_adapter.py tests/test_normalize.py tests/test_parser_interface.py -q`
- Secondary checks: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_analysis_new_modules.py::test_authoritative_component_flags_drive_mechanics_detection -q`

---

## Task 3: Add a Parser-Authored Touch Event Stream

**Parallel:** no  
**Blocked by:** Task 2  
**Owned files:** `parsers/rlreplay_rust/src/lib.rs`, `src/rlcoach/parser/types.py`, `src/rlcoach/normalize.py`, `src/rlcoach/events/touches.py`, `src/rlcoach/report.py`, `tests/test_rust_adapter.py`, `tests/test_events.py`, `tests/test_events_calibration_synthetic.py`  
**Invariants:** Existing proximity-based touch fallback remains available when parser-authored touches are absent.  
**Out of scope:** Demo/kickoff/tickmark streams.

**Files:**
- Modify: `parsers/rlreplay_rust/src/lib.rs`
- Modify: `src/rlcoach/parser/types.py`
- Modify: `src/rlcoach/normalize.py`
- Modify: `src/rlcoach/events/touches.py`
- Modify: `src/rlcoach/report.py`
- Modify: `tests/test_rust_adapter.py`
- Modify: `tests/test_events.py`
- Modify: `tests/test_events_calibration_synthetic.py`

**Step 1: Write the failing tests**
```python
def test_parser_frames_can_include_authoritative_touch_events():
    network = get_adapter("rust").parse_network(Path("testing_replay.replay"))
    frame = network.frames[0]
    assert "touch_events" in frame


def test_touch_detector_prefers_parser_authored_touch_events():
    touches = detect_touches(frames_with_parser_touch_events)
    assert touches
    assert touches[0].player_id == "player_0"
```

**Step 2: Run tests to verify failure**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_rust_adapter.py::test_parser_frames_can_include_authoritative_touch_events tests/test_events.py::test_touch_detector_prefers_parser_authored_touch_events -q`  
Expected: FAIL because `touch_events` is not emitted/consumed yet.

**Step 3: Write minimal implementation**
```rust
// parsers/rlreplay_rust/src/lib.rs
f.set_item("touch_events", touch_list)?;
```

```python
# src/rlcoach/events/touches.py
if _frames_have_authoritative_touches(frames):
    return _touches_from_parser_events(frames)
return _touches_from_proximity(frames)
```

**Step 4: Run tests to verify pass**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_rust_adapter.py tests/test_events.py::test_touch_detector_prefers_parser_authored_touch_events tests/test_events_calibration_synthetic.py -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_rust_adapter.py tests/test_events.py tests/test_events_calibration_synthetic.py -q`
- Secondary checks: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_report_end_to_end.py -q`

---

## Task 4: Add Parser-Authored Demo, Kickoff, and Tickmark Streams

**Parallel:** no  
**Blocked by:** Task 3  
**Owned files:** `parsers/rlreplay_rust/src/lib.rs`, `src/rlcoach/parser/types.py`, `src/rlcoach/normalize.py`, `src/rlcoach/events/demos.py`, `src/rlcoach/events/kickoffs.py`, `src/rlcoach/events/timeline.py`, `tests/test_events.py`, `tests/test_rust_adapter.py`  
**Invariants:** Existing heuristic demo/kickoff detectors stay as fallback.  
**Out of scope:** Mechanics-specific parser upgrades.

**Files:**
- Modify: `parsers/rlreplay_rust/src/lib.rs`
- Modify: `src/rlcoach/parser/types.py`
- Modify: `src/rlcoach/normalize.py`
- Modify: `src/rlcoach/events/demos.py`
- Modify: `src/rlcoach/events/kickoffs.py`
- Modify: `src/rlcoach/events/timeline.py`
- Modify: `tests/test_events.py`
- Modify: `tests/test_rust_adapter.py`

**Step 1: Write the failing tests**
```python
def test_parser_can_emit_demo_events():
    network = get_adapter("rust").parse_network(Path("testing_replay.replay"))
    frame = network.frames[0]
    assert "demo_events" in frame


def test_demo_detector_prefers_authoritative_parser_events():
    demos = detect_demos(frames_with_parser_demo_events)
    assert demos[0].attacker == "player_1"
```

**Step 2: Run tests to verify failure**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_rust_adapter.py::test_parser_can_emit_demo_events tests/test_events.py::test_demo_detector_prefers_authoritative_parser_events -q`  
Expected: FAIL.

**Step 3: Write minimal implementation**
```python
# src/rlcoach/events/demos.py
if _frames_have_authoritative_demos(frames):
    return _demos_from_parser_events(frames)
return _demos_from_state_transitions(frames)
```

**Step 4: Run tests to verify pass**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_events.py tests/test_rust_adapter.py -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_events.py tests/test_rust_adapter.py -q`
- Secondary checks: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_report_end_to_end.py::test_report_baseline_surfaces_network_scorecard_and_diagnostics -q`

---

## Task 5: Expand the Typed Parser/Normalize Contract for Authoritative Event Data

**Parallel:** yes  
**Blocked by:** Task 4  
**Owned files:** `src/rlcoach/parser/types.py`, `src/rlcoach/normalize.py`, `tests/test_normalize.py`, `tests/test_parser_interface.py`  
**Invariants:** Type additions must be additive and optional.  
**Out of scope:** Event detector behavior.

**Files:**
- Modify: `src/rlcoach/parser/types.py`
- Modify: `src/rlcoach/normalize.py`
- Modify: `tests/test_normalize.py`
- Modify: `tests/test_parser_interface.py`

**Step 1: Write the failing tests**
```python
def test_frame_supports_authoritative_event_collections():
    frame = Frame(timestamp=0.0, ball=ball)
    assert hasattr(frame, "boost_pad_events")
    assert hasattr(frame, "touch_events")
    assert hasattr(frame, "demo_events")
```

**Step 2: Run test to verify failure**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_parser_interface.py::test_frame_supports_authoritative_event_collections -q`  
Expected: FAIL.

**Step 3: Write minimal implementation**
```python
@dataclass(frozen=True)
class Frame:
    ...
    boost_pad_events: list[BoostPadEventFrame] = field(default_factory=list)
    touch_events: list[TouchEventFrame] = field(default_factory=list)
    demo_events: list[DemoEventFrame] = field(default_factory=list)
```

**Step 4: Run test to verify pass**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_parser_interface.py::test_frame_supports_authoritative_event_collections tests/test_normalize.py -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_normalize.py tests/test_parser_interface.py -q`
- Secondary checks: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_events.py -q`

---

## Task 6: Rebuild the Touch/Challenge/Passing Stack on Top of Authoritative Events

**Parallel:** yes  
**Blocked by:** Task 5  
**Owned files:** `src/rlcoach/events/touches.py`, `src/rlcoach/events/challenges.py`, `src/rlcoach/analysis/passing.py`, `tests/test_events.py`, `tests/test_analysis_passing.py`, `tests/test_analysis_challenges.py`  
**Invariants:** Existing public event/report schemas remain compatible.  
**Out of scope:** Mechanics-specific event upgrades.

**Files:**
- Modify: `src/rlcoach/events/touches.py`
- Modify: `src/rlcoach/events/challenges.py`
- Modify: `src/rlcoach/analysis/passing.py`
- Modify: `tests/test_events.py`
- Modify: `tests/test_analysis_passing.py`
- Modify: `tests/test_analysis_challenges.py`

**Step 1: Write the failing tests**
```python
def test_challenge_detection_prefers_authoritative_touch_order():
    challenges = detect_challenge_events(frames, touches_from_parser)
    assert challenges


def test_passing_analysis_uses_authoritative_touch_chain():
    result = analyze_passing(frames, events, player_id="player_0")
    assert result["passes_completed"] >= 1
```

**Step 2: Run tests to verify failure**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_analysis_passing.py tests/test_analysis_challenges.py -q`  
Expected: FAIL or expose heuristic-only assumptions.

**Step 3: Write minimal implementation**
```python
def _touch_sequence(frames: list[Frame]) -> list[TouchEvent]:
    if _frames_have_authoritative_touches(frames):
        return _touches_from_parser_events(frames)
    return _touches_from_proximity(frames)
```

**Step 4: Run tests to verify pass**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_analysis_passing.py tests/test_analysis_challenges.py tests/test_events.py -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_analysis_passing.py tests/test_analysis_challenges.py tests/test_events.py -q`
- Secondary checks: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_report_end_to_end.py -q`

---

## Task 7: Upgrade Mechanics Detection to Prefer Parser Authority Everywhere Feasible

**Parallel:** no  
**Blocked by:** Tasks 3, 4, 5, 6  
**Owned files:** `src/rlcoach/analysis/mechanics.py`, `src/rlcoach/parser/types.py`, `tests/test_analysis_new_modules.py`, `MECHANICS_DETECTION.md`  
**Invariants:** Mechanics remain available on degraded replays via physics heuristics.  
**Out of scope:** Report/schema surface changes.

**Files:**
- Modify: `src/rlcoach/analysis/mechanics.py`
- Modify: `src/rlcoach/parser/types.py`
- Modify: `tests/test_analysis_new_modules.py`
- Modify: `MECHANICS_DETECTION.md`

**Step 1: Write the failing tests**
```python
def test_mechanics_prefers_authoritative_touch_and_component_state_when_available():
    result = analyze_mechanics(frames_with_authoritative_touch_and_jump_flags)
    assert result["per_player"]["player_0"]["flip_reset_count"] == 1


def test_mechanics_falls_back_to_derivative_logic_when_authority_missing():
    result = analyze_mechanics(heuristic_only_frames)
    assert result["per_player"]["player_0"]["fast_aerial_count"] >= 0
```

**Step 2: Run tests to verify failure**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_analysis_new_modules.py -q`  
Expected: FAIL on new authoritative-path cases.

**Step 3: Write minimal implementation**
```python
if player.is_jumping is not None:
    use_authoritative_component_flags(...)
if frame.touch_events:
    use_authoritative_touch_context(...)
else:
    use_physics_heuristics(...)
```

**Step 4: Run tests to verify pass**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_analysis_new_modules.py -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_analysis_new_modules.py -q`
- Secondary checks: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_goldens.py -q`

---

## Task 8: Finish the Mechanics Report Surface

**Parallel:** yes  
**Blocked by:** Task 7  
**Owned files:** `src/rlcoach/analysis/mechanics.py`, `src/rlcoach/analysis/__init__.py`, `src/rlcoach/report.py`, `schemas/replay_report.schema.json`, `tests/test_schema_validation.py`, `tests/test_report_end_to_end.py`  
**Invariants:** Existing keys remain valid; new keys are additive.  
**Out of scope:** Parser internals.

**Files:**
- Modify: `src/rlcoach/analysis/mechanics.py`
- Modify: `src/rlcoach/analysis/__init__.py`
- Modify: `src/rlcoach/report.py`
- Modify: `schemas/replay_report.schema.json`
- Modify: `tests/test_schema_validation.py`
- Modify: `tests/test_report_end_to_end.py`

**Step 1: Write the failing tests**
```python
def test_player_mechanics_surface_includes_skim_and_psycho_counts():
    report = generate_report(Path("testing_replay.replay"), adapter_name="rust")
    mechanics = next(iter(report["analysis"]["per_player"].values()))["mechanics"]
    assert "skim_count" in mechanics
    assert "psycho_count" in mechanics
```

**Step 2: Run test to verify failure**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_report_end_to_end.py::test_player_mechanics_surface_includes_skim_and_psycho_counts -q`  
Expected: FAIL.

**Step 3: Write minimal implementation**
```python
per_player[player_id]["skim_count"] = counts.get("skim", 0)
per_player[player_id]["psycho_count"] = counts.get("psycho", 0)
```

**Step 4: Run test to verify pass**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_schema_validation.py tests/test_report_end_to_end.py -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_schema_validation.py tests/test_report_end_to_end.py -q`
- Secondary checks: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_goldens.py -q`

---

## Task 9: Add Real, Named Tests for Every Advanced Mechanic and Authoritative Event Path

**Parallel:** no  
**Blocked by:** Tasks 7 and 8  
**Owned files:** `tests/test_analysis_new_modules.py`, `tests/test_events.py`, `tests/test_events_calibration_synthetic.py`, `tests/goldens/synthetic_small.md`, `tests/goldens/header_only.md`  
**Invariants:** Test additions should not require large binary fixtures.  
**Out of scope:** Production code changes not needed to satisfy the new tests.

**Files:**
- Modify: `tests/test_analysis_new_modules.py`
- Modify: `tests/test_events.py`
- Modify: `tests/test_events_calibration_synthetic.py`
- Modify: `tests/goldens/synthetic_small.md`
- Modify: `tests/goldens/header_only.md`

**Step 1: Write the failing tests**
```python
def test_fast_aerial_authoritative_path():
    result = analyze_mechanics(frames_with_authoritative_fast_aerial)
    assert result["per_player"]["player_0"]["fast_aerial_count"] == 1


def test_flip_reset_authoritative_touch_path():
    result = analyze_mechanics(frames_with_authoritative_flip_reset_touch)
    assert result["per_player"]["player_0"]["flip_reset_count"] == 1


def test_parser_touch_fallback_to_proximity_when_missing():
    touches = detect_touches(frames_without_parser_touch_events)
    assert touches


def test_demo_detector_uses_parser_event_before_state_heuristic():
    demos = detect_demos(frames_with_parser_demo_events)
    assert demos[0].attacker == "player_1"
```

**Step 2: Run tests to verify failure**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_analysis_new_modules.py tests/test_events.py tests/test_events_calibration_synthetic.py -q`  
Expected: FAIL on the new named cases.

**Step 3: Write minimal implementation**
```python
# tests/test_analysis_new_modules.py
frames_with_authoritative_fast_aerial = build_frames_for_authoritative_fast_aerial()
frames_with_authoritative_flip_reset_touch = build_frames_for_authoritative_flip_reset()

# tests/test_events.py
frames_with_parser_demo_events = build_frames_with_parser_demo_events()
frames_without_parser_touch_events = build_frames_without_parser_touch_events()
```

**Step 4: Run tests to verify pass**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_analysis_new_modules.py tests/test_events.py tests/test_events_calibration_synthetic.py -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_analysis_new_modules.py tests/test_events.py tests/test_events_calibration_synthetic.py -q`
- Secondary checks: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_goldens.py -q`

---

## Task 10: Harden Corpus Reliability, Performance, and Fallback Semantics

**Parallel:** no  
**Blocked by:** Tasks 1 through 9  
**Owned files:** `scripts/parser_corpus_health.py`, `tests/test_benchmarks.py`, `codex/docs/network-frames-integration-issue-report.md`, `codex/logs/2026-04-07-parser-full-vision-corpus.md`  
**Invariants:** Maintain diagnostics-first behavior; never reintroduce silent parser degradation.  
**Out of scope:** New analysis features.

**Files:**
- Modify: `scripts/parser_corpus_health.py`
- Modify: `tests/test_benchmarks.py`
- Modify: `codex/docs/network-frames-integration-issue-report.md`
- Create: `codex/logs/2026-04-07-parser-full-vision-corpus.md`

**Step 1: Write the failing tests**
```python
def test_parser_corpus_health_tracks_authoritative_event_coverage(tmp_path):
    result = run_parser_corpus_health(tmp_path)
    assert "touch_event_coverage" in result
    assert "demo_event_coverage" in result
```

**Step 2: Run test to verify failure**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_benchmarks.py::test_parser_corpus_health_tracks_authoritative_event_coverage -q`  
Expected: FAIL.

**Step 3: Write minimal implementation**
```python
summary["touch_event_coverage"] = _coverage_ratio(
    total_replays, replays_with_authoritative_touches
)
summary["demo_event_coverage"] = _coverage_ratio(
    total_replays, replays_with_authoritative_demos
)
summary["authoritative_component_state_coverage"] = _coverage_ratio(
    total_replays, replays_with_authoritative_component_flags
)
```

**Step 4: Run test to verify pass**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_benchmarks.py -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_benchmarks.py -q`
- Secondary checks: `source .venv/bin/activate && PYTHONPATH=src python scripts/parser_corpus_health.py --roots replays,Replay_files --json`

---

## Task 11: Refresh the Human Docs to Match the Real Parser Contract

**Parallel:** yes  
**Blocked by:** Tasks 1 through 10  
**Owned files:** `README.md`, `MECHANICS_DETECTION.md`, `docs/api.md`, `codex/docs/master_status.md`, `codex/docs/network-frames-integration-issue-report.md`  
**Invariants:** Docs must describe actual behavior and fallback policy, not idealized or stale contracts.  
**Out of scope:** New production features.

**Files:**
- Modify: `README.md`
- Modify: `MECHANICS_DETECTION.md`
- Modify: `docs/api.md`
- Modify: `codex/docs/master_status.md`
- Modify: `codex/docs/network-frames-integration-issue-report.md`

**Step 1: Write the failing docs check**
```python
def test_docs_do_not_describe_networkframes_as_stub():
    text = Path("src/rlcoach/parser/types.py").read_text()
    assert "stub implementation" not in text.lower()
```

**Step 2: Run check to verify failure**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_parser_interface.py::test_network_frames_creation -q`  
Expected: PASS today, but docs/type comments still need manual refresh.

**Step 3: Write minimal documentation updates**
```markdown
- Parser contract: header + frames + diagnostics + authoritative events
- Fallback policy: authoritative first, heuristics second
- Verification commands: venv-first pytest/make workflow
```

**Step 4: Verify docs align with code**
Run: `source .venv/bin/activate && PYTHONPATH=src python -m rlcoach.cli --help`  
Expected: PASS, and docs references remain valid.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_parser_interface.py -q`
- Secondary checks: manual doc/code spot-check across the listed files

---

## Task 12: Run the Full End-to-End Gate for “Built, Tested, and Working”

**Parallel:** no  
**Blocked by:** Tasks 0 through 11  
**Owned files:** `codex/logs/2026-04-07-parser-full-vision-final-gate.md`  
**Invariants:** No partial closeout; this task is only done when all gate outputs are recorded.  
**Out of scope:** New code changes except narrowly-scoped fixes required to pass gates.

**Files:**
- Create: `codex/logs/2026-04-07-parser-full-vision-final-gate.md`

**Step 1: Run targeted parser + event + mechanics suites**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/parser/test_rust_adapter_smoke.py tests/test_rust_adapter.py tests/test_parser_interface.py tests/test_normalize.py tests/test_events.py tests/test_events_calibration_synthetic.py tests/test_analysis_new_modules.py tests/test_report_end_to_end.py tests/test_schema_validation.py tests/test_benchmarks.py -q`  
Expected: PASS.

**Step 2: Run repo quality gates**
Run: `make lint`  
Expected: PASS.

Run: `make test`  
Expected: PASS.

**Step 3: Run coverage gate**
Run: `make test-cov`  
Expected: PASS, including category threshold check.

**Step 4: Run end-to-end CLI smoke**
Run: `source .venv/bin/activate && PYTHONPATH=src python -m rlcoach.cli report-md testing_replay.replay --out /tmp/rlcoach-full-vision --pretty`  
Expected: writes `.json` and `.md` outputs without crashing.

**Step 5: Run corpus-health verification**
Run: `source .venv/bin/activate && PYTHONPATH=src python scripts/parser_corpus_health.py --roots replays,Replay_files --json`  
Expected: successful JSON output with parser coverage and authority metrics.

**Step 6: Record final evidence**
Write command summaries, pass/fail, and any residual risks to `codex/logs/2026-04-07-parser-full-vision-final-gate.md`.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/parser/test_rust_adapter_smoke.py tests/test_rust_adapter.py tests/test_parser_interface.py tests/test_normalize.py tests/test_events.py tests/test_events_calibration_synthetic.py tests/test_analysis_new_modules.py tests/test_report_end_to_end.py tests/test_schema_validation.py tests/test_benchmarks.py -q`
- Secondary checks: `make lint`, `make test`, `make test-cov`, CLI smoke, corpus-health smoke

---

## Recommended Execution Order

1. Tasks 0 through 4 sequentially to finish the parser contract.
2. Tasks 5 and 6 in parallel once parser-authored events exist.
3. Task 7 after authoritative signals are flowing end to end.
4. Tasks 8 and 11 in parallel once behavior stabilizes.
5. Tasks 9 and 10 after report/schema and mechanics authority have landed.
6. Task 12 only after all earlier tasks are green.

---

## Owned Files Validation Command

Run after any edits to this plan:

```bash
python - <<'PY'
from pathlib import Path

plan = Path("docs/plans/2026-04-07-parser-full-vision-implementation.md").read_text().splitlines()
parallel_blocks = []
for i, line in enumerate(plan):
    if line.strip() == "**Parallel:** yes":
        owned = next(
            (l for l in plan[i:i+8] if l.startswith("**Owned files:**")),
            None,
        )
        if owned:
            files = [
                part.strip().strip("`")
                for part in owned.split("**Owned files:**", 1)[1].split(",")
            ]
            parallel_blocks.append(files)

seen = {}
dupes = set()
for idx, files in enumerate(parallel_blocks):
    for f in files:
        if f in seen:
            dupes.add(f)
        seen[f] = idx

for dup in sorted(dupes):
    print(dup)
PY
```

Expected: no output.

---

## Execution Handoff

Once this plan is approved, the safest execution options are:

1. Execute sequentially in this session for maximum continuity across parser contract work.
2. Split only the explicitly parallel tasks into isolated tickets/worktrees after rerunning the Owned Files Validation command.
3. Keep parser-contract tasks on one branch until the authoritative frame/event contract is stable, then branch out report/docs/test follow-up lanes.
