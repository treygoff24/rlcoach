#![allow(deprecated)]
//! PyO3 boundary for `rlinput`.
//!
//! WP8 intentionally exposes the stable boundary before WP7's full fit solver
//! exists. `solve_timeline` accepts the final columnar payload shape and returns
//! a real `SolveOutput` assembled from the contracts that already landed:
//! contact-free segmentation plus seeded component-edge reconstruction. Samples
//! are empty until fit/channel solving lands; segment confidence is structurally
//! set to 1.0 so coverage reports count the current segmentation denominator
//! honestly.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyAny, PyDict, PyList};
use rlinput::model::{
    BallSeries, ComponentEventIn, ComponentKind, ComponentStream, DemoEventIn, Kinematics,
    PlayerSeries, ReplaySeries, ReplicatedChannels, TouchEventIn,
};
use rlinput::segment::segment_replay_with_confidences;
use rlinput::timeline::{
    AmbiguityFlags, BoundaryCause, CancelSummary, CoverageReport, ExclusionBreakdown,
    InputTimeline, LatticeDiagnostic, SegmentSummary, SolveDiagnostics, SolveOutput, SolvedEvent,
    SolvedEventKind,
};
use rlinput::tracker::{
    classify_dodge_torque_vector, reconstruct_seeded_edges, EdgeEvidence, ReconstructedEdge,
    SecondActionClass,
};

#[pyfunction]
fn solve_timeline(py: Python<'_>, payload: &PyAny, _config: Option<&PyAny>) -> PyResult<PyObject> {
    let payload = payload.downcast::<PyDict>()?;
    let series = parse_replay_series(payload)?;
    let output = solve_series(&series);
    solve_output_to_py(py, &output)
}

fn solve_series(series: &ReplaySeries) -> SolveOutput {
    let segmentation =
        segment_replay_with_confidences(series, 0.7, |_player_id, _segment| Some(1.0));
    let frame_times = frame_times(series);

    let timelines = segmentation
        .players
        .iter()
        .map(|segmented_player| {
            let events = series
                .players
                .iter()
                .find(|player| player.player_id == segmented_player.player_id)
                .map(|player| solved_events_for_player(player, &frame_times, series.tick_rate))
                .unwrap_or_default();
            InputTimeline {
                player_id: segmented_player.player_id.clone(),
                samples: Vec::new(),
                events,
                segments: segmented_player
                    .segments
                    .iter()
                    .map(|segment| segment.summary.clone())
                    .collect(),
            }
        })
        .collect();

    let mut nonstandard_cadence = false;
    let mut lattice = Vec::new();
    for player in &segmentation.players {
        for segment in &player.segments {
            let diagnostics = &segment.lattice.diagnostics;
            if diagnostics.nonstandard_cadence {
                nonstandard_cadence = true;
                lattice.push(LatticeDiagnostic {
                    kind: "nonstandard_cadence".to_string(),
                    first_frame_index: diagnostics.first_nonstandard_frame.unwrap_or(0),
                    count: 1,
                });
            }
        }
    }

    SolveOutput {
        timelines,
        coverage: segmentation.coverage,
        diagnostics: SolveDiagnostics {
            nonstandard_cadence,
            lattice,
            warnings: vec!["wp8_boundary_only_samples_omitted_until_wp7_solver".to_string()],
        },
    }
}

fn solved_events_for_player(
    player: &PlayerSeries,
    frame_times: &[f64],
    tick_rate: f64,
) -> Vec<SolvedEvent> {
    reconstruct_seeded_edges(&player.component)
        .into_iter()
        .filter_map(|edge| solved_event_from_edge(edge, frame_times, tick_rate))
        .collect()
}

fn solved_event_from_edge(
    edge: ReconstructedEdge,
    frame_times: &[f64],
    tick_rate: f64,
) -> Option<SolvedEvent> {
    if edge.component == ComponentKind::Boost {
        return None;
    }

    let t = if edge.t > 0.0 {
        edge.t
    } else {
        frame_times
            .get(edge.frame_index as usize)
            .copied()
            .unwrap_or(0.0)
    };
    let mut flags = AmbiguityFlags::empty();
    let confidence = match edge.source {
        EdgeEvidence::VectorEvent => 1.0,
        EdgeEvidence::RawCounter => {
            if edge
                .counter_delta
                .as_ref()
                .is_some_and(|delta| delta.has_subframe_toggles)
            {
                flags |= AmbiguityFlags::LOW_MARGIN;
                0.5
            } else {
                0.75
            }
        }
    };
    let kind = match edge.component {
        ComponentKind::Jump => {
            if edge
                .counter_delta
                .as_ref()
                .is_some_and(|delta| delta.current % 2 == 0)
            {
                SolvedEventKind::JumpRelease
            } else {
                SolvedEventKind::JumpPress
            }
        }
        ComponentKind::DoubleJumpImpulse => SolvedEventKind::DoubleJump,
        ComponentKind::DodgeTorque => match edge.vector {
            Some(vector) => match classify_dodge_torque_vector(vector) {
                SecondActionClass::Dodge { dir, .. } => SolvedEventKind::Dodge {
                    dir,
                    cancel: empty_cancel(),
                },
                SecondActionClass::Stall => SolvedEventKind::Stall,
                SecondActionClass::DoubleJump => SolvedEventKind::DoubleJump,
            },
            None => {
                flags |= AmbiguityFlags::LOW_MARGIN;
                SolvedEventKind::Dodge {
                    dir: [0.0, 0.0],
                    cancel: empty_cancel(),
                }
            }
        },
        ComponentKind::Boost => return None,
    };

    Some(SolvedEvent {
        kind,
        tick: (t * tick_rate).round().max(0.0) as u64,
        t,
        frame_index: edge.frame_index,
        confidence,
        flags,
    })
}

fn empty_cancel() -> CancelSummary {
    CancelSummary {
        onset_tick: None,
        peak_pitch: 0.0,
        full_cancel: false,
    }
}

fn parse_replay_series(payload: &PyDict) -> PyResult<ReplaySeries> {
    Ok(ReplaySeries {
        tick_rate: optional_extract(payload, "tick_rate")?.unwrap_or(120.0),
        build_bucket: optional_extract(payload, "build_bucket")?
            .unwrap_or_else(|| "unknown".to_string()),
        players: parse_players(required_list(payload, "players")?)?,
        ball: parse_ball(required_dict(payload, "ball")?)?,
        deltas: required(payload, "deltas")?.extract()?,
        demo_events: parse_demo_events(required_list(payload, "demo_events")?)?,
        touch_events: parse_touch_events(required_list(payload, "touch_events")?)?,
        kickoff_markers: parse_kickoff_markers(required_list(payload, "kickoff_markers")?)?,
    })
}

fn parse_players(items: &PyList) -> PyResult<Vec<PlayerSeries>> {
    items
        .iter()
        .map(|item| {
            let item = item.downcast::<PyDict>()?;
            let player = PlayerSeries {
                player_id: required(item, "player_id")?.extract()?,
                frames: parse_kinematics(required_dict(item, "frames")?)?,
                replicated: parse_replicated(required_dict(item, "replicated")?)?,
                component: parse_component_stream(required_dict(item, "component")?)?,
            };
            validate_player_lengths(&player)?;
            Ok(player)
        })
        .collect()
}

fn parse_ball(ball: &PyDict) -> PyResult<BallSeries> {
    Ok(BallSeries {
        pos: flat_vec3(required(ball, "pos")?, "ball.pos")?,
        vel: flat_vec3(required(ball, "vel")?, "ball.vel")?,
    })
}

fn parse_kinematics(frames: &PyDict) -> PyResult<Kinematics> {
    Ok(Kinematics {
        pos: flat_vec3(required(frames, "pos")?, "frames.pos")?,
        vel: flat_vec3(required(frames, "vel")?, "frames.vel")?,
        quat_xyzw: flat_quat(required(frames, "quat_xyzw")?, "frames.quat_xyzw")?,
        ang_vel: flat_vec3(required(frames, "ang_vel")?, "frames.ang_vel")?,
        on_ground: required(frames, "on_ground")?.extract()?,
        sleeping: required(frames, "sleeping")?.extract()?,
        demolished: required(frames, "demolished")?.extract()?,
    })
}

fn parse_replicated(replicated: &PyDict) -> PyResult<ReplicatedChannels> {
    Ok(ReplicatedChannels {
        throttle_raw: required(replicated, "throttle_raw")?.extract()?,
        steer_raw: required(replicated, "steer_raw")?.extract()?,
        handbrake: required(replicated, "handbrake")?.extract()?,
        boost_amount_raw: required(replicated, "boost_amount_raw")?.extract()?,
        boost_active_raw: required(replicated, "boost_active_raw")?.extract()?,
    })
}

fn parse_component_stream(component: &PyDict) -> PyResult<ComponentStream> {
    Ok(ComponentStream {
        jump_raw: required(component, "jump_raw")?.extract()?,
        dodge_raw: required(component, "dodge_raw")?.extract()?,
        double_jump_raw: required(component, "double_jump_raw")?.extract()?,
        boost_raw: required(component, "boost_raw")?.extract()?,
        events: parse_component_events(required_list(component, "events")?)?,
    })
}

fn parse_component_events(items: &PyList) -> PyResult<Vec<ComponentEventIn>> {
    items
        .iter()
        .map(|item| {
            let item = item.downcast::<PyDict>()?;
            Ok(ComponentEventIn {
                t: required(item, "t")?.extract()?,
                frame_index: required(item, "frame_index")?.extract()?,
                component: parse_component_kind(required(item, "component")?.extract()?)?,
                vector: optional_flat_vec3(item, "vector")?,
                raw_value: optional_extract(item, "raw_value")?,
            })
        })
        .collect()
}

fn parse_demo_events(items: &PyList) -> PyResult<Vec<DemoEventIn>> {
    items
        .iter()
        .map(|item| {
            let item = item.downcast::<PyDict>()?;
            Ok(DemoEventIn {
                t: required(item, "t")?.extract()?,
                frame_index: optional_extract(item, "frame_index")?,
                victim_id: required(item, "victim_id")?.extract()?,
                attacker_id: optional_extract(item, "attacker_id")?,
            })
        })
        .collect()
}

fn parse_touch_events(items: &PyList) -> PyResult<Vec<TouchEventIn>> {
    items
        .iter()
        .map(|item| {
            let item = item.downcast::<PyDict>()?;
            Ok(TouchEventIn {
                t: required(item, "t")?.extract()?,
                frame_index: optional_extract(item, "frame_index")?,
                player_id: required(item, "player_id")?.extract()?,
                team: optional_extract(item, "team")?,
            })
        })
        .collect()
}

fn parse_kickoff_markers(items: &PyList) -> PyResult<Vec<rlinput::model::KickoffMarkerIn>> {
    items
        .iter()
        .map(|item| {
            let item = item.downcast::<PyDict>()?;
            Ok(rlinput::model::KickoffMarkerIn {
                t: required(item, "t")?.extract()?,
                frame_index: optional_extract(item, "frame_index")?,
                phase: required(item, "phase")?.extract()?,
            })
        })
        .collect()
}

fn parse_component_kind(value: String) -> PyResult<ComponentKind> {
    match value.as_str() {
        "Jump" => Ok(ComponentKind::Jump),
        "DodgeTorque" => Ok(ComponentKind::DodgeTorque),
        "DoubleJumpImpulse" => Ok(ComponentKind::DoubleJumpImpulse),
        "Boost" => Ok(ComponentKind::Boost),
        _ => Err(PyValueError::new_err(format!(
            "unknown component kind: {value}"
        ))),
    }
}

fn validate_player_lengths(player: &PlayerSeries) -> PyResult<()> {
    let frame_len = player.frames.pos.len();
    let lengths = [
        ("frames.vel", player.frames.vel.len()),
        ("frames.quat_xyzw", player.frames.quat_xyzw.len()),
        ("frames.ang_vel", player.frames.ang_vel.len()),
        ("frames.on_ground", player.frames.on_ground.len()),
        ("frames.sleeping", player.frames.sleeping.len()),
        ("frames.demolished", player.frames.demolished.len()),
        (
            "replicated.throttle_raw",
            player.replicated.throttle_raw.len(),
        ),
        ("replicated.steer_raw", player.replicated.steer_raw.len()),
        ("replicated.handbrake", player.replicated.handbrake.len()),
        (
            "replicated.boost_amount_raw",
            player.replicated.boost_amount_raw.len(),
        ),
        (
            "replicated.boost_active_raw",
            player.replicated.boost_active_raw.len(),
        ),
        ("component.jump_raw", player.component.jump_raw.len()),
        ("component.dodge_raw", player.component.dodge_raw.len()),
        (
            "component.double_jump_raw",
            player.component.double_jump_raw.len(),
        ),
        ("component.boost_raw", player.component.boost_raw.len()),
    ];
    for (name, len) in lengths {
        if len != frame_len {
            return Err(PyValueError::new_err(format!(
                "{} length {} did not match frames.pos length {} for {}",
                name, len, frame_len, player.player_id
            )));
        }
    }
    Ok(())
}

fn flat_vec3(value: &PyAny, field: &str) -> PyResult<Vec<[f32; 3]>> {
    let flat: Vec<f32> = value.extract()?;
    if !flat.len().is_multiple_of(3) {
        return Err(PyValueError::new_err(format!(
            "{field} length must be a multiple of 3"
        )));
    }
    Ok(flat
        .chunks_exact(3)
        .map(|chunk| [chunk[0], chunk[1], chunk[2]])
        .collect())
}

fn optional_flat_vec3(dict: &PyDict, key: &str) -> PyResult<Option<[f32; 3]>> {
    let Some(value) = dict.get_item(key)? else {
        return Ok(None);
    };
    if value.is_none() {
        return Ok(None);
    }
    let values = flat_vec3(value, key)?;
    Ok(values.into_iter().next())
}

fn flat_quat(value: &PyAny, field: &str) -> PyResult<Vec<[f32; 4]>> {
    let flat: Vec<f32> = value.extract()?;
    if !flat.len().is_multiple_of(4) {
        return Err(PyValueError::new_err(format!(
            "{field} length must be a multiple of 4"
        )));
    }
    Ok(flat
        .chunks_exact(4)
        .map(|chunk| [chunk[0], chunk[1], chunk[2], chunk[3]])
        .collect())
}

fn frame_times(series: &ReplaySeries) -> Vec<f64> {
    let frame_count = series
        .players
        .iter()
        .map(|player| player.frames.pos.len())
        .max()
        .unwrap_or(series.deltas.len());
    let mut out = vec![0.0; frame_count];
    for frame in 1..frame_count {
        out[frame] = out[frame - 1] + f64::from(delta_for(series, frame));
    }
    out
}

fn delta_for(series: &ReplaySeries, terminating_frame: usize) -> f32 {
    if series.deltas.len() > terminating_frame {
        series.deltas[terminating_frame]
    } else if terminating_frame > 0 && series.deltas.len() >= terminating_frame {
        series.deltas[terminating_frame - 1]
    } else {
        0.0
    }
}

fn required<'py>(dict: &'py PyDict, key: &str) -> PyResult<&'py PyAny> {
    dict.get_item(key)?
        .ok_or_else(|| PyValueError::new_err(format!("missing required key: {key}")))
}

fn required_dict<'py>(dict: &'py PyDict, key: &str) -> PyResult<&'py PyDict> {
    Ok(required(dict, key)?.downcast::<PyDict>()?)
}

fn required_list<'py>(dict: &'py PyDict, key: &str) -> PyResult<&'py PyList> {
    Ok(required(dict, key)?.downcast::<PyList>()?)
}

fn optional_extract<T>(dict: &PyDict, key: &str) -> PyResult<Option<T>>
where
    for<'a> T: FromPyObject<'a>,
{
    let Some(value) = dict.get_item(key)? else {
        return Ok(None);
    };
    if value.is_none() {
        Ok(None)
    } else {
        value.extract().map(Some)
    }
}

fn solve_output_to_py(py: Python<'_>, output: &SolveOutput) -> PyResult<PyObject> {
    let out = PyDict::new(py);
    let timelines = PyList::empty(py);
    for timeline in &output.timelines {
        timelines.append(timeline_to_py(py, timeline)?)?;
    }
    out.set_item("timelines", timelines)?;
    out.set_item("coverage", coverage_to_py(py, &output.coverage)?)?;
    out.set_item("diagnostics", diagnostics_to_py(py, &output.diagnostics)?)?;
    Ok(out.into())
}

fn timeline_to_py(py: Python<'_>, timeline: &InputTimeline) -> PyResult<PyObject> {
    let out = PyDict::new(py);
    out.set_item("player_id", &timeline.player_id)?;
    out.set_item("samples", PyList::empty(py))?;
    let events = PyList::empty(py);
    for event in &timeline.events {
        events.append(event_to_py(py, event)?)?;
    }
    out.set_item("events", events)?;
    let segments = PyList::empty(py);
    for segment in &timeline.segments {
        segments.append(segment_to_py(py, segment)?)?;
    }
    out.set_item("segments", segments)?;
    Ok(out.into())
}

fn event_to_py(py: Python<'_>, event: &SolvedEvent) -> PyResult<PyObject> {
    let out = PyDict::new(py);
    let (kind, detail) = event_kind_to_py(py, &event.kind)?;
    out.set_item("kind", kind)?;
    out.set_item("detail", detail)?;
    out.set_item("tick", event.tick)?;
    out.set_item("t", event.t)?;
    out.set_item("frame_index", event.frame_index)?;
    out.set_item("confidence", event.confidence)?;
    out.set_item("flags", event.flags.bits())?;
    Ok(out.into())
}

fn event_kind_to_py(py: Python<'_>, kind: &SolvedEventKind) -> PyResult<(&'static str, PyObject)> {
    let detail = PyDict::new(py);
    let name = match kind {
        SolvedEventKind::JumpPress => "JumpPress",
        SolvedEventKind::JumpRelease => "JumpRelease",
        SolvedEventKind::DoubleJump => "DoubleJump",
        SolvedEventKind::Stall => "Stall",
        SolvedEventKind::Liftoff => "Liftoff",
        SolvedEventKind::Landing => "Landing",
        SolvedEventKind::Dodge { dir, cancel } => {
            detail.set_item("dir", vec![dir[0], dir[1]])?;
            let cancel_py = PyDict::new(py);
            cancel_py.set_item("onset_tick", cancel.onset_tick)?;
            cancel_py.set_item("peak_pitch", cancel.peak_pitch)?;
            cancel_py.set_item("full_cancel", cancel.full_cancel)?;
            detail.set_item("cancel", cancel_py)?;
            "Dodge"
        }
    };
    Ok((name, detail.into()))
}

fn segment_to_py(py: Python<'_>, segment: &SegmentSummary) -> PyResult<PyObject> {
    let out = PyDict::new(py);
    out.set_item("id", segment.id)?;
    out.set_item("tick_span", vec![segment.tick_span.0, segment.tick_span.1])?;
    out.set_item(
        "boundary_causes",
        segment
            .boundary_causes
            .iter()
            .map(cause_name)
            .collect::<Vec<_>>(),
    )?;
    out.set_item("confidence", segment.confidence)?;
    Ok(out.into())
}

fn coverage_to_py(py: Python<'_>, coverage: &CoverageReport) -> PyResult<PyObject> {
    let out = PyDict::new(py);
    out.set_item("air_segments", coverage.air_segments)?;
    out.set_item("air_segments_confident", coverage.air_segments_confident)?;
    out.set_item("coverage", coverage.coverage)?;
    out.set_item(
        "duration_weighted_coverage",
        coverage.duration_weighted_coverage,
    )?;
    let excluded = PyList::empty(py);
    for item in &coverage.excluded_player_seconds_by_cause {
        excluded.append(exclusion_to_py(py, item)?)?;
    }
    out.set_item("excluded_player_seconds_by_cause", excluded)?;
    Ok(out.into())
}

fn exclusion_to_py(py: Python<'_>, item: &ExclusionBreakdown) -> PyResult<PyObject> {
    let out = PyDict::new(py);
    out.set_item("cause", cause_name(&item.cause))?;
    out.set_item("player_seconds", item.player_seconds)?;
    Ok(out.into())
}

fn diagnostics_to_py(py: Python<'_>, diagnostics: &SolveDiagnostics) -> PyResult<PyObject> {
    let out = PyDict::new(py);
    out.set_item("nonstandard_cadence", diagnostics.nonstandard_cadence)?;
    let lattice = PyList::empty(py);
    for item in &diagnostics.lattice {
        let item_py = PyDict::new(py);
        item_py.set_item("kind", &item.kind)?;
        item_py.set_item("first_frame_index", item.first_frame_index)?;
        item_py.set_item("count", item.count)?;
        lattice.append(item_py)?;
    }
    out.set_item("lattice", lattice)?;
    out.set_item("warnings", diagnostics.warnings.clone())?;
    Ok(out.into())
}

fn cause_name(cause: &BoundaryCause) -> &'static str {
    match cause {
        BoundaryCause::BallTouch => "BallTouch",
        BoundaryCause::BallProximity => "BallProximity",
        BoundaryCause::CarContactSuspected => "CarContactSuspected",
        BoundaryCause::Demolition => "Demolition",
        BoundaryCause::Respawn => "Respawn",
        BoundaryCause::KickoffReset => "KickoffReset",
        BoundaryCause::Liftoff => "Liftoff",
        BoundaryCause::Landing => "Landing",
        BoundaryCause::SurfaceProximity => "SurfaceProximity",
        BoundaryCause::StreamEdge => "StreamEdge",
    }
}

#[pymodule]
fn rlinput_py(_py: Python<'_>, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(solve_timeline, m)?)?;
    m.add("RUST_CORE", true)?;
    m.add(
        "__doc__",
        "PyO3 boundary for rlinput input timeline solving",
    )?;
    pyo3::prepare_freethreaded_python();
    Ok(())
}
