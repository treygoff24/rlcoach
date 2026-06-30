# RLCoach Full Parser Authority and Analysis Completion Implementation Plan

**Goal:** Take RLCoach from its current diagnostics-first Rust telemetry bridge plus downstream inference stack to a fully integrated parser-and-analysis system where the parser captures the critical authoritative replay signals, normalization preserves them, events/mechanics prefer parser truth, and reporting/tests/docs prove the full vision works end to end.

**Architecture:** Keep the existing `boxcars` + `pyo3` Rust core and Python adapter/normalization/report pipeline, but expand the parser contract in layers: richer header metadata, fuller authoritative per-frame state, explicit parser event streams, typed normalization, parser-first downstream consumers, and corpus/golden verification. Do not rewrite the whole stack or add a second backend now; finish the current architecture and harden it against the maximal scope already defined in repo plans.

**Tech Stack:** Rust (`boxcars`, `pyo3`), Python (`pytest`, dataclasses, jsonschema), existing RLCoach parser/normalize/events/analysis/report modules, existing Makefile + `maturin` workflow.

---

## Plan Principles

- Always use the project virtualenv for Python commands:
  `source .venv/bin/activate && ...`
- Treat the Rust parser as the authoritative source for what replay data explicitly contains.
- Prefer parser truth over heuristics when the parser emits a signal; keep heuristics only as fallback until corpus coverage proves the parser lane is complete.
- Land contract changes in this order:
  1. types/schema/tests
  2. Rust emission
  3. Python normalization
  4. downstream consumers
  5. report/markdown/docs
  6. corpus and regression gates
- Keep `boxcars` as the only backend unless corpus reliability regresses below the already documented decision gate.

## Final Done Criteria

- Rust parser emits the full agreed contract for:
  - richer header metadata
  - authoritative per-frame player/ball state
  - explicit parser event streams for touches, demos/explosions, boost pads, and replay markers/tickmarks where available
  - complete component-state semantics (`True`/`False`/`None`) rather than positive pulses only
- `src/rlcoach/normalize.py` preserves all parser-authoritative data into typed Python structures.
- `src/rlcoach/events/*` prefers parser-authoritative events and falls back cleanly to heuristics only when parser data is absent.
- `src/rlcoach/analysis/mechanics.py` uses parser authority wherever possible for mechanic detection and report surfaces fully reflect the implemented mechanic set.
- JSON schema, markdown report, and team/player rollups expose the full advanced mechanics/output contract.
- Focused tests, goldens, parser smoke tests, and corpus-health checks all pass.
- Parser/operator docs accurately describe real behavior.

---

### Task 0: Freeze the Contract and Gap Matrix

**Parallel:** no  
**Blocked by:** none  
**Owned files:** `docs/plans/2026-04-07-rlcoach-parser-full-vision-implementation.md`, `codex/Plans/2026-02-10-parser-refactor-update-plan.md`, `codex/Plans/rlcoach_implementation_plan.md`, `MECHANICS_SPEC.md`, `MECHANICS_DETECTION.md`, `MECHANICS_IMPLEMENTATION_PLAN_v2.md`, `codex/Plans/missing-mechanics.md`  
**Invariants:** Do not change runtime behavior; only document the target contract and execution order.  
**Out of scope:** Implementing code changes.

**Files:**
- Modify: `docs/plans/2026-04-07-rlcoach-parser-full-vision-implementation.md`
- Read-only reference: `codex/Plans/2026-02-10-parser-refactor-update-plan.md`
- Read-only reference: `codex/Plans/rlcoach_implementation_plan.md`
- Read-only reference: `MECHANICS_SPEC.md`
- Read-only reference: `MECHANICS_DETECTION.md`
- Read-only reference: `MECHANICS_IMPLEMENTATION_PLAN_v2.md`
- Read-only reference: `codex/Plans/missing-mechanics.md`

**Step 1: Write the failing checklist**
```markdown
- [ ] Header contract lists every required field and source of truth
- [ ] Frame contract lists every authoritative per-frame field and event stream
- [ ] Downstream consumer ownership is mapped for every parser field
- [ ] Every planned mechanic is mapped to its required parser inputs
```

**Step 2: Verify the repo currently has no unified contract**
Run: `rg -n "full parser|authoritative.*touch|tickmark|is_double_jumping" docs/plans codex/Plans MECHANICS_* src/rlcoach`  
Expected: multiple partial matches, no single canonical complete contract.

**Step 3: Write the unified contract section into this plan**
```markdown
## Unified Contract
- Header fields
- Frame/player/ball fields
- Parser event streams
- Mechanics-required signals
- Report/schema outputs
```

**Step 4: Verify the plan now names all required surfaces**
Run: `rg -n "Unified Contract|Header fields|Parser event streams|Mechanics-required signals" docs/plans/2026-04-07-rlcoach-parser-full-vision-implementation.md`  
Expected: PASS with all sections present.

**Verification plan:**
- Primary command: `rg -n "Unified Contract|Parser event streams|Mechanics-required signals" docs/plans/2026-04-07-rlcoach-parser-full-vision-implementation.md`
- Secondary checks: manual review against `MECHANICS_SPEC.md` and `codex/Plans/2026-02-10-parser-refactor-update-plan.md`

---

### Task 1: Expand Parser Types and Report Schema for the Full Contract

**Parallel:** no  
**Blocked by:** Task 0  
**Owned files:** `src/rlcoach/parser/types.py`, `schemas/replay_report.schema.json`, `tests/test_parser_interface.py`, `tests/test_schema_validation.py`, `tests/test_schema_validation_hardening.py`  
**Invariants:** Existing serialized reports must remain backward-compatible where possible; new fields should be optional/null-safe during migration.  
**Out of scope:** Rust emission and normalization.

**Files:**
- Modify: `src/rlcoach/parser/types.py`
- Modify: `schemas/replay_report.schema.json`
- Modify: `tests/test_parser_interface.py`
- Modify: `tests/test_schema_validation.py`
- Modify: `tests/test_schema_validation_hardening.py`

**Step 1: Write the failing tests**
```python
def test_player_frame_supports_authoritative_false_semantics():
    from rlcoach.parser.types import PlayerFrame, Vec3, Rotation
    player = PlayerFrame(
        player_id="player_0",
        team=0,
        position=Vec3(0, 0, 17),
        velocity=Vec3(0, 0, 0),
        rotation=Rotation(0, 0, 0),
        boost_amount=33,
        is_jumping=False,
        is_dodging=False,
        is_double_jumping=False,
    )
    assert player.is_jumping is False


def test_network_frames_supports_parser_event_streams():
    from rlcoach.parser.types import FrameTouchEvent, FrameDemoEvent, FrameMarkerEvent
    assert FrameTouchEvent is not None
    assert FrameDemoEvent is not None
    assert FrameMarkerEvent is not None
```

```python
def test_schema_supports_parser_authoritative_outputs():
    report = make_minimal_report()
    report["quality"]["parser"]["network_diagnostics"]["attempted_backends"] = ["boxcars"]
    report["events"]["parser_markers"] = []
    validate_report(report)
```

**Step 2: Run tests to verify failure**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_parser_interface.py tests/test_schema_validation.py tests/test_schema_validation_hardening.py -q`  
Expected: FAIL due to missing types/schema fields.

**Step 3: Write minimal implementation**
```python
@dataclass(frozen=True)
class FrameTouchEvent:
    t: float
    player_id: str | None = None
    team: int | None = None
    ball_position: Vec3 | None = None
    ball_velocity: Vec3 | None = None
    player_position: Vec3 | None = None
    surface_hint: str | None = None


@dataclass(frozen=True)
class FrameDemoEvent:
    t: float
    victim_id: str | None = None
    attacker_id: str | None = None
    location: Vec3 | None = None


@dataclass(frozen=True)
class FrameMarkerEvent:
    t: float
    kind: str
    frame: int | None = None
    data: dict[str, Any] = field(default_factory=dict)
```

**Step 4: Extend schema for parser markers and complete mechanic surfaces**
```json
"parser_markers": {
  "type": "array",
  "items": { "$ref": "#/definitions/timelineEvent" }
}
```

**Step 5: Run tests to verify pass**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_parser_interface.py tests/test_schema_validation.py tests/test_schema_validation_hardening.py -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_parser_interface.py tests/test_schema_validation.py tests/test_schema_validation_hardening.py -q`
- Secondary checks: `rg -n "FrameTouchEvent|FrameDemoEvent|FrameMarkerEvent|parser_markers" src/rlcoach/parser/types.py schemas/replay_report.schema.json`

---

### Task 2: Complete Rust Header Extraction

**Parallel:** yes  
**Blocked by:** Task 1  
**Owned files:** `parsers/rlreplay_rust/src/lib.rs`, `tests/test_rust_adapter.py`, `tests/test_report_metadata.py`  
**Invariants:** Keep header parsing fast and header-only safe; do not regress current goal/highlight extraction.  
**Out of scope:** Network frame/event emission.

**Files:**
- Modify: `parsers/rlreplay_rust/src/lib.rs`
- Modify: `tests/test_rust_adapter.py`
- Modify: `tests/test_report_metadata.py`

**Step 1: Write the failing tests**
```python
def test_rust_header_exposes_match_metadata_fields():
    header = RustAdapter().parse_header(Path("testing_replay.replay"))
    assert hasattr(header, "match_guid")
    assert hasattr(header, "overtime")
    assert hasattr(header, "mutators")
```

**Step 2: Run test to verify failure**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_rust_adapter.py::test_rust_header_exposes_match_metadata_fields tests/test_report_metadata.py -q`  
Expected: FAIL because Rust header dict omits one or more fields.

**Step 3: Write minimal implementation**
```rust
if let Some(p) = find_prop(&properties, "MatchGUID") {
    if let Some(s) = p.as_string() {
        header.set_item("match_guid", s)?;
    }
}
```

**Step 4: Populate `overtime`, `mutators`, and any available started-at/build metadata**
```rust
header.set_item("overtime", inferred_overtime)?;
header.set_item("mutators", mutators_dict)?;
```

**Step 5: Run tests to verify pass**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_rust_adapter.py::test_rust_header_exposes_match_metadata_fields tests/test_report_metadata.py -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_rust_adapter.py::test_rust_header_exposes_match_metadata_fields tests/test_report_metadata.py -q`
- Secondary checks: `source .venv/bin/activate && python -m rlcoach.cli analyze testing_replay.replay --adapter rust --out /tmp/rlcoach-plan-check`

---

### Task 3: Upgrade Authoritative Per-Frame Player and Ball State Semantics

**Parallel:** yes  
**Blocked by:** Task 1  
**Owned files:** `parsers/rlreplay_rust/src/lib.rs`, `src/rlcoach/parser/rust_adapter.py`, `src/rlcoach/normalize.py`, `tests/test_normalize.py`, `tests/test_rust_adapter.py`, `tests/test_parser_interface.py`  
**Invariants:** Keep existing frame field names stable where already consumed by Python.  
**Out of scope:** Parser event streams.

**Files:**
- Modify: `parsers/rlreplay_rust/src/lib.rs`
- Modify: `src/rlcoach/parser/rust_adapter.py`
- Modify: `src/rlcoach/normalize.py`
- Modify: `tests/test_normalize.py`
- Modify: `tests/test_rust_adapter.py`
- Modify: `tests/test_parser_interface.py`

**Step 1: Write the failing tests**
```python
def test_component_flags_support_false_not_just_true_or_none():
    raw = [{
        "timestamp": 0.0,
        "ball": {"position": {"x":0,"y":0,"z":93.15}, "velocity": {"x":0,"y":0,"z":0}, "angular_velocity": {"x":0,"y":0,"z":0}},
        "players": [{
            "player_id": "player_0",
            "team": 0,
            "position": {"x":0,"y":0,"z":17},
            "velocity": {"x":0,"y":0,"z":0},
            "rotation": {"pitch":0,"yaw":0,"roll":0},
            "boost_amount": 33,
            "is_jumping": False,
            "is_dodging": False,
            "is_double_jumping": False,
        }],
    }]
    frames = build_timeline(Header(players=[]), raw)
    assert frames[0].players[0].is_jumping is False
```

**Step 2: Run test to verify failure**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_normalize.py::test_component_flags_support_false_not_just_true_or_none tests/test_rust_adapter.py -q`  
Expected: FAIL because inactive states are collapsed to `None`.

**Step 3: Write minimal implementation**
```rust
p.set_item("is_jumping", frame_jumping_actors.contains(&aid))?;
p.set_item("is_dodging", frame_dodging_actors.contains(&aid))?;
p.set_item("is_double_jumping", frame_double_jumping_actors.contains(&aid))?;
```

**Step 4: Preserve strict optional semantics in Python**
```python
if present and field_name in dataclass_fields:
    updates[field_name] = value
```

**Step 5: Run tests to verify pass**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_normalize.py tests/test_rust_adapter.py tests/test_parser_interface.py -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_normalize.py tests/test_rust_adapter.py tests/test_parser_interface.py -q`
- Secondary checks: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_analysis_new_modules.py::test_mechanics_prefers_authoritative_jump_flags_over_derivative_only -q`

---

### Task 4: Emit Parser-Authoritative Touch Stream

**Parallel:** no  
**Blocked by:** Tasks 1, 3  
**Owned files:** `parsers/rlreplay_rust/src/lib.rs`, `src/rlcoach/parser/types.py`, `src/rlcoach/normalize.py`, `src/rlcoach/events/touches.py`, `tests/test_events.py`, `tests/test_events_calibration_synthetic.py`, `tests/test_rust_adapter.py`  
**Invariants:** Keep heuristic touch detection available until parser touch coverage is corpus-proven.  
**Out of scope:** Demo/kickoff marker stream.

**Files:**
- Modify: `parsers/rlreplay_rust/src/lib.rs`
- Modify: `src/rlcoach/parser/types.py`
- Modify: `src/rlcoach/normalize.py`
- Modify: `src/rlcoach/events/touches.py`
- Modify: `tests/test_events.py`
- Modify: `tests/test_events_calibration_synthetic.py`
- Modify: `tests/test_rust_adapter.py`

**Step 1: Write the failing tests**
```python
def test_normalize_preserves_parser_touch_events():
    raw = [{
        "timestamp": 1.0,
        "ball": {...},
        "players": [],
        "touch_events": [{"t": 1.0, "player_id": "player_0", "team": 0}],
    }]
    frames = build_timeline(Header(players=[]), raw)
    assert getattr(frames[0], "touch_events", None)
```

```python
def test_detect_touches_prefers_parser_authority():
    touches = detect_touches(frames_with_parser_touch_events())
    assert len(touches) == 1
    assert touches[0].player_id == "player_0"
```

**Step 2: Run tests to verify failure**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_events.py tests/test_events_calibration_synthetic.py tests/test_rust_adapter.py -q`  
Expected: FAIL due to missing parser touch plumbing.

**Step 3: Write minimal implementation**
```rust
let touch_list = PyList::empty(py);
touch_dict.set_item("t", nf.time as f64)?;
touch_dict.set_item("player_id", format!("player_{}", idx))?;
f.set_item("touch_events", touch_list)?;
```

**Step 4: Teach normalization and touch detection to consume parser touch events first**
```python
if getattr(frame, "touch_events", None):
    return _touches_from_parser_events(frames)
return _touches_from_proximity_heuristics(frames)
```

**Step 5: Run tests to verify pass**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_events.py tests/test_events_calibration_synthetic.py tests/test_rust_adapter.py -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_events.py tests/test_events_calibration_synthetic.py tests/test_rust_adapter.py -q`
- Secondary checks: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_report_end_to_end.py -q`

---

### Task 5: Emit Parser-Authoritative Demo and Marker Streams

**Parallel:** yes  
**Blocked by:** Tasks 1, 3  
**Owned files:** `parsers/rlreplay_rust/src/lib.rs`, `src/rlcoach/parser/types.py`, `src/rlcoach/normalize.py`, `src/rlcoach/events/demos.py`, `src/rlcoach/events/goals.py`, `src/rlcoach/events/kickoffs.py`, `tests/test_events.py`, `tests/test_report_end_to_end.py`  
**Invariants:** Existing header-goal and heuristic kickoff logic must remain fallback-safe during migration.  
**Out of scope:** Mechanics consumption.

**Files:**
- Modify: `parsers/rlreplay_rust/src/lib.rs`
- Modify: `src/rlcoach/parser/types.py`
- Modify: `src/rlcoach/normalize.py`
- Modify: `src/rlcoach/events/demos.py`
- Modify: `src/rlcoach/events/goals.py`
- Modify: `src/rlcoach/events/kickoffs.py`
- Modify: `tests/test_events.py`
- Modify: `tests/test_report_end_to_end.py`

**Step 1: Write the failing tests**
```python
def test_detect_demos_prefers_parser_demo_events():
    demos = detect_demos(frames_with_parser_demo_events())
    assert demos[0].attacker == "player_1"
    assert demos[0].victim == "player_0"


def test_detect_kickoffs_accepts_parser_markers():
    kickoffs = detect_kickoffs(frames_with_parser_markers(), header)
    assert len(kickoffs) >= 1
```

**Step 2: Run tests to verify failure**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_events.py tests/test_report_end_to_end.py -q`  
Expected: FAIL due to missing parser marker streams.

**Step 3: Write minimal implementation**
```rust
f.set_item("demo_events", demo_list)?;
f.set_item("marker_events", marker_list)?;
```

**Step 4: Prefer parser authority downstream**
```python
if parser_demo_events:
    return _demos_from_parser_events(frames)
```

**Step 5: Run tests to verify pass**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_events.py tests/test_report_end_to_end.py -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_events.py tests/test_report_end_to_end.py -q`
- Secondary checks: `source .venv/bin/activate && python -m rlcoach.cli analyze testing_replay.replay --adapter rust --out /tmp/rlcoach-demo-marker-check`

---

### Task 6: Preserve Surface and Environment Contacts Needed for Advanced Mechanics

**Parallel:** yes  
**Blocked by:** Tasks 1, 3  
**Owned files:** `parsers/rlreplay_rust/src/lib.rs`, `src/rlcoach/parser/types.py`, `src/rlcoach/normalize.py`, `tests/test_normalize.py`, `tests/test_analysis_new_modules.py`  
**Invariants:** Keep current kinematic fields stable; add new fields additively.  
**Out of scope:** Rewriting mechanic algorithms yet.

**Files:**
- Modify: `parsers/rlreplay_rust/src/lib.rs`
- Modify: `src/rlcoach/parser/types.py`
- Modify: `src/rlcoach/normalize.py`
- Modify: `tests/test_normalize.py`
- Modify: `tests/test_analysis_new_modules.py`

**Step 1: Write the failing tests**
```python
def test_normalize_preserves_surface_contact_hints():
    raw = [{
        "timestamp": 0.0,
        "ball": {...},
        "players": [{
            "player_id": "player_0",
            "team": 0,
            "position": {"x":0,"y":0,"z":2040},
            "velocity": {"x":0,"y":0,"z":0},
            "rotation": {"pitch":0,"yaw":0,"roll":3.14},
            "boost_amount": 33,
            "surface_contact": "ceiling",
        }],
    }]
    frames = build_timeline(Header(players=[]), raw)
    assert getattr(frames[0].players[0], "surface_contact", None) == "ceiling"
```

**Step 2: Run tests to verify failure**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_normalize.py tests/test_analysis_new_modules.py -q`  
Expected: FAIL because `surface_contact`/contact hints do not exist.

**Step 3: Write minimal implementation**
```python
@dataclass(frozen=True)
class PlayerFrame:
    ...
    surface_contact: str | None = None
    wall_contact: bool | None = None
    ceiling_contact: bool | None = None
```

**Step 4: Emit and preserve these fields**
```rust
p.set_item("surface_contact", inferred_surface_contact)?;
```

**Step 5: Run tests to verify pass**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_normalize.py tests/test_analysis_new_modules.py -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_normalize.py tests/test_analysis_new_modules.py -q`
- Secondary checks: `rg -n "surface_contact|ceiling_contact|wall_contact" src/rlcoach/parser/types.py src/rlcoach/normalize.py parsers/rlreplay_rust/src/lib.rs`

---

### Task 7: Refactor Mechanics to Prefer Parser Authority End to End

**Parallel:** no  
**Blocked by:** Tasks 4, 5, 6  
**Owned files:** `src/rlcoach/analysis/mechanics.py`, `tests/test_analysis_new_modules.py`, `tests/test_events_calibration_synthetic.py`, `tests/fixtures/builders.py`  
**Invariants:** Existing heuristic fallbacks must continue working when parser authority is missing.  
**Out of scope:** Report/schema surfaces.

**Files:**
- Modify: `src/rlcoach/analysis/mechanics.py`
- Modify: `tests/test_analysis_new_modules.py`
- Modify: `tests/test_events_calibration_synthetic.py`
- Modify: `tests/fixtures/builders.py`

**Step 1: Write the failing tests**
```python
def test_flip_reset_prefers_parser_touch_context_over_proximity_only():
    frames = build_frames_with_parser_touch_and_surface_hints()
    result = analyze_mechanics(frames)
    assert result["per_player"]["player_0"]["flip_reset_count"] == 1


def test_ceiling_shot_prefers_parser_ceiling_contact_over_height_heuristic():
    frames = build_frames_with_authoritative_ceiling_contact()
    result = analyze_mechanics(frames)
    assert result["per_player"]["player_0"]["ceiling_shot_count"] == 1
```

**Step 2: Run tests to verify failure**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_analysis_new_modules.py tests/test_events_calibration_synthetic.py -q`  
Expected: FAIL because mechanics still rely primarily on kinematic heuristics.

**Step 3: Write minimal implementation**
```python
if parser_touch_events_available:
    touch_context = parser_touch_context[player_id]
else:
    touch_context = inferred_touch_context
```

**Step 4: Migrate mechanic groups in order**
- Phase A: jump/dodge/double-jump and fast aerial
- Phase B: flip reset, air roll, dribble, flick, musty
- Phase C: ceiling/wall/surface-dependent mechanics
- Phase D: redirect, double touch, skim, psycho

**Step 5: Run tests to verify pass**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_analysis_new_modules.py tests/test_events_calibration_synthetic.py -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_analysis_new_modules.py tests/test_events_calibration_synthetic.py -q`
- Secondary checks: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_report_end_to_end.py -q`

---

### Task 8: Finish Mechanics and Report Surface Completeness

**Parallel:** yes  
**Blocked by:** Tasks 1, 7  
**Owned files:** `src/rlcoach/analysis/mechanics.py`, `src/rlcoach/analysis/__init__.py`, `src/rlcoach/report.py`, `src/rlcoach/report_markdown.py`, `schemas/replay_report.schema.json`, `tests/test_report_end_to_end.py`, `tests/test_report_markdown.py`  
**Invariants:** Do not remove existing fields; extend outputs additively.  
**Out of scope:** Parser emission.

**Files:**
- Modify: `src/rlcoach/analysis/mechanics.py`
- Modify: `src/rlcoach/analysis/__init__.py`
- Modify: `src/rlcoach/report.py`
- Modify: `src/rlcoach/report_markdown.py`
- Modify: `schemas/replay_report.schema.json`
- Modify: `tests/test_report_end_to_end.py`
- Modify: `tests/test_report_markdown.py`

**Step 1: Write the failing tests**
```python
def test_report_surfaces_skim_and_psycho_counts():
    report = generate_report(Path("testing_replay.replay"), adapter_name="rust")
    mechanics = report["players"][0]["analysis"]["mechanics"]
    assert "skim_count" in mechanics
    assert "psycho_count" in mechanics


def test_team_mechanics_includes_advanced_counts():
    report = generate_report(Path("testing_replay.replay"), adapter_name="rust")
    assert "total_fast_aerials" in report["analysis"]["per_team"]["blue"]["mechanics"]
```

**Step 2: Run tests to verify failure**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_report_end_to_end.py tests/test_report_markdown.py -q`  
Expected: FAIL because report surfaces lag the implemented mechanic set.

**Step 3: Write minimal implementation**
```python
"skim_count": counts.get("skim", 0),
"psycho_count": counts.get("psycho", 0),
```

**Step 4: Expand team/report/markdown surfaces**
```python
return {
    "total_fast_aerials": ...,
    "total_flip_resets": ...,
    "total_ceiling_shots": ...,
}
```

**Step 5: Run tests to verify pass**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_report_end_to_end.py tests/test_report_markdown.py -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_report_end_to_end.py tests/test_report_markdown.py -q`
- Secondary checks: `rg -n "skim_count|psycho_count|total_fast_aerials|total_flip_resets" src/rlcoach/analysis src/rlcoach/report* schemas/replay_report.schema.json`

---

### Task 9: Make Events Fully Parser-First with Heuristic Fallback

**Parallel:** no  
**Blocked by:** Tasks 4, 5, 6  
**Owned files:** `src/rlcoach/events/touches.py`, `src/rlcoach/events/demos.py`, `src/rlcoach/events/goals.py`, `src/rlcoach/events/kickoffs.py`, `src/rlcoach/events/timeline.py`, `tests/test_events.py`, `tests/test_report_end_to_end.py`  
**Invariants:** Header-only and degraded parses must still produce sensible output.  
**Out of scope:** Mechanics internals.

**Files:**
- Modify: `src/rlcoach/events/touches.py`
- Modify: `src/rlcoach/events/demos.py`
- Modify: `src/rlcoach/events/goals.py`
- Modify: `src/rlcoach/events/kickoffs.py`
- Modify: `src/rlcoach/events/timeline.py`
- Modify: `tests/test_events.py`
- Modify: `tests/test_report_end_to_end.py`

**Step 1: Write the failing tests**
```python
def test_report_marks_authoritative_event_sources():
    report = generate_report(Path("testing_replay.replay"), adapter_name="rust")
    assert report["quality"]["parser"]["network_diagnostics"]["status"] in {"ok", "degraded", "unavailable"}
```

```python
def test_timeline_uses_parser_events_when_present():
    timeline = build_timeline(events_from_parser_first_fixture())
    assert timeline[0]["type"] == "KICKOFF"
```

**Step 2: Run tests to verify failure**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_events.py tests/test_report_end_to_end.py -q`  
Expected: FAIL due to missing parser-first event provenance.

**Step 3: Write minimal implementation**
```python
source = "parser" if parser_events_available else "heuristic"
```

**Step 4: Run tests to verify pass**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_events.py tests/test_report_end_to_end.py -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_events.py tests/test_report_end_to_end.py -q`
- Secondary checks: `source .venv/bin/activate && python -m rlcoach.cli report-md testing_replay.replay --out /tmp/rlcoach-parser-first-report --pretty`

---

### Task 10: Build a Full Mechanics Regression Suite

**Parallel:** yes  
**Blocked by:** Tasks 4, 6, 7, 8  
**Owned files:** `tests/test_analysis_new_modules.py`, `tests/fixtures/builders.py`, `tests/goldens/synthetic_small.json`, `tests/goldens/synthetic_small.md`, `tests/test_goldens.py`  
**Invariants:** Tests should be deterministic and synthetic-first; do not require large real replays for core regression coverage.  
**Out of scope:** Corpus-health and perf harness.

**Files:**
- Modify: `tests/test_analysis_new_modules.py`
- Modify: `tests/fixtures/builders.py`
- Modify: `tests/goldens/synthetic_small.json`
- Modify: `tests/goldens/synthetic_small.md`
- Modify: `tests/test_goldens.py`

**Step 1: Write failing tests for every advanced mechanic family**
```python
def test_fast_aerial_authoritative_case(): ...
def test_flip_reset_authoritative_case(): ...
def test_ceiling_shot_authoritative_case(): ...
def test_redirect_authoritative_case(): ...
def test_skim_authoritative_case(): ...
def test_psycho_authoritative_case(): ...
```

**Step 2: Run tests to verify gaps**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_analysis_new_modules.py tests/test_goldens.py -q`  
Expected: FAIL until builders/goldens reflect the full mechanic contract.

**Step 3: Add synthetic builders and golden expectations**
```python
def build_authoritative_ceiling_shot_sequence() -> list[Frame]:
    ...
```

**Step 4: Run tests to verify pass**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_analysis_new_modules.py tests/test_goldens.py -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_analysis_new_modules.py tests/test_goldens.py -q`
- Secondary checks: `source .venv/bin/activate && PYTHONPATH=src pytest tests/test_report_markdown.py -q`

---

### Task 11: Expand Parser Smoke, Corpus, and Coverage Gates

**Parallel:** yes  
**Blocked by:** Tasks 2, 3, 4, 5, 6, 10  
**Owned files:** `tests/parser/test_rust_adapter_smoke.py`, `tests/parser/test_rust_pad_registry.py`, `tests/test_benchmarks.py`, `tests/test_report_end_to_end.py`, `scripts/parser_corpus_health.py`, `codex/docs/master_status.md`  
**Invariants:** Corpus-health remains local-only; do not introduce remote dependencies.  
**Out of scope:** Feature implementation.

**Files:**
- Modify: `tests/parser/test_rust_adapter_smoke.py`
- Modify: `tests/parser/test_rust_pad_registry.py`
- Modify: `tests/test_benchmarks.py`
- Modify: `tests/test_report_end_to_end.py`
- Modify: `scripts/parser_corpus_health.py`
- Modify: `codex/docs/master_status.md`

**Step 1: Write the failing tests**
```python
def test_rust_adapter_smoke_includes_parser_event_streams():
    nf = get_adapter("rust").parse_network(Path("testing_replay.replay"))
    frame = nf.frames[0]
    assert "touch_events" in frame
    assert "marker_events" in frame
```

```python
def test_parser_corpus_health_reports_authoritative_event_coverage():
    result = run_health_fixture()
    assert "touch_event_coverage" in result
```

**Step 2: Run tests to verify failure**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/parser/test_rust_adapter_smoke.py tests/test_benchmarks.py tests/test_report_end_to_end.py -q`  
Expected: FAIL because corpus/smoke coverage does not yet measure new parser authority.

**Step 3: Extend smoke/corpus tooling**
```python
assert report["quality"]["parser"]["scorecard"]["usable_network_parse"] is True
assert report["quality"]["parser"]["network_diagnostics"]["attempted_backends"] == ["boxcars"]
```

**Step 4: Run tests to verify pass**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/parser/test_rust_adapter_smoke.py tests/test_benchmarks.py tests/test_report_end_to_end.py -q`  
Expected: PASS.

**Verification plan:**
- Primary command: `source .venv/bin/activate && PYTHONPATH=src pytest tests/parser/test_rust_adapter_smoke.py tests/test_benchmarks.py tests/test_report_end_to_end.py -q`
- Secondary checks: `source .venv/bin/activate && PYTHONPATH=src python scripts/parser_corpus_health.py --roots replays,Replay_files --json`

---

### Task 12: Refresh Parser and Operator Documentation to Match Reality

**Parallel:** yes  
**Blocked by:** Tasks 2 through 11  
**Owned files:** `docs/parser_adapter.md`, `README.md`, `docs/api.md`, `docs/user-guide.md`, `codex/docs/network-frames-integration-issue-report.md`  
**Invariants:** Docs must describe actual current behavior, fallback semantics, and real commands only.  
**Out of scope:** New product marketing or UI docs.

**Files:**
- Create: `docs/parser_adapter.md`
- Modify: `README.md`
- Modify: `docs/api.md`
- Modify: `docs/user-guide.md`
- Modify: `codex/docs/network-frames-integration-issue-report.md`

**Step 1: Write the failing docs assertions**
```bash
test -f docs/parser_adapter.md
rg -n "parse_network_with_diagnostics|debug_first_frames|boost_pad_events|touch_events" docs/parser_adapter.md README.md docs/api.md
```

**Step 2: Run checks to verify failure**
Run: `test -f docs/parser_adapter.md && rg -n "parse_network_with_diagnostics|debug_first_frames" docs/parser_adapter.md README.md docs/api.md`  
Expected: FAIL because `docs/parser_adapter.md` is missing or incomplete.

**Step 3: Write minimal implementation**
```markdown
## Rust Parser Contract
- Header parse
- Network diagnostics
- Frame/player/ball fields
- Parser event streams
- Fallback behavior
- Build commands
```

**Step 4: Run checks to verify pass**
Run: `test -f docs/parser_adapter.md && rg -n "parse_network_with_diagnostics|debug_first_frames|boost_pad_events|touch_events" docs/parser_adapter.md README.md docs/api.md`  
Expected: PASS.

**Verification plan:**
- Primary command: `test -f docs/parser_adapter.md && rg -n "parse_network_with_diagnostics|debug_first_frames|boost_pad_events|touch_events" docs/parser_adapter.md README.md docs/api.md`
- Secondary checks: manual read-through against actual `parsers/rlreplay_rust/src/lib.rs`

---

### Task 13: Final Integration Gate

**Parallel:** no  
**Blocked by:** Tasks 2 through 12  
**Owned files:** `parsers/rlreplay_rust/src/lib.rs`, `src/rlcoach/parser/*.py`, `src/rlcoach/normalize.py`, `src/rlcoach/events/*.py`, `src/rlcoach/analysis/*.py`, `src/rlcoach/report*.py`, `schemas/replay_report.schema.json`, `docs/parser_adapter.md`  
**Invariants:** No partial closeout; this task only passes when the full chain is green.  
**Out of scope:** Additional feature work after the agreed vision is complete.

**Files:**
- Verify only: parser, normalization, events, analysis, schema, docs, and tests touched above

**Step 1: Build the Rust extension**
Run: `make rust-dev`  
Expected: Rust core builds and `rlreplay_rust` imports successfully.

**Step 2: Run focused parser + downstream suites**
Run: `source .venv/bin/activate && PYTHONPATH=src pytest tests/parser/test_rust_adapter_smoke.py tests/test_rust_adapter.py tests/test_parser_interface.py tests/test_normalize.py tests/test_events.py tests/test_events_calibration_synthetic.py tests/test_analysis_new_modules.py tests/test_report_end_to_end.py tests/test_report_markdown.py tests/test_goldens.py tests/test_benchmarks.py -q`  
Expected: PASS.

**Step 3: Run repo gates**
Run: `make lint && make test-cov`  
Expected: PASS.

**Step 4: Run end-to-end CLI verification**
Run: `source .venv/bin/activate && python -m rlcoach.cli report-md testing_replay.replay --out /tmp/rlcoach-final-plan-check --pretty`  
Expected: both `.json` and `.md` are produced without contract errors.

**Step 5: Run corpus-health gate**
Run: `source .venv/bin/activate && PYTHONPATH=src python scripts/parser_corpus_health.py --roots replays,Replay_files --json`  
Expected: parser success remains at or above the existing reliability gate and new event-authority coverage metrics are populated.

**Verification plan:**
- Primary command: `make lint && make test-cov`
- Secondary checks:
  - `source .venv/bin/activate && PYTHONPATH=src pytest tests/parser/test_rust_adapter_smoke.py tests/test_report_end_to_end.py -q`
  - `source .venv/bin/activate && python -m rlcoach.cli report-md testing_replay.replay --out /tmp/rlcoach-final-plan-check --pretty`

---

## Parallel Execution Map

- After Task 1:
  - Task 2
  - Task 3
- After Tasks 1 and 3:
  - Task 5
  - Task 6
- After Tasks 2 through 6:
  - Task 8
  - Task 10
  - Task 11
  - Task 12
- Sequential anchors:
  - Task 4 before Task 7
  - Task 7 before Task 8
  - Task 13 last

## Owned Files Validation

Run before parallel implementation:

```bash
rg '\*\*Owned files:\*\*' docs/plans/2026-04-07-rlcoach-parser-full-vision-implementation.md \
  | sed 's/.*\*\*Owned files:\*\* *//' \
  | tr ',' '\n' \
  | sed 's/`//g' \
  | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' \
  | rg -v '^$' \
  | sort \
  | uniq -d
```

Expected: no output before parallel ticket execution.

## Recommended Execution Order

1. Land Task 1 alone.
2. Land Tasks 2 and 3.
3. Land Tasks 4, 5, and 6 in the correct dependency order.
4. Land Task 7 as the parser-authority mechanics pivot.
5. Land Tasks 8, 10, 11, and 12.
6. Run Task 13 and only then close the initiative.

## Execution Handoff Options

1. Execute sequentially in this session.
2. Execute in a new worktree after Task 1 lands cleanly.
3. Split Tasks 2, 3, 5, 6, 8, 10, 11, and 12 into parallel tickets after a `plan_checker` review.
