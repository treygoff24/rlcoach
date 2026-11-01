mod arena_tables;
mod pads;

use pyo3::exceptions::{PyIOError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet};
use std::fs::File;
use std::io::Read;

use boxcars::{Attribute, NewActor, Vector3f};
use boxcars::{HeaderProp, ParserBuilder, Replay};

use pads::{PadEvent, PadRegistry};

const KICKOFF_POSITION_TOLERANCE: f64 = 120.0;
const BALL_REST_HEIGHT: f64 = 93.15;
const BALL_STATIONARY_SPEED: f64 = 60.0;

const TOUCH_PROXIMITY_THRESHOLD: f32 = 200.0; // Distance for player-ball contact (units)
const TOUCH_DEBOUNCE_TIME: f64 = 0.2; // Seconds between touches to count as new
const TOUCH_LOCATION_EPS: f32 = 120.0; // Distance to consider same location

fn infer_kickoff_phase(timestamp: f64, overtime: bool, match_length: f64) -> &'static str {
    let overtime_boundary = match_length.max(300.0);
    if overtime && timestamp >= overtime_boundary {
        "OT"
    } else {
        "INITIAL"
    }
}

/// Compute Euclidean distance between two 3D points
fn distance_3d((ax, ay, az): (f32, f32, f32), (bx, by, bz): (f32, f32, f32)) -> f32 {
    let dx = ax - bx;
    let dy = ay - by;
    let dz = az - bz;
    (dx * dx + dy * dy + dz * dz).sqrt()
}

fn bind_player_index(
    actor_to_player_index: &mut HashMap<i32, usize>,
    next_by_team: &mut HashMap<i64, Vec<usize>>,
    actor_id: i32,
    player_index: usize,
) {
    for queue in next_by_team.values_mut() {
        queue.retain(|candidate| *candidate != player_index);
    }
    actor_to_player_index.retain(|existing_actor, existing_index| {
        *existing_actor == actor_id || *existing_index != player_index
    });
    actor_to_player_index.insert(actor_id, player_index);
}

fn pop_available_player_index(
    actor_to_player_index: &HashMap<i32, usize>,
    next_by_team: &mut HashMap<i64, Vec<usize>>,
    team: i64,
) -> Option<usize> {
    let assigned_indices: HashSet<usize> = actor_to_player_index.values().copied().collect();
    let queue = next_by_team.get_mut(&team)?;
    while !queue.is_empty() {
        let candidate = queue.remove(0);
        if !assigned_indices.contains(&candidate) {
            return Some(candidate);
        }
    }
    None
}

fn unique_header_index_by_name(
    header_players: &[(String, i64)],
    player_name: &str,
) -> Option<usize> {
    let mut matches = header_players
        .iter()
        .enumerate()
        .filter_map(|(idx, (name, _team))| (name == player_name).then_some(idx));
    let first = matches.next()?;
    matches.next().is_none().then_some(first)
}

/// Flatten a boxcars `CamSettings` into ordered (key, value) pairs for emission.
///
/// The `swivel`/`transition` fields are surfaced under the more descriptive
/// `swivel_speed`/`transition_speed` keys to match the Python-facing contract.
/// `transition` is optional in the network stream and defaults to `0.0`.
fn cam_settings_pairs(cam: &boxcars::CamSettings) -> [(&'static str, f64); 7] {
    [
        ("fov", cam.fov as f64),
        ("height", cam.height as f64),
        ("angle", cam.angle as f64),
        ("distance", cam.distance as f64),
        ("stiffness", cam.stiffness as f64),
        ("swivel_speed", cam.swivel as f64),
        ("transition_speed", cam.transition.unwrap_or(0.0) as f64),
    ]
}

/// Flatten a boxcars `Loadout` into ordered (slot, product_id) pairs.
///
/// The six mandatory cosmetic slots are always present; the optional slots are
/// only emitted when the network stream carried a value for them.
fn loadout_pairs(loadout: &boxcars::Loadout) -> Vec<(&'static str, u32)> {
    let mut pairs = vec![
        ("body", loadout.body),
        ("decal", loadout.decal),
        ("wheels", loadout.wheels),
        ("rocket_trail", loadout.rocket_trail),
        ("antenna", loadout.antenna),
        ("topper", loadout.topper),
    ];
    if let Some(value) = loadout.engine_audio {
        pairs.push(("engine_audio", value));
    }
    if let Some(value) = loadout.trail {
        pairs.push(("trail", value));
    }
    if let Some(value) = loadout.goal_explosion {
        pairs.push(("goal_explosion", value));
    }
    if let Some(value) = loadout.banner {
        pairs.push(("banner", value));
    }
    if let Some(value) = loadout.product_id {
        pairs.push(("product_id", value));
    }
    pairs
}

/// Choose the player's own loadout from a `TeamLoadout`, preferring the team the
/// player is bound to. Team `1` is orange; everything else falls back to blue.
fn team_loadout_for(team: Option<i64>, team_loadout: &boxcars::TeamLoadout) -> boxcars::Loadout {
    match team {
        Some(1) => team_loadout.orange,
        _ => team_loadout.blue,
    }
}

#[derive(Clone, Default)]
struct ActorKind {
    is_ball: bool,
    is_car: bool,
}

#[derive(Clone, Copy, Default)]
struct ComponentKind {
    is_jump: bool,
    is_dodge: bool,
    is_double_jump: bool,
    is_boost: bool,
    is_air_activate: bool,
}

#[derive(Clone)]
struct ComponentEvent {
    owner_actor_id: i32,
    kind: &'static str,
    component: &'static str,
    vector: Option<(f32, f32, f32)>,
    raw_value: Option<i64>,
    active: Option<bool>,
}

#[derive(Clone)]
struct ParserStatEvent {
    object_id: i32,
    object_name: Option<String>,
    unknown1: bool,
}

fn component_label(component: &ComponentKind) -> Option<&'static str> {
    if component.is_jump {
        Some("jump")
    } else if component.is_dodge {
        Some("dodge")
    } else if component.is_double_jump {
        Some("double_jump")
    } else if component.is_boost {
        Some("boost")
    } else if component.is_air_activate {
        Some("air_activate")
    } else {
        None
    }
}

fn is_car_state_actor(
    actor_id: i32,
    actor_kind: &HashMap<i32, ActorKind>,
    car_team: &HashMap<i32, i64>,
    car_owner: &HashMap<i32, i32>,
    component_owner: &HashMap<i32, i32>,
    actor_to_player_index: &HashMap<i32, usize>,
) -> bool {
    if actor_kind
        .get(&actor_id)
        .map(|kind| kind.is_ball)
        .unwrap_or(false)
    {
        return false;
    }

    actor_kind
        .get(&actor_id)
        .map(|kind| kind.is_car)
        .unwrap_or(false)
        || car_team.contains_key(&actor_id)
        || car_owner.contains_key(&actor_id)
        || component_owner.values().any(|owner| *owner == actor_id)
        || actor_to_player_index.contains_key(&actor_id)
}

fn resolve_component_owner(component_owner: &HashMap<i32, i32>, actor_id: i32) -> i32 {
    let mut resolved = actor_id;
    let mut guard = 0;
    while let Some(owner) = component_owner.get(&resolved) {
        if *owner == resolved {
            break;
        }
        resolved = *owner;
        guard += 1;
        if guard > 8 {
            break;
        }
    }
    resolved
}

fn pickup_bool_raw_state(picked_up: bool) -> u8 {
    u8::from(picked_up)
}

fn angular_velocity_to_radians(ang: Vector3f) -> (f32, f32, f32) {
    (ang.x / 100.0, ang.y / 100.0, ang.z / 100.0)
}

fn normalize_input_byte(raw: u8) -> f64 {
    (((raw as f64) - 128.0) / 127.0).clamp(-1.0, 1.0)
}

fn read_file_bytes(path: &str) -> PyResult<Vec<u8>> {
    let mut file = File::open(path)
        .map_err(|e| PyIOError::new_err(format!("Failed to open replay file '{}': {}", path, e)))?;
    let mut buf = Vec::new();
    file.read_to_end(&mut buf)
        .map_err(|e| PyIOError::new_err(format!("Failed to read replay file '{}': {}", path, e)))?;
    Ok(buf)
}

fn looks_like_replay_header(bytes: &[u8]) -> bool {
    let needles: [&[u8]; 3] = [
        b"TAGame.Replay_Soccar_TA",
        b"TAGame.Replay_",
        b"\x00\x00\x00\x00\x08\x00\x00\x00TAGame",
    ];
    let head = if bytes.len() > 2048 {
        &bytes[..2048]
    } else {
        bytes
    };
    needles
        .iter()
        .any(|n| head.windows(n.len()).any(|w| w == *n))
}

fn header_prop_to_py(py: Python<'_>, prop: &HeaderProp) -> PyResult<PyObject> {
    Ok(match prop {
        HeaderProp::Array(arr) => {
            let list = PyList::empty_bound(py);
            for inner in arr {
                let dict = PyDict::new_bound(py);
                for (k, v) in inner {
                    let value = header_prop_to_py(py, v)?;
                    dict.set_item(k.as_str(), value)?;
                }
                list.append(dict)?;
            }
            list.to_object(py)
        }
        HeaderProp::Bool(val) => val.into_py(py),
        HeaderProp::Byte { kind, value } => {
            let dict = PyDict::new_bound(py);
            dict.set_item("kind", kind.as_str())?;
            match value {
                Some(v) => dict.set_item("value", v.as_str())?,
                None => dict.set_item("value", py.None())?,
            }
            dict.to_object(py)
        }
        HeaderProp::Float(val) => (*val as f64).into_py(py),
        HeaderProp::Int(val) => (*val).into_py(py),
        HeaderProp::Name(val) | HeaderProp::Str(val) => val.to_object(py),
        HeaderProp::QWord(val) => (*val).into_py(py),
        HeaderProp::Struct { name, fields } => {
            let dict = PyDict::new_bound(py);
            dict.set_item("_struct", name.as_str())?;
            for (k, v) in fields {
                let value = header_prop_to_py(py, v)?;
                dict.set_item(k.as_str(), value)?;
            }
            dict.to_object(py)
        }
    })
}

#[pyfunction]
fn parse_header(path: &str) -> PyResult<PyObject> {
    Python::with_gil(|py| {
        let data = read_file_bytes(path)?;
        if data.len() < 100 {
            return Err(PyValueError::new_err("File too short to be a valid replay"));
        }

        let mut playlist_id: Option<String> = None;
        let mut map_name: Option<String> = None;
        let mut match_guid: Option<String> = None;
        let mut overtime: Option<bool> = None;
        let mut declared_record_fps: Option<f64> = None;
        let mut team0_score: i64 = 0;
        let mut team1_score: i64 = 0;
        let mut match_length: f64 = 0.0;
        let mut players_vec: Vec<(String, i64)> = Vec::new();
        let mut players_meta: Vec<PyObject> = Vec::new();
        let highlights_list = PyList::empty_bound(py);
        let mut team_size: i64 = 0;
        let mut warnings_vec: Vec<String> = Vec::new();
        let mutators = PyDict::new_bound(py);

        fn find_prop<'a>(props: &'a [(String, HeaderProp)], key: &str) -> Option<&'a HeaderProp> {
            props.iter().find(|(k, _)| k == key).map(|(_, v)| v)
        }

        let goals_list = PyList::empty_bound(py);

        match ParserBuilder::new(&data).never_parse_network_data().parse() {
            Ok(Replay { properties, .. }) => {
                if let Some(p) = find_prop(&properties, "MapName") {
                    if let Some(s) = p.as_string() {
                        map_name = Some(s.to_string());
                    }
                }
                if let Some(p) = find_prop(&properties, "PlaylistID") {
                    // PlaylistID can be string or integer - handle both
                    if let Some(s) = p.as_string() {
                        playlist_id = Some(s.to_string());
                    } else if let Some(i) = p.as_i32() {
                        playlist_id = Some(i.to_string());
                    }
                }
                // Read TeamSize early (needed for playlist inference)
                if let Some(p) = find_prop(&properties, "TeamSize") {
                    if let Some(ts) = p.as_i32() {
                        team_size = ts as i64;
                    }
                }
                // Fallback: infer playlist from MatchType + TeamSize when PlaylistID is missing
                if playlist_id.is_none() {
                    let match_type = find_prop(&properties, "MatchType")
                        .and_then(|p| p.as_string())
                        .map(|s| s.to_string());
                    if let Some(mt) = match_type {
                        match mt.as_str() {
                            "Online" => {
                                playlist_id = Some(format!("inferred_{}", team_size));
                            }
                            "Tournament" => {
                                playlist_id = Some("tournament".to_string());
                            }
                            "Private" | "Offline" => {
                                playlist_id = Some("private".to_string());
                            }
                            _ => {}
                        }
                    }
                }
                if let Some(p) = find_prop(&properties, "BuildVersion") {
                    if let Some(s) = p.as_string() {
                        warnings_vec.push(format!("build_version:{}", s));
                    }
                }
                if let Some(p) = find_prop(&properties, "MatchGUID")
                    .or_else(|| find_prop(&properties, "MatchGuid"))
                {
                    if let Some(s) = p.as_string() {
                        match_guid = Some(s.to_string());
                    }
                }
                if let Some(p) = find_prop(&properties, "bOverTime")
                    .or_else(|| find_prop(&properties, "Overtime"))
                    .or_else(|| find_prop(&properties, "IsOvertime"))
                {
                    overtime = match p {
                        HeaderProp::Bool(v) => Some(*v),
                        HeaderProp::Int(v) => Some(*v != 0),
                        _ => None,
                    };
                }
                if let Some(p) = find_prop(&properties, "MutatorSettings")
                    .or_else(|| find_prop(&properties, "Mutators"))
                {
                    match p {
                        HeaderProp::Struct { fields, .. } => {
                            for (k, v) in fields {
                                let value = header_prop_to_py(py, v)?;
                                mutators.set_item(k.as_str(), value)?;
                            }
                        }
                        _ => {
                            mutators.set_item("raw", header_prop_to_py(py, p)?)?;
                        }
                    }
                }
                if let Some(p) = find_prop(&properties, "NumFrames") {
                    if let Some(fr) = p.as_i32() {
                        match_length = (fr as f64) / declared_record_fps.unwrap_or(30.0);
                    }
                }
                if let Some(p) = find_prop(&properties, "RecordFPS") {
                    declared_record_fps = match p {
                        HeaderProp::Float(value) => Some(*value as f64),
                        HeaderProp::Int(value) => Some(*value as f64),
                        _ => None,
                    };
                    if !declared_record_fps.map(|fps| fps > 0.0).unwrap_or(false) {
                        declared_record_fps = None;
                    }
                    if let Some(frames) =
                        find_prop(&properties, "NumFrames").and_then(|prop| prop.as_i32())
                    {
                        match_length = (frames as f64) / declared_record_fps.unwrap_or(30.0);
                    }
                }
                if let Some(p) = find_prop(&properties, "Team0Score") {
                    if let Some(s0) = p.as_i32() {
                        team0_score = s0 as i64;
                    }
                }
                if let Some(p) = find_prop(&properties, "Team1Score") {
                    if let Some(s1) = p.as_i32() {
                        team1_score = s1 as i64;
                    }
                }

                if let Some(p) = find_prop(&properties, "PlayerStats") {
                    if let Some(arr) = p.as_array() {
                        for entry in arr {
                            // Each entry is Vec<(String, HeaderProp)>
                            let mut name: Option<String> = None;
                            let mut team: i64 = 0;
                            let stats_dict = PyDict::new_bound(py);
                            for (k, v) in entry {
                                match (k.as_str(), v) {
                                    ("Name", hp) | ("PlayerName", hp) => {
                                        if let Some(s) = hp.as_string() {
                                            name = Some(s.to_string());
                                        }
                                    }
                                    ("Team", hp) | ("PlayerTeam", hp) => {
                                        if let Some(t) = hp.as_i32() {
                                            team = t as i64;
                                        }
                                    }
                                    _ => {
                                        let value = header_prop_to_py(py, v)?;
                                        stats_dict.set_item(k.as_str(), value)?;
                                    }
                                }
                            }

                            if let Some(n) = name.clone() {
                                players_vec.push((n.clone(), team));
                                let player_dict = PyDict::new_bound(py);
                                player_dict.set_item("name", n)?;
                                player_dict.set_item("team", team)?;
                                player_dict.set_item("stats", stats_dict)?;
                                players_meta.push(player_dict.to_object(py));
                            }
                        }
                    }
                }

                // Goals (frame, PlayerName, PlayerTeam)
                if let Some(p) = find_prop(&properties, "Goals") {
                    if let Some(arr) = p.as_array() {
                        for entry in arr {
                            let mut g_frame: Option<i64> = None;
                            let mut g_name: Option<String> = None;
                            let mut g_team: Option<i64> = None;
                            for (k, v) in entry {
                                match (k.as_str(), v) {
                                    ("frame", hp) => {
                                        if let Some(i) = hp.as_i32() {
                                            g_frame = Some(i as i64);
                                        }
                                    }
                                    ("PlayerName", hp) => {
                                        if let Some(s) = hp.as_string() {
                                            g_name = Some(s.to_string());
                                        }
                                    }
                                    ("PlayerTeam", hp) => {
                                        if let Some(i) = hp.as_i32() {
                                            g_team = Some(i as i64);
                                        }
                                    }
                                    _ => {}
                                }
                            }
                            let g = PyDict::new_bound(py);
                            if let Some(fv) = g_frame {
                                g.set_item("frame", fv)?;
                            }
                            if let Some(nv) = g_name {
                                g.set_item("player_name", nv)?;
                            }
                            if let Some(tv) = g_team {
                                g.set_item("player_team", tv)?;
                            }
                            goals_list.append(g)?;
                        }
                    }
                }

                if let Some(p) = find_prop(&properties, "HighLights") {
                    if let Some(arr) = p.as_array() {
                        for entry in arr {
                            let mut h_frame: Option<i64> = None;
                            let mut h_ball: Option<String> = None;
                            let mut h_car: Option<String> = None;
                            for (k, v) in entry {
                                match (k.as_str(), v) {
                                    ("frame", hp) => {
                                        if let Some(i) = hp.as_i32() {
                                            h_frame = Some(i as i64);
                                        }
                                    }
                                    ("BallName", hp) | ("Ball", hp) => {
                                        if let Some(s) = hp.as_string() {
                                            h_ball = Some(s.to_string());
                                        }
                                    }
                                    ("CarName", hp) | ("Car", hp) => {
                                        if let Some(s) = hp.as_string() {
                                            h_car = Some(s.to_string());
                                        }
                                    }
                                    _ => {}
                                }
                            }
                            let h = PyDict::new_bound(py);
                            if let Some(fv) = h_frame {
                                h.set_item("frame", fv)?;
                            }
                            if let Some(ball) = h_ball {
                                h.set_item("ball_name", ball)?;
                            }
                            if let Some(car) = h_car {
                                h.set_item("car_name", car)?;
                            }
                            highlights_list.append(h)?;
                        }
                    }
                }

                if !players_vec.is_empty() {
                    let mut team_counts: HashMap<i64, i64> = HashMap::new();
                    for (_, t) in &players_vec {
                        *team_counts.entry(*t).or_insert(0) += 1;
                    }
                    team_size = team_counts.values().cloned().max().unwrap_or(1);
                } else {
                    warnings_vec.push("boxcars_no_playerstats".to_string());
                }
            }
            Err(e) => {
                warnings_vec.push(format!("boxcars_parse_error: {}", e));
                let looks_like = looks_like_replay_header(&data);
                if !looks_like {
                    warnings_vec.push("rust_core_suspect_format".to_string());
                }
                players_vec.push(("Unknown Player 1".to_string(), 0));
                players_vec.push(("Unknown Player 2".to_string(), 1));
                team_size = 1;
            }
        }

        let header = PyDict::new_bound(py);
        header.set_item(
            "playlist_id",
            playlist_id.unwrap_or_else(|| "unknown".to_string()),
        )?;
        header.set_item(
            "map_name",
            map_name.unwrap_or_else(|| "unknown".to_string()),
        )?;
        header.set_item("team_size", team_size)?;
        header.set_item("team0_score", team0_score)?;
        header.set_item("team1_score", team1_score)?;
        header.set_item("match_length", match_length)?;
        header.set_item("declared_record_fps", declared_record_fps)?;
        header.set_item("match_guid", match_guid)?;
        match overtime {
            Some(value) => header.set_item("overtime", value)?,
            None => header.set_item("overtime", py.None())?,
        }
        header.set_item("mutators", mutators)?;

        if players_meta.is_empty() {
            let players = PyList::empty_bound(py);
            for (name, team) in &players_vec {
                let p = PyDict::new_bound(py);
                p.set_item("name", name)?;
                p.set_item("team", team)?;
                players.append(p)?;
            }
            header.set_item("players", players)?;
        } else {
            header.set_item("players", PyList::new_bound(py, players_meta))?;
        }
        if let Some(build) = warnings_vec
            .iter()
            .find_map(|w| w.strip_prefix("build_version:"))
        {
            header.set_item("engine_build", build)?;
        }
        header.set_item("goals", goals_list)?;
        header.set_item("highlights", highlights_list)?;
        let warnings = PyList::empty_bound(py);
        warnings.append("parsed_with_rust_core")?;
        for w in warnings_vec {
            warnings.append(w)?;
        }
        header.set_item("quality_warnings", warnings)?;

        Ok(header.to_object(py))
    })
}

#[pyfunction]
fn header_property_keys(path: &str) -> PyResult<Vec<String>> {
    let data = read_file_bytes(path)?;
    let replay = ParserBuilder::new(&data)
        .never_parse_network_data()
        .parse()
        .map_err(|e| PyValueError::new_err(format!("Failed to parse replay header: {e}")))?;
    Ok(replay.properties.iter().map(|(k, _)| k.clone()).collect())
}

#[pyfunction]
fn header_property(path: &str, key: &str) -> PyResult<Option<PyObject>> {
    Python::with_gil(|py| {
        let data = read_file_bytes(path)?;
        let replay = ParserBuilder::new(&data)
            .never_parse_network_data()
            .parse()
            .map_err(|e| PyValueError::new_err(format!("Failed to parse replay header: {e}")))?;
        for (k, v) in replay.properties {
            if k == key {
                let value = header_prop_to_py(py, &v)?;
                return Ok(Some(value));
            }
        }
        Ok(None)
    })
}

/// Convert quaternion (x, y, z, w) to Euler angles (roll, pitch, yaw) in radians.
/// Uses the standard aerospace rotation sequence (ZYX).
fn quat_to_euler(q: (f32, f32, f32, f32)) -> (f64, f64, f64) {
    let (x, y, z, w) = (q.0 as f64, q.1 as f64, q.2 as f64, q.3 as f64);

    let sinr_cosp = 2.0 * (w * x + y * z);
    let cosr_cosp = 1.0 - 2.0 * (x * x + y * y);
    let roll = sinr_cosp.atan2(cosr_cosp);

    let sinp = 2.0 * (w * y - z * x);
    let pitch = if sinp.abs() >= 1.0 {
        std::f64::consts::FRAC_PI_2.copysign(sinp)
    } else {
        sinp.asin()
    };

    let siny_cosp = 2.0 * (w * z + x * y);
    let cosy_cosp = 1.0 - 2.0 * (y * y + z * z);
    let yaw = siny_cosp.atan2(cosy_cosp);

    (roll, pitch, yaw)
}

fn map_network_error_code(message: &str) -> &'static str {
    let lower = message.to_ascii_lowercase();
    if lower.contains("failed to open replay file")
        || lower.contains("failed to read replay file")
        || lower.contains("no such file")
    {
        "replay_io_error"
    } else if lower.contains("unknown attributes for object")
        || lower.contains("no known attributes found")
    {
        "boxcars_unknown_attribute_network_error"
    } else {
        "boxcars_network_error"
    }
}

#[cfg(test)]
mod tests {
    use super::{
        cam_settings_pairs, infer_kickoff_phase, is_car_state_actor, loadout_pairs,
        map_network_error_code, normalize_input_byte, pickup_bool_raw_state,
        resolve_component_owner, team_loadout_for, ActorKind,
    };
    use std::collections::HashMap;

    #[test]
    fn kickoff_phase_stays_initial_before_overtime() {
        assert_eq!(infer_kickoff_phase(15.0, false, 300.0), "INITIAL");
    }

    #[test]
    fn kickoff_phase_uses_overtime_metadata() {
        assert_eq!(infer_kickoff_phase(301.0, true, 300.0), "OT");
    }

    #[test]
    fn kickoff_phase_does_not_infer_overtime_without_metadata() {
        assert_eq!(infer_kickoff_phase(301.0, false, 300.0), "INITIAL");
    }

    #[test]
    fn kickoff_phase_respects_extended_match_length_boundary() {
        assert_eq!(infer_kickoff_phase(350.0, true, 400.0), "INITIAL");
        assert_eq!(infer_kickoff_phase(401.0, true, 400.0), "OT");
    }

    #[test]
    fn unknown_attribute_network_errors_are_classified_explicitly() {
        assert_eq!(
            map_network_error_code(
                "Error decoding frame: no known attributes found for actor id / object id"
            ),
            "boxcars_unknown_attribute_network_error",
        );
        assert_eq!(
            map_network_error_code("unknown attributes for object id 118"),
            "boxcars_unknown_attribute_network_error",
        );
    }

    #[test]
    fn car_state_actor_requires_positive_car_signal() {
        let actor_kind = HashMap::new();
        let car_team = HashMap::new();
        let car_owner = HashMap::new();
        let component_owner = HashMap::new();
        let actor_to_player_index = HashMap::new();

        assert!(!is_car_state_actor(
            7,
            &actor_kind,
            &car_team,
            &car_owner,
            &component_owner,
            &actor_to_player_index,
        ));

        let mut actor_kind = HashMap::new();
        actor_kind.insert(
            7,
            ActorKind {
                is_ball: false,
                is_car: true,
            },
        );
        assert!(is_car_state_actor(
            7,
            &actor_kind,
            &car_team,
            &car_owner,
            &component_owner,
            &actor_to_player_index,
        ));

        actor_kind.insert(
            8,
            ActorKind {
                is_ball: true,
                is_car: false,
            },
        );
        let mut car_team = HashMap::new();
        car_team.insert(8, 0);
        assert!(!is_car_state_actor(
            8,
            &actor_kind,
            &car_team,
            &car_owner,
            &component_owner,
            &actor_to_player_index,
        ));
    }

    #[test]
    fn component_owner_binding_is_a_car_signal_for_owner() {
        let actor_kind = HashMap::new();
        let car_team = HashMap::new();
        let car_owner = HashMap::new();
        let mut component_owner = HashMap::new();
        let actor_to_player_index = HashMap::new();
        component_owner.insert(20, 7);

        assert!(is_car_state_actor(
            7,
            &actor_kind,
            &car_team,
            &car_owner,
            &component_owner,
            &actor_to_player_index,
        ));
        assert!(!is_car_state_actor(
            20,
            &actor_kind,
            &car_team,
            &car_owner,
            &component_owner,
            &actor_to_player_index,
        ));
    }

    #[test]
    fn component_owner_resolution_follows_short_chains() {
        let mut component_owner = HashMap::new();
        component_owner.insert(30, 20);
        component_owner.insert(20, 7);

        assert_eq!(resolve_component_owner(&component_owner, 30), 7);
        assert_eq!(resolve_component_owner(&component_owner, 9), 9);
    }

    #[test]
    fn pickup_bool_raw_state_matches_legacy_pickup_state() {
        assert_eq!(pickup_bool_raw_state(true), 1);
        assert_eq!(pickup_bool_raw_state(false), 0);
    }

    #[test]
    fn normalize_input_byte_uses_centered_signed_range() {
        assert_eq!(normalize_input_byte(128), 0.0);
        assert_eq!(normalize_input_byte(255), 1.0);
        assert_eq!(normalize_input_byte(0), -1.0);
    }

    #[test]
    fn cam_settings_pairs_renames_swivel_and_defaults_transition() {
        // boxcars structs are non_exhaustive, so build them via serde.
        let cam: boxcars::CamSettings = serde_json::from_value(serde_json::json!({
            "fov": 110.0,
            "height": 100.0,
            "angle": -3.0,
            "distance": 270.0,
            "stiffness": 0.45,
            "swivel": 2.5,
        }))
        .unwrap();
        let pairs = cam_settings_pairs(&cam);
        assert_eq!(pairs[0], ("fov", 110.0));
        assert_eq!(pairs[3], ("distance", 270.0));
        assert_eq!(pairs[5], ("swivel_speed", 2.5));
        // Missing transition is surfaced as 0.0 rather than dropped.
        assert_eq!(pairs[6], ("transition_speed", 0.0));
    }

    fn sample_loadout(body: u32) -> boxcars::Loadout {
        serde_json::from_value(serde_json::json!({
            "version": 23,
            "body": body,
            "decal": 2,
            "wheels": 3,
            "rocket_trail": 4,
            "antenna": 5,
            "topper": 6,
            "unknown1": 0,
            "engine_audio": 7,
            "goal_explosion": 9,
        }))
        .unwrap()
    }

    #[test]
    fn loadout_pairs_emits_mandatory_slots_and_present_optionals() {
        let pairs = loadout_pairs(&sample_loadout(1));
        assert!(pairs.contains(&("body", 1)));
        assert!(pairs.contains(&("topper", 6)));
        // Present optionals are included, absent ones are skipped.
        assert!(pairs.contains(&("engine_audio", 7)));
        assert!(pairs.contains(&("goal_explosion", 9)));
        assert!(!pairs.iter().any(|(slot, _)| *slot == "trail"));
        assert!(!pairs.iter().any(|(slot, _)| *slot == "banner"));
    }

    #[test]
    fn team_loadout_for_prefers_player_team() {
        let team_loadout = boxcars::TeamLoadout {
            blue: sample_loadout(100),
            orange: sample_loadout(200),
        };
        assert_eq!(team_loadout_for(Some(0), &team_loadout).body, 100);
        assert_eq!(team_loadout_for(Some(1), &team_loadout).body, 200);
        // Unknown team falls back to blue.
        assert_eq!(team_loadout_for(None, &team_loadout).body, 100);
    }
}

/// Parse a replay's network stream into per-frame telemetry plus per-player
/// profile metadata (camera + loadout). Returns `(frames, player_metadata)` so
/// callers can expose frames alone or the richer payload as needed.
fn run_iter_frames(path: &str) -> PyResult<(Py<PyAny>, Py<PyAny>)> {
    Python::with_gil(|py| {
        let data = read_file_bytes(path)?;
        let replay = ParserBuilder::new(&data)
            .must_parse_network_data()
            .parse()
            .map_err(|e| PyValueError::new_err(format!("Failed to parse network frames: {e}")))?;

        let map_name: String = replay
            .properties
            .iter()
            .find(|(k, _)| k == "MapName")
            .and_then(|(_, v)| v.as_string())
            .map(|s| s.to_string())
            .unwrap_or_default();
        let header_overtime = replay
            .properties
            .iter()
            .find(|(k, _)| k == "bOverTime" || k == "Overtime" || k == "IsOvertime")
            .and_then(|(_, prop)| match prop {
                HeaderProp::Bool(value) => Some(*value),
                HeaderProp::Int(value) => Some(*value != 0),
                _ => None,
            })
            .unwrap_or(false);
        let header_match_length = replay
            .properties
            .iter()
            .find(|(k, _)| k == "NumFrames")
            .and_then(|(_, prop)| prop.as_i32())
            .map(|frames| {
                let fps = replay
                    .properties
                    .iter()
                    .find(|(k, _)| k == "RecordFPS")
                    .and_then(|(_, prop)| match prop {
                        HeaderProp::Float(value) => Some(*value as f64),
                        HeaderProp::Int(value) => Some(*value as f64),
                        _ => None,
                    })
                    .filter(|fps| *fps > 0.0)
                    .unwrap_or(30.0);
                frames as f64 / fps
            })
            .unwrap_or(0.0);

        let mut header_players: Vec<(String, i64)> = Vec::new();
        for (k, v) in &replay.properties {
            if k == "PlayerStats" {
                if let Some(arr) = v.as_array() {
                    for entry in arr {
                        let mut name: Option<String> = None;
                        let mut team: i64 = 0;
                        for (kk, vv) in entry {
                            match (kk.as_str(), vv) {
                                ("Name", hp) | ("PlayerName", hp) => {
                                    if let Some(s) = hp.as_string() {
                                        name = Some(s.to_string());
                                    }
                                }
                                ("Team", hp) | ("PlayerTeam", hp) => {
                                    if let Some(t) = hp.as_i32() {
                                        team = t as i64;
                                    }
                                }
                                _ => {}
                            }
                        }
                        if let Some(n) = name {
                            header_players.push((n, team));
                        }
                    }
                }
            }
        }

        let objects = &replay.objects;
        let mut actor_object_name: HashMap<i32, String> = HashMap::new();
        let mut actor_kind: HashMap<i32, ActorKind> = HashMap::new();
        let mut component_kind: HashMap<i32, ComponentKind> = HashMap::new();
        let mut car_team: HashMap<i32, i64> = HashMap::new();
        let mut car_boost: HashMap<i32, i64> = HashMap::new(); // 0-100
        let mut car_pos: HashMap<i32, (f32, f32, f32)> = HashMap::new();
        let mut car_vel: HashMap<i32, (f32, f32, f32)> = HashMap::new();
        let mut car_angvel: HashMap<i32, (f32, f32, f32)> = HashMap::new();
        let mut car_sleeping: HashMap<i32, bool> = HashMap::new();
        let mut car_throttle_raw: HashMap<i32, u8> = HashMap::new();
        let mut car_steer_raw: HashMap<i32, u8> = HashMap::new();
        let mut car_handbrake: HashMap<i32, bool> = HashMap::new();
        let mut car_boost_raw: HashMap<i32, u8> = HashMap::new();
        let mut car_boost_grant_count: HashMap<i32, u8> = HashMap::new();
        let mut car_rot: HashMap<i32, (f32, f32, f32, f32)> = HashMap::new(); // quaternion (x,y,z,w)
        let mut car_demo: HashMap<i32, bool> = HashMap::new();
        let mut car_owner: HashMap<i32, i32> = HashMap::new();
        let mut component_owner: HashMap<i32, i32> = HashMap::new();
        let mut component_active_state: HashMap<i32, bool> = HashMap::new();
        let mut component_active_raw: HashMap<i32, u8> = HashMap::new();
        let mut pad_registry = PadRegistry::new_with_arena(&map_name);
        let mut ball_actor: Option<i32> = None;
        let mut ball_pos: (f32, f32, f32) = (0.0, 0.0, 93.15);
        let mut ball_vel: (f32, f32, f32) = (0.0, 0.0, 0.0);
        let mut ball_angvel: (f32, f32, f32) = (0.0, 0.0, 0.0);
        let mut ball_sleeping = false;
        let mut actor_to_player_index: HashMap<i32, usize> = HashMap::new();
        let mut owner_to_player_index: HashMap<i32, usize> = HashMap::new();
        let mut next_by_team: HashMap<i64, Vec<usize>> = HashMap::new();
        // Per-player profile metadata (camera + loadout), captured from the network
        // stream and keyed by PRI actor id. These persist for the whole replay even
        // across actor deletion/respawn, then resolve to header indices at the end.
        let mut camera_actor_to_pri: HashMap<i32, i32> = HashMap::new();
        let mut camera_by_pri: HashMap<i32, boxcars::CamSettings> = HashMap::new();
        // CamSettings observed on a CameraSettingsActor before its PRI link was seen.
        let mut camera_pending: HashMap<i32, boxcars::CamSettings> = HashMap::new();
        let mut loadout_by_pri: HashMap<i32, boxcars::Loadout> = HashMap::new();
        // Raw team loadouts kept unresolved until the final pass, where the
        // player's team is reliably known (the PRI->index binding may not exist
        // yet when ClientLoadouts is first replicated).
        let mut team_loadout_by_pri: HashMap<i32, boxcars::TeamLoadout> = HashMap::new();
        let mut fallback_actor_index: HashMap<i32, usize> = HashMap::new();
        let mut next_fallback_index: usize = 0;
        let mut prev_demo_state: HashMap<i32, bool> = HashMap::new();
        let mut frame_index: i64 = 0;
        let mut kickoff_active = false;

        let mut last_touch_time: HashMap<i32, f64> = HashMap::new();
        let mut last_touch_pos: HashMap<i32, (f32, f32, f32)> = HashMap::new();
        let mut tickmarks_by_frame: HashMap<i64, Vec<(String, i64)>> = HashMap::new();

        let mut team_zero: Vec<usize> = Vec::new();
        let mut team_one: Vec<usize> = Vec::new();
        for (idx, (_, team)) in header_players.iter().enumerate() {
            if *team == 0 {
                team_zero.push(idx);
            } else {
                team_one.push(idx);
            }
        }
        next_by_team.insert(0, team_zero);
        next_by_team.insert(1, team_one);

        for tickmark in &replay.tick_marks {
            tickmarks_by_frame
                .entry(tickmark.frame as i64)
                .or_default()
                .push((tickmark.description.clone(), tickmark.frame as i64));
        }

        let frames_out = PyList::empty_bound(py);

        fn classify_object_name_lower(lname: &str) -> ActorKind {
            let is_ball = lname.contains("ball_ta")
                || lname.contains("ball_default")
                || lname.contains("archetypes.ball")
                || lname.ends_with("ball")
                || (lname.contains("ball_") && !lname.contains("ballcam"));
            let is_car = (lname.contains("archetypes.car.car_")
                || lname.contains("car_default")
                || lname.contains("car_ta")
                || lname.contains("vehicle_ta")
                || lname.contains("default__car_ta")
                || lname.contains("default__carbody")
                || lname.contains("tagame.car_")
                // Additional patterns for modern replay builds
                || lname.contains("pawntype_ta")
                || lname.contains("rbactor_ta")
                || lname.contains("body_ta"))
                && !lname.contains("carcomponent");
            ActorKind { is_ball, is_car }
        }

        fn classify_component_name_lower(lname: &str) -> Option<ComponentKind> {
            if !lname.contains("carcomponent") {
                return None;
            }
            Some(ComponentKind {
                is_jump: lname.contains("carcomponent_jump"),
                is_dodge: lname.contains("carcomponent_dodge"),
                is_double_jump: lname.contains("carcomponent_doublejump"),
                is_boost: lname.contains("carcomponent_boost"),
                is_air_activate: lname.contains("carcomponent_airactivate"),
            })
        }

        if let Some(net) = replay.network_frames {
            for nf in net.frames {
                let mut frame_pad_events: Vec<PadEvent> = Vec::new();
                let mut frame_jumping_actors: HashSet<i32> = HashSet::new();
                let mut frame_dodging_actors: HashSet<i32> = HashSet::new();
                let mut frame_double_jumping_actors: HashSet<i32> = HashSet::new();
                let mut frame_demo_records: Vec<(i32, Option<i32>)> = Vec::new();
                let mut frame_component_events: Vec<ComponentEvent> = Vec::new();
                let mut frame_stat_events: Vec<ParserStatEvent> = Vec::new();
                // Prune actors that were deleted before processing updates to avoid stale telemetry
                for deleted in nf.deleted_actors {
                    let aid: i32 = deleted.into();
                    let team_for_return = car_team
                        .get(&aid)
                        .copied()
                        .or_else(|| {
                            actor_to_player_index
                                .get(&aid)
                                .and_then(|idx| header_players.get(*idx))
                                .map(|(_, team)| *team)
                        })
                        .or_else(|| {
                            car_pos
                                .get(&aid)
                                .map(|(_, y, _)| if *y > 0.0 { 1 } else { 0 })
                        });
                    if ball_actor == Some(aid) {
                        ball_actor = None;
                        ball_pos = (0.0, 0.0, 93.15);
                        ball_vel = (0.0, 0.0, 0.0);
                        ball_angvel = (0.0, 0.0, 0.0);
                        ball_sleeping = false;
                    }
                    if let Some(idx) = actor_to_player_index.remove(&aid) {
                        if let Some(team) = team_for_return {
                            if let Some(queue) = next_by_team.get_mut(&team) {
                                queue.push(idx);
                            }
                        }
                    }
                    actor_object_name.remove(&aid);
                    actor_kind.remove(&aid);
                    component_kind.remove(&aid);
                    component_active_state.remove(&aid);
                    component_active_raw.remove(&aid);
                    car_team.remove(&aid);
                    car_boost.remove(&aid);
                    car_boost_raw.remove(&aid);
                    car_boost_grant_count.remove(&aid);
                    car_pos.remove(&aid);
                    car_vel.remove(&aid);
                    car_angvel.remove(&aid);
                    car_sleeping.remove(&aid);
                    car_throttle_raw.remove(&aid);
                    car_steer_raw.remove(&aid);
                    car_handbrake.remove(&aid);
                    car_rot.remove(&aid);
                    car_demo.remove(&aid);
                    car_owner.remove(&aid);
                    prev_demo_state.remove(&aid);
                    last_touch_time.remove(&aid);
                    last_touch_pos.remove(&aid);
                    // Drop transient camera-actor links keyed by this (ephemeral)
                    // actor id so a reused id can't bind a later CamSettings to a
                    // stale PRI. The persistent camera_by_pri/loadout_by_pri are
                    // keyed by PRI and intentionally survive (respawn persistence).
                    camera_actor_to_pri.remove(&aid);
                    camera_pending.remove(&aid);
                    component_owner.retain(|comp, owner| *comp != aid && *owner != aid);
                    let retained_components: HashSet<i32> =
                        component_owner.keys().copied().collect();
                    component_active_state.retain(|comp, _| retained_components.contains(comp));
                    component_active_raw.retain(|comp, _| retained_components.contains(comp));
                    pad_registry.remove_actor(aid);
                }

                for NewActor {
                    actor_id,
                    object_id,
                    ..
                } in nf.new_actors
                {
                    let oid: usize = object_id.into();
                    let obj_name = objects.get(oid).cloned().unwrap_or_default();
                    let obj_name_lower = obj_name.to_ascii_lowercase();
                    let aid: i32 = actor_id.into();
                    actor_object_name.insert(aid, obj_name.clone());
                    let kind = classify_object_name_lower(&obj_name_lower);
                    if kind.is_ball {
                        ball_actor = Some(aid);
                        ball_pos = (0.0, 0.0, 93.15);
                        ball_vel = (0.0, 0.0, 0.0);
                        ball_angvel = (0.0, 0.0, 0.0);
                        ball_sleeping = false;
                    }
                    if kind.is_ball || kind.is_car {
                        actor_kind.insert(aid, kind);
                    }
                    if let Some(component) = classify_component_name_lower(&obj_name_lower) {
                        component_kind.insert(aid, component);
                    }
                    pad_registry.track_new_actor(aid, &obj_name);
                }

                for upd in nf.updated_actors {
                    let aid: i32 = upd.actor_id.into();
                    let upd_object_id: usize = upd.object_id.into();
                    match upd.attribute {
                        Attribute::ActiveActor(active) => {
                            // Link a CameraSettingsActor to the PRI it belongs to so a
                            // later ProfileSettings update can be attributed to a player.
                            // Only trust the reference when active; an inactive update
                            // carries a stale/invalid actor id (matches car-owner binding).
                            if active.active
                                && objects
                                    .get(upd_object_id)
                                    .map(|name| name == "TAGame.CameraSettingsActor_TA:PRI")
                                    .unwrap_or(false)
                            {
                                let pri: i32 = active.actor.into();
                                camera_actor_to_pri.insert(aid, pri);
                                if let Some(cam) = camera_pending.remove(&aid) {
                                    camera_by_pri.insert(pri, cam);
                                }
                            }
                            if component_kind.contains_key(&aid) {
                                let owner_id: i32 = active.actor.into();
                                component_owner.insert(aid, owner_id);
                            }
                            if active.active
                                && actor_kind
                                    .get(&aid)
                                    .map(|kind| kind.is_car)
                                    .unwrap_or(false)
                            {
                                let owner_id: i32 = active.actor.into();
                                let owner_is_player = owner_to_player_index.contains_key(&owner_id)
                                    || actor_object_name
                                        .get(&owner_id)
                                        .map(|object_name| object_name.contains("PRI_TA"))
                                        .unwrap_or(false);
                                if !owner_is_player {
                                    continue;
                                }
                                car_owner.insert(aid, owner_id);
                                if let Some(idx) = owner_to_player_index.get(&owner_id).copied() {
                                    bind_player_index(
                                        &mut actor_to_player_index,
                                        &mut next_by_team,
                                        aid,
                                        idx,
                                    );
                                    if let Some((_, team)) = header_players.get(idx) {
                                        car_team.insert(aid, *team);
                                    }
                                }
                            }
                        }
                        Attribute::String(player_name) => {
                            let is_player_replication_actor = actor_object_name
                                .get(&aid)
                                .map(|object_name| object_name.contains("PRI_TA"))
                                .unwrap_or(false);
                            if !is_player_replication_actor {
                                continue;
                            }
                            if let Some(idx) =
                                unique_header_index_by_name(&header_players, &player_name)
                            {
                                owner_to_player_index.insert(aid, idx);
                                let owned_cars: Vec<i32> = car_owner
                                    .iter()
                                    .filter_map(|(car_actor, owner)| {
                                        (*owner == aid).then_some(*car_actor)
                                    })
                                    .collect();
                                for car_actor in owned_cars {
                                    bind_player_index(
                                        &mut actor_to_player_index,
                                        &mut next_by_team,
                                        car_actor,
                                        idx,
                                    );
                                    if let Some((_, team)) = header_players.get(idx) {
                                        car_team.insert(car_actor, *team);
                                    }
                                }
                            }
                        }
                        // Primary physics carrier observed across builds
                        Attribute::RigidBody(rb) => {
                            let loc = rb.location;
                            let vel = rb.linear_velocity.unwrap_or(Vector3f {
                                x: 0.0,
                                y: 0.0,
                                z: 0.0,
                            });
                            let ang = rb.angular_velocity.unwrap_or(Vector3f {
                                x: 0.0,
                                y: 0.0,
                                z: 0.0,
                            });
                            // Update ball or car state depending on classification and fallback
                            let is_ball = Some(aid) == ball_actor
                                || actor_kind
                                    .get(&aid)
                                    .map(|kind| kind.is_ball)
                                    .unwrap_or(false);
                            if is_ball {
                                ball_actor = Some(aid);
                                ball_pos = (loc.x, loc.y, loc.z);
                                ball_vel = (vel.x, vel.y, vel.z);
                                ball_angvel = angular_velocity_to_radians(ang);
                                ball_sleeping = rb.sleeping;
                            } else if is_car_state_actor(
                                aid,
                                &actor_kind,
                                &car_team,
                                &car_owner,
                                &component_owner,
                                &actor_to_player_index,
                            ) {
                                car_pos.insert(aid, (loc.x, loc.y, loc.z));
                                car_vel.insert(aid, (vel.x, vel.y, vel.z));
                                car_angvel.insert(aid, angular_velocity_to_radians(ang));
                                car_sleeping.insert(aid, rb.sleeping);
                                let rot = rb.rotation;
                                car_rot.insert(aid, (rot.x, rot.y, rot.z, rot.w));
                            }
                            let events = pad_registry.update_position(aid, (loc.x, loc.y, loc.z));
                            frame_pad_events.extend(events);
                        }
                        // Some builds carry these separately
                        Attribute::Location(loc) => {
                            let update_name = objects.get(upd_object_id).map(String::as_str);
                            if let Some(component) = component_kind.get(&aid) {
                                let target = resolve_component_owner(&component_owner, aid);
                                if component.is_jump {
                                    frame_jumping_actors.insert(target);
                                }
                                if component.is_dodge {
                                    frame_dodging_actors.insert(target);
                                }
                                if component.is_double_jump {
                                    frame_double_jumping_actors.insert(target);
                                }
                                let vector_event = match update_name {
                                    Some("TAGame.CarComponent_Dodge_TA:DodgeTorque") => {
                                        Some(("dodge_torque", "dodge"))
                                    }
                                    // Unverified against real replay data (absent from all
                                    // committed fixtures); do not build on this signal until
                                    // a fixture containing it is found.
                                    Some("TAGame.CarComponent_Dodge_TA:DodgeImpulse") => {
                                        Some(("dodge_impulse", "dodge"))
                                    }
                                    Some("TAGame.CarComponent_DoubleJump_TA:DoubleJumpImpulse") => {
                                        Some(("double_jump_impulse", "double_jump"))
                                    }
                                    _ => None,
                                };
                                if let Some((kind, label)) = vector_event {
                                    frame_component_events.push(ComponentEvent {
                                        owner_actor_id: target,
                                        kind,
                                        component: label,
                                        vector: Some((loc.x, loc.y, loc.z)),
                                        raw_value: None,
                                        active: None,
                                    });
                                }
                            }
                            let is_ball = Some(aid) == ball_actor
                                || actor_kind
                                    .get(&aid)
                                    .map(|kind| kind.is_ball)
                                    .unwrap_or(false);
                            if is_ball {
                                ball_actor = Some(aid);
                                ball_pos = (loc.x, loc.y, loc.z);
                            } else if is_car_state_actor(
                                aid,
                                &actor_kind,
                                &car_team,
                                &car_owner,
                                &component_owner,
                                &actor_to_player_index,
                            ) {
                                car_pos.insert(aid, (loc.x, loc.y, loc.z));
                            }
                            let events = pad_registry.update_position(aid, (loc.x, loc.y, loc.z));
                            frame_pad_events.extend(events);
                        }
                        Attribute::Byte(raw) => {
                            match objects.get(upd_object_id).map(String::as_str) {
                                Some("TAGame.Vehicle_TA:ReplicatedThrottle") => {
                                    car_throttle_raw.insert(aid, raw);
                                }
                                Some("TAGame.Vehicle_TA:ReplicatedSteer") => {
                                    car_steer_raw.insert(aid, raw);
                                }
                                Some("TAGame.CarComponent_Boost_TA:ReplicatedBoostAmount") => {
                                    let target = resolve_component_owner(&component_owner, aid);
                                    let amt = ((raw as f64) * (100.0 / 255.0)).round() as i64;
                                    car_boost.insert(target, amt.clamp(0, 100));
                                    car_boost_raw.insert(target, raw);
                                }
                                Some("TAGame.CarComponent_TA:ReplicatedActive") => {
                                    if let Some(component) = component_kind.get(&aid) {
                                        if let Some(label) = component_label(component) {
                                            // `active` is the per-frame parity sample, not a
                                            // debounced activation edge; sub-frame double-toggles
                                            // leave parity unchanged and are invisible here.
                                            // `raw` is a u8 counter: consumers computing deltas
                                            // must do so modulo 256 (254 -> 2 means +4, not -252).
                                            let active = raw % 2 == 1;
                                            let target =
                                                resolve_component_owner(&component_owner, aid);
                                            let previous = component_active_raw.insert(aid, raw);
                                            component_active_state.insert(aid, active);
                                            if previous != Some(raw)
                                                && (previous.is_some() || active)
                                            {
                                                frame_component_events.push(ComponentEvent {
                                                    owner_actor_id: target,
                                                    kind: "active",
                                                    component: label,
                                                    vector: None,
                                                    raw_value: Some(raw as i64),
                                                    active: Some(active),
                                                });
                                            }
                                        }
                                    }
                                }
                                _ => {
                                    if let Some(component) = component_kind.get(&aid) {
                                        if component.is_jump
                                            || component.is_dodge
                                            || component.is_double_jump
                                        {
                                            component_active_state.insert(aid, raw % 2 == 1);
                                        }
                                    }
                                }
                            }
                        }
                        Attribute::Boolean(value) => {
                            if objects
                                .get(upd_object_id)
                                .map(|name| name == "TAGame.Vehicle_TA:bReplicatedHandbrake")
                                .unwrap_or(false)
                            {
                                car_handbrake.insert(aid, value);
                            }
                        }
                        Attribute::Int(value) => {
                            if objects
                                .get(upd_object_id)
                                .map(|name| {
                                    name == "TAGame.CarComponent_AirActivate_TA:AirActivateCount"
                                })
                                .unwrap_or(false)
                            {
                                let target = resolve_component_owner(&component_owner, aid);
                                frame_component_events.push(ComponentEvent {
                                    owner_actor_id: target,
                                    kind: "air_activate_count",
                                    component: "air_activate",
                                    vector: None,
                                    raw_value: Some(value as i64),
                                    active: None,
                                });
                            }
                        }

                        Attribute::Pickup(pickup) => {
                            let mut raw_actor_opt: Option<i32> = None;
                            let mut resolved_actor: Option<i32> = None;
                            if let Some(instigator) = pickup.instigator {
                                let raw_actor: i32 = instigator.into();
                                raw_actor_opt = Some(raw_actor);
                                resolved_actor =
                                    Some(resolve_component_owner(&component_owner, raw_actor));
                            }

                            let events = pad_registry.handle_pickup(
                                aid,
                                pickup_bool_raw_state(pickup.picked_up),
                                nf.time,
                                raw_actor_opt,
                                resolved_actor,
                                resolved_actor.and_then(|actor| car_pos.get(&actor).copied()),
                            );
                            frame_pad_events.extend(events);
                        }

                        Attribute::PickupNew(pickup) => {
                            let mut raw_actor_opt: Option<i32> = None;
                            let mut resolved_actor: Option<i32> = None;
                            if let Some(instigator) = pickup.instigator {
                                let raw_actor: i32 = instigator.into();
                                raw_actor_opt = Some(raw_actor);
                                resolved_actor =
                                    Some(resolve_component_owner(&component_owner, raw_actor));
                            }

                            let events = pad_registry.handle_pickup(
                                aid,
                                pickup.picked_up,
                                nf.time,
                                raw_actor_opt,
                                resolved_actor,
                                resolved_actor.and_then(|actor| car_pos.get(&actor).copied()),
                            );
                            frame_pad_events.extend(events);
                        }
                        // Team + visual paint data (use team assignment if present)
                        Attribute::TeamPaint(tp) => {
                            let t = (tp.team as i64).clamp(0, 1);
                            let target = component_owner.get(&aid).cloned().unwrap_or(aid);
                            car_team.insert(target, t);
                            // Skip only if we positively know this actor is NOT a car.
                            // Unclassified actors that receive TeamPaint are treated as cars
                            // (TeamPaint is a car-exclusive attribute in Rocket League).
                            if actor_kind
                                .get(&target)
                                .map(|kind| !kind.is_car)
                                .unwrap_or(false)
                            {
                                continue;
                            }
                            // Register as car if not yet classified (TeamPaint implies car)
                            actor_kind.entry(target).or_insert(ActorKind {
                                is_ball: false,
                                is_car: true,
                            });
                            let mut assigned_idx = actor_to_player_index.get(&target).copied();
                            if assigned_idx.is_none() {
                                assigned_idx = car_owner
                                    .get(&target)
                                    .and_then(|owner| owner_to_player_index.get(owner))
                                    .copied();
                                if let Some(idx) = assigned_idx {
                                    bind_player_index(
                                        &mut actor_to_player_index,
                                        &mut next_by_team,
                                        target,
                                        idx,
                                    );
                                }
                            }
                            if assigned_idx.is_none() {
                                assigned_idx = pop_available_player_index(
                                    &actor_to_player_index,
                                    &mut next_by_team,
                                    t,
                                );
                                if let Some(idx) = assigned_idx {
                                    bind_player_index(
                                        &mut actor_to_player_index,
                                        &mut next_by_team,
                                        target,
                                        idx,
                                    );
                                }
                            }
                            if let Some(idx) = assigned_idx {
                                if car_owner.contains_key(&target) {
                                    if let Some((_, team)) = header_players.get(idx) {
                                        car_team.insert(target, *team);
                                    }
                                }
                            }
                        }
                        // Boost value replication (0..=255) → scale to 0..=100
                        Attribute::ReplicatedBoost(rb) => {
                            let amt = ((rb.boost_amount as f64) * (100.0 / 255.0)).round() as i64;
                            let target = resolve_component_owner(&component_owner, aid);
                            car_boost.insert(target, amt.clamp(0, 100));
                            car_boost_raw.insert(target, rb.boost_amount);
                            car_boost_grant_count.insert(target, rb.grant_count);
                        }
                        Attribute::StatEvent(stat) => {
                            let object_name = if stat.object_id >= 0 {
                                objects.get(stat.object_id as usize).cloned()
                            } else {
                                None
                            };
                            frame_stat_events.push(ParserStatEvent {
                                object_id: stat.object_id,
                                object_name,
                                unknown1: stat.unknown1,
                            });
                        }
                        // Demolition signals carry attacker/victim attribution in some builds.
                        Attribute::Demolish(demo) => {
                            let victim_id: i32 = if demo.victim_flag {
                                demo.victim.into()
                            } else {
                                aid
                            };
                            let attacker_id = if demo.attacker_flag {
                                Some(i32::from(demo.attacker))
                            } else {
                                None
                            };
                            car_demo.insert(victim_id, true);
                            frame_demo_records.push((victim_id, attacker_id));
                        }
                        Attribute::DemolishExtended(demo) => {
                            let victim_id = if demo.victim.active {
                                Some(i32::from(demo.victim.actor))
                            } else {
                                None
                            };
                            let attacker_id = if demo.attacker.active {
                                Some(i32::from(demo.attacker.actor))
                            } else {
                                None
                            };
                            if let Some(victim_actor) = victim_id {
                                car_demo.insert(victim_actor, true);
                                frame_demo_records.push((victim_actor, attacker_id));
                            } else {
                                car_demo.insert(aid, true);
                                frame_demo_records.push((aid, attacker_id));
                            }
                        }
                        Attribute::DemolishFx(demo) => {
                            let victim_id: i32 = if demo.victim_flag {
                                demo.victim.into()
                            } else {
                                aid
                            };
                            let attacker_id = if demo.attacker_flag {
                                Some(i32::from(demo.attacker))
                            } else {
                                None
                            };
                            car_demo.insert(victim_id, true);
                            frame_demo_records.push((victim_id, attacker_id));
                        }
                        // Per-player camera profile. Arrives either directly on the PRI
                        // (PRI_TA:CameraSettings) or on a linked CameraSettingsActor
                        // (CameraSettingsActor_TA:ProfileSettings).
                        Attribute::CamSettings(cam) => {
                            let on_pri = objects
                                .get(upd_object_id)
                                .map(|name| name == "TAGame.PRI_TA:CameraSettings")
                                .unwrap_or(false);
                            if on_pri {
                                camera_by_pri.insert(aid, *cam);
                            } else if let Some(pri) = camera_actor_to_pri.get(&aid).copied() {
                                camera_by_pri.insert(pri, *cam);
                            } else {
                                // PRI link not seen yet; buffer until the link arrives.
                                camera_pending.insert(aid, *cam);
                            }
                        }
                        // Per-player loadout. Replicated on the PRI_TA actor itself.
                        Attribute::Loadout(loadout) => {
                            loadout_by_pri.insert(aid, *loadout);
                        }
                        Attribute::TeamLoadout(team_loadout) => {
                            // Defer blue/orange selection to the final pass; the
                            // player's team may not be bound yet at this point.
                            team_loadout_by_pri.insert(aid, *team_loadout);
                        }
                        _ => {}
                    }
                }

                frame_pad_events.extend(pad_registry.flush_ready_events());

                let f = PyDict::new_bound(py);
                f.set_item("timestamp", nf.time as f64)?;
                f.set_item("delta", nf.delta as f64)?;
                let ball = PyDict::new_bound(py);
                let bpos = PyDict::new_bound(py);
                bpos.set_item("x", ball_pos.0)?;
                bpos.set_item("y", ball_pos.1)?;
                bpos.set_item("z", ball_pos.2)?;
                let bvel = PyDict::new_bound(py);
                bvel.set_item("x", ball_vel.0)?;
                bvel.set_item("y", ball_vel.1)?;
                bvel.set_item("z", ball_vel.2)?;
                ball.set_item("position", bpos)?;
                ball.set_item("velocity", bvel)?;
                ball.set_item("sleeping", ball_sleeping)?;
                let ang = PyDict::new_bound(py);
                ang.set_item("x", ball_angvel.0)?;
                ang.set_item("y", ball_angvel.1)?;
                ang.set_item("z", ball_angvel.2)?;
                ball.set_item("angular_velocity", ang)?;
                f.set_item("ball", ball)?;

                let mut actors: BTreeSet<i32> = BTreeSet::new();
                for k in car_pos.keys() {
                    actors.insert(*k);
                }
                for k in car_boost.keys() {
                    actors.insert(*k);
                }
                for k in car_team.keys() {
                    actors.insert(*k);
                }
                if let Some(ball_id) = ball_actor {
                    actors.remove(&ball_id);
                }
                // Emit only actors with a positive car signal. Component/boost actors can
                // receive physics updates too, so unclassified physics alone is not enough.
                actors.retain(|aid| {
                    is_car_state_actor(
                        *aid,
                        &actor_kind,
                        &car_team,
                        &car_owner,
                        &component_owner,
                        &actor_to_player_index,
                    )
                });

                let mut players_map: BTreeMap<usize, PyObject> = BTreeMap::new();
                let owned_actor_ids: HashSet<i32> = component_owner.values().copied().collect();
                let mut owner_jump_state: HashMap<i32, bool> = HashMap::new();
                let mut owner_dodge_state: HashMap<i32, bool> = HashMap::new();
                let mut owner_double_jump_state: HashMap<i32, bool> = HashMap::new();
                let mut owner_boost_state: HashMap<i32, bool> = HashMap::new();
                let mut owner_jump_raw: HashMap<i32, u8> = HashMap::new();
                let mut owner_dodge_raw: HashMap<i32, u8> = HashMap::new();
                let mut owner_double_jump_raw: HashMap<i32, u8> = HashMap::new();
                let mut owner_boost_raw: HashMap<i32, u8> = HashMap::new();
                for (component_id, owner_id) in &component_owner {
                    let Some(component) = component_kind.get(component_id) else {
                        continue;
                    };
                    let active = component_active_state
                        .get(component_id)
                        .copied()
                        .unwrap_or(false);
                    let raw = component_active_raw.get(component_id).copied();
                    if component.is_jump {
                        owner_jump_state.insert(*owner_id, active);
                        if let Some(raw) = raw {
                            owner_jump_raw.insert(*owner_id, raw);
                        }
                    }
                    if component.is_dodge {
                        owner_dodge_state.insert(*owner_id, active);
                        if let Some(raw) = raw {
                            owner_dodge_raw.insert(*owner_id, raw);
                        }
                    }
                    if component.is_double_jump {
                        owner_double_jump_state.insert(*owner_id, active);
                        if let Some(raw) = raw {
                            owner_double_jump_raw.insert(*owner_id, raw);
                        }
                    }
                    if component.is_boost {
                        owner_boost_state.insert(*owner_id, active);
                        if let Some(raw) = raw {
                            owner_boost_raw.insert(*owner_id, raw);
                        }
                    }
                }
                for actor_id in &frame_jumping_actors {
                    owner_jump_state.insert(*actor_id, true);
                }
                for actor_id in &frame_dodging_actors {
                    owner_dodge_state.insert(*actor_id, true);
                }
                for actor_id in &frame_double_jumping_actors {
                    owner_double_jump_state.insert(*actor_id, true);
                }
                let mut frame_classification_source = "object_name";
                for aid in actors {
                    let mut actor_classification_source = "fallback_unclassified";
                    if actor_kind.contains_key(&aid) {
                        actor_classification_source = "object_name";
                    } else if owned_actor_ids.contains(&aid) {
                        actor_classification_source = "component_owner_chain";
                    }
                    if actor_classification_source == "fallback_unclassified" {
                        frame_classification_source = "fallback_unclassified";
                    } else if actor_classification_source == "component_owner_chain"
                        && frame_classification_source == "object_name"
                    {
                        frame_classification_source = "component_owner_chain";
                    }

                    let (x, y, z) = car_pos.get(&aid).cloned().unwrap_or((0.0, 0.0, 17.0));
                    let mut team = *car_team.get(&aid).unwrap_or(&-1);
                    if team < 0 {
                        team = if y > 0.0 { 1 } else { 0 };
                    }
                    // Assign player index if not assigned and team known
                    if !actor_to_player_index.contains_key(&aid) && team >= 0 {
                        let mut assigned_idx = car_owner
                            .get(&aid)
                            .and_then(|owner| owner_to_player_index.get(owner))
                            .copied();
                        if let Some(idx) = assigned_idx {
                            bind_player_index(
                                &mut actor_to_player_index,
                                &mut next_by_team,
                                aid,
                                idx,
                            );
                        } else if let Some(idx) = pop_available_player_index(
                            &actor_to_player_index,
                            &mut next_by_team,
                            team,
                        ) {
                            bind_player_index(
                                &mut actor_to_player_index,
                                &mut next_by_team,
                                aid,
                                idx,
                            );
                            assigned_idx = Some(idx);
                        } else if header_players.is_empty() {
                            let fallback = *fallback_actor_index.entry(aid).or_insert_with(|| {
                                let idx = next_fallback_index;
                                next_fallback_index += 1;
                                idx
                            });
                            actor_to_player_index.insert(aid, fallback);
                            assigned_idx = Some(fallback);
                        }
                        if let Some(idx) = assigned_idx {
                            if car_owner.contains_key(&aid) {
                                if let Some((_, team)) = header_players.get(idx) {
                                    car_team.insert(aid, *team);
                                }
                            }
                        }
                    }
                    if let Some(idx) = actor_to_player_index.get(&aid).cloned() {
                        let p = PyDict::new_bound(py);
                        p.set_item("player_id", format!("player_{}", idx))?;
                        p.set_item("team", team)?;
                        let ppos = PyDict::new_bound(py);
                        ppos.set_item("x", x)?;
                        ppos.set_item("y", y)?;
                        ppos.set_item("z", z)?;
                        let v = car_vel.get(&aid).cloned().unwrap_or((0.0, 0.0, 0.0));
                        let pvel = PyDict::new_bound(py);
                        pvel.set_item("x", v.0)?;
                        pvel.set_item("y", v.1)?;
                        pvel.set_item("z", v.2)?;
                        let av = car_angvel.get(&aid).cloned().unwrap_or((0.0, 0.0, 0.0));
                        let pang = PyDict::new_bound(py);
                        pang.set_item("x", av.0)?;
                        pang.set_item("y", av.1)?;
                        pang.set_item("z", av.2)?;

                        // Use true quaternion rotation if available, else fallback to velocity approximation
                        let prot = PyDict::new_bound(py);
                        if let Some(q) = car_rot.get(&aid) {
                            let (roll, pitch, yaw) = quat_to_euler(*q);
                            prot.set_item("pitch", pitch)?;
                            prot.set_item("yaw", yaw)?;
                            prot.set_item("roll", roll)?;
                            // Also include raw quaternion for precision work
                            let quat = PyDict::new_bound(py);
                            quat.set_item("x", q.0 as f64)?;
                            quat.set_item("y", q.1 as f64)?;
                            quat.set_item("z", q.2 as f64)?;
                            quat.set_item("w", q.3 as f64)?;
                            prot.set_item("quaternion", quat)?;
                        } else {
                            // Fallback to velocity approximation for older replays
                            let speed2 = v.0 * v.0 + v.1 * v.1 + v.2 * v.2;
                            let mut pitch = 0.0f64;
                            let mut yaw = 0.0f64;
                            if speed2 > 1e-6 {
                                let speed = speed2.sqrt();
                                yaw = (v.1 as f64).atan2(v.0 as f64);
                                pitch = (v.2 as f64 / speed as f64).asin();
                            }
                            prot.set_item("pitch", pitch)?;
                            prot.set_item("yaw", yaw)?;
                            prot.set_item("roll", 0.0f64)?;
                        }
                        p.set_item("position", ppos)?;
                        p.set_item("velocity", pvel)?;
                        p.set_item("angular_velocity", pang)?;
                        p.set_item("rotation", prot)?;
                        let boost = *car_boost.get(&aid).unwrap_or(&33);
                        p.set_item("boost_amount", boost)?;
                        if let Some(raw) = car_boost_raw.get(&aid) {
                            p.set_item("boost_amount_raw", *raw)?;
                        }
                        if let Some(grant_count) = car_boost_grant_count.get(&aid) {
                            p.set_item("boost_grant_count", *grant_count)?;
                        }
                        if let Some(raw) = car_throttle_raw.get(&aid) {
                            p.set_item("throttle_raw", *raw)?;
                            p.set_item("throttle", normalize_input_byte(*raw))?;
                        }
                        if let Some(raw) = car_steer_raw.get(&aid) {
                            p.set_item("steer_raw", *raw)?;
                            p.set_item("steer", normalize_input_byte(*raw))?;
                        }
                        if let Some(value) = car_handbrake.get(&aid) {
                            p.set_item("handbrake", *value)?;
                        }
                        let speed = (v.0 * v.0 + v.1 * v.1 + v.2 * v.2).sqrt();
                        p.set_item("is_supersonic", speed > 2300.0)?;
                        let sleeping = *car_sleeping.get(&aid).unwrap_or(&false);
                        p.set_item("sleeping", sleeping)?;
                        p.set_item("is_on_ground", z <= 18.0 || sleeping)?;
                        p.set_item("is_demolished", *car_demo.get(&aid).unwrap_or(&false))?;
                        if let Some(active) = owner_jump_state.get(&aid) {
                            p.set_item("is_jumping", *active)?;
                        }
                        if let Some(raw) = owner_jump_raw.get(&aid) {
                            p.set_item("jump_active_raw", *raw)?;
                        }
                        if let Some(active) = owner_dodge_state.get(&aid) {
                            p.set_item("is_dodging", *active)?;
                        }
                        if let Some(raw) = owner_dodge_raw.get(&aid) {
                            p.set_item("dodge_active_raw", *raw)?;
                        }
                        if let Some(active) = owner_double_jump_state.get(&aid) {
                            p.set_item("is_double_jumping", *active)?;
                        }
                        if let Some(raw) = owner_double_jump_raw.get(&aid) {
                            p.set_item("double_jump_active_raw", *raw)?;
                        }
                        if let Some(active) = owner_boost_state.get(&aid) {
                            p.set_item("boost_active", *active)?;
                        }
                        if let Some(raw) = owner_boost_raw.get(&aid) {
                            p.set_item("boost_active_raw", *raw)?;
                        }

                        players_map.insert(idx, p.into_py(py));
                    }
                }
                let players = PyList::empty_bound(py);
                for (_idx, pobj) in players_map.iter() {
                    players.append(pobj.bind(py))?;
                }
                f.set_item("players", players)?;
                let parser_meta = PyDict::new_bound(py);
                parser_meta.set_item("classification_source", frame_classification_source)?;
                f.set_item("_parser_meta", parser_meta)?;

                let pad_list = PyList::empty_bound(py);
                for event in frame_pad_events {
                    let pad_dict = PyDict::new_bound(py);
                    pad_dict.set_item("pad_id", event.pad_id as i64)?;
                    pad_dict.set_item("is_big", event.is_big)?;
                    pad_dict.set_item("pad_side", event.pad_side)?;
                    pad_dict.set_item("arena", event.arena)?;
                    pad_dict.set_item("arena_supported", event.arena_supported)?;
                    pad_dict.set_item("status", event.status.as_str())?;
                    pad_dict.set_item("object_name", event.object_name.clone())?;
                    pad_dict.set_item("raw_state", event.raw_state)?;
                    pad_dict.set_item("timestamp", event.timestamp as f64)?;

                    let pos_dict = PyDict::new_bound(py);
                    pos_dict.set_item("x", event.position.0)?;
                    pos_dict.set_item("y", event.position.1)?;
                    pos_dict.set_item("z", event.position.2)?;
                    pad_dict.set_item("position", pos_dict)?;

                    if let Some(raw_actor) = event.instigator_actor_id {
                        pad_dict.set_item("instigator_actor_id", raw_actor)?;
                    }
                    if let Some(resolved) = event.resolved_actor_id {
                        pad_dict.set_item("actor_id", resolved)?;
                        if let Some(idx) = actor_to_player_index.get(&resolved) {
                            pad_dict.set_item("player_index", *idx as i64)?;
                            pad_dict.set_item("player_id", format!("player_{}", idx))?;
                        }
                        if let Some(team) = car_team.get(&resolved) {
                            pad_dict.set_item("player_team", *team)?;
                        }
                    }
                    if let Some(dist) = event.snap_distance {
                        pad_dict.set_item("snap_distance", dist as f64)?;
                    }
                    if let Some(err) = event.snap_error_uu {
                        pad_dict.set_item("snap_error_uu", err as f64)?;
                    }

                    pad_list.append(pad_dict)?;
                }
                f.set_item("boost_pad_events", pad_list)?;

                let parser_demo_events = PyList::empty_bound(py);
                let mut emitted_demo_victims: HashSet<i32> = HashSet::new();
                for (victim_actor_id, attacker_actor_id) in &frame_demo_records {
                    let Some(victim_index) = actor_to_player_index.get(victim_actor_id) else {
                        continue;
                    };
                    let demo_dict = PyDict::new_bound(py);
                    demo_dict.set_item("timestamp", nf.time as f64)?;
                    demo_dict.set_item("victim_id", format!("player_{}", victim_index))?;
                    if let Some(team) = car_team.get(victim_actor_id) {
                        demo_dict.set_item("victim_team", *team)?;
                    }
                    if let Some(attacker_actor_id) = attacker_actor_id {
                        if let Some(attacker_index) = actor_to_player_index.get(attacker_actor_id) {
                            demo_dict
                                .set_item("attacker_id", format!("player_{}", attacker_index))?;
                        }
                        if let Some(team) = car_team.get(attacker_actor_id) {
                            demo_dict.set_item("attacker_team", *team)?;
                        }
                    }
                    demo_dict.set_item("frame_index", frame_index)?;
                    demo_dict.set_item("source", "parser")?;
                    parser_demo_events.append(demo_dict)?;
                    emitted_demo_victims.insert(*victim_actor_id);
                }
                for (actor_id, is_demolished) in &car_demo {
                    let was_demolished = *prev_demo_state.get(actor_id).unwrap_or(&false);
                    if !was_demolished && *is_demolished {
                        if emitted_demo_victims.contains(actor_id) {
                            continue;
                        }
                        if let Some(idx) = actor_to_player_index.get(actor_id) {
                            let demo_dict = PyDict::new_bound(py);
                            demo_dict.set_item("timestamp", nf.time as f64)?;
                            demo_dict.set_item("victim_id", format!("player_{}", idx))?;
                            if let Some(team) = car_team.get(actor_id) {
                                demo_dict.set_item("victim_team", *team)?;
                            }
                            demo_dict.set_item("frame_index", frame_index)?;
                            demo_dict.set_item("source", "parser")?;
                            parser_demo_events.append(demo_dict)?;
                        }
                    }
                }
                prev_demo_state = car_demo.clone();

                let component_events = PyList::empty_bound(py);
                for event in &frame_component_events {
                    let event_dict = PyDict::new_bound(py);
                    event_dict.set_item("timestamp", nf.time as f64)?;
                    event_dict.set_item("frame_index", frame_index)?;
                    event_dict.set_item("kind", event.kind)?;
                    event_dict.set_item("component", event.component)?;
                    event_dict.set_item("actor_id", event.owner_actor_id)?;
                    if let Some(idx) = actor_to_player_index.get(&event.owner_actor_id) {
                        event_dict.set_item("player_id", format!("player_{}", idx))?;
                    }
                    if let Some(team) = car_team.get(&event.owner_actor_id) {
                        event_dict.set_item("team", *team)?;
                    }
                    if let Some(active) = event.active {
                        event_dict.set_item("active", active)?;
                    }
                    if let Some(raw_value) = event.raw_value {
                        event_dict.set_item("raw_value", raw_value)?;
                    }
                    if let Some((x, y, z)) = event.vector {
                        let vector = PyDict::new_bound(py);
                        vector.set_item("x", x)?;
                        vector.set_item("y", y)?;
                        vector.set_item("z", z)?;
                        event_dict.set_item("vector", vector)?;
                    }
                    event_dict.set_item("source", "parser")?;
                    component_events.append(event_dict)?;
                }
                f.set_item("component_events", component_events)?;

                let parser_stat_events = PyList::empty_bound(py);
                for event in &frame_stat_events {
                    let event_dict = PyDict::new_bound(py);
                    event_dict.set_item("timestamp", nf.time as f64)?;
                    event_dict.set_item("frame_index", frame_index)?;
                    event_dict.set_item("object_id", event.object_id)?;
                    if let Some(object_name) = &event.object_name {
                        event_dict.set_item("object_name", object_name)?;
                    }
                    event_dict.set_item("unknown1", event.unknown1)?;
                    event_dict.set_item("source", "parser")?;
                    parser_stat_events.append(event_dict)?;
                }
                f.set_item("parser_stat_events", parser_stat_events)?;

                // Detect touches: proximity-based ball-car contact detection
                let parser_touch_events = PyList::empty_bound(py);
                for (actor_id, car_position) in &car_pos {
                    let dist = distance_3d(*car_position, ball_pos);
                    if dist >= TOUCH_PROXIMITY_THRESHOLD {
                        continue;
                    }

                    let last_time = last_touch_time.get(actor_id);
                    let last_pos = last_touch_pos.get(actor_id);
                    let timestamp = nf.time as f64;

                    let is_new_touch = if let Some(last_t) = last_time {
                        let delta_t = timestamp - last_t;
                        // Must wait debounce time between touches
                        if delta_t < TOUCH_DEBOUNCE_TIME {
                            continue;
                        }
                        // If same area, skip (debounce on location too)
                        if let Some(last_p) = last_pos {
                            let loc_dist = distance_3d(*car_position, *last_p);
                            if loc_dist <= TOUCH_LOCATION_EPS && delta_t < TOUCH_DEBOUNCE_TIME * 2.0
                            {
                                continue;
                            }
                        }
                        true // Enough time has passed, this is a new touch
                    } else {
                        true // First touch for this actor
                    };

                    if is_new_touch {
                        if let Some(idx) = actor_to_player_index.get(actor_id) {
                            let touch_dict = PyDict::new_bound(py);
                            touch_dict.set_item("timestamp", timestamp)?;
                            touch_dict.set_item("player_id", format!("player_{}", idx))?;
                            if let Some(team) = car_team.get(actor_id) {
                                touch_dict.set_item("team", *team)?;
                            } else {
                                touch_dict.set_item("team", 0i64)?;
                            }
                            touch_dict.set_item("frame_index", frame_index)?;
                            touch_dict.set_item("source", "parser")?;
                            parser_touch_events.append(touch_dict)?;

                            last_touch_time.insert(*actor_id, timestamp);
                            last_touch_pos.insert(*actor_id, *car_position);
                        }
                    }
                }

                f.set_item("parser_touch_events", parser_touch_events)?;
                f.set_item("parser_demo_events", parser_demo_events)?;
                let parser_tickmarks = PyList::empty_bound(py);
                if let Some(tickmarks) = tickmarks_by_frame.get(&frame_index) {
                    for (description, tickmark_frame) in tickmarks {
                        let tickmark_dict = PyDict::new_bound(py);
                        tickmark_dict.set_item("timestamp", nf.time as f64)?;
                        tickmark_dict.set_item("kind", description.clone())?;
                        tickmark_dict.set_item("frame_index", *tickmark_frame)?;
                        let payload = PyDict::new_bound(py);
                        payload.set_item("description", description.clone())?;
                        payload.set_item("frame", *tickmark_frame)?;
                        tickmark_dict.set_item("payload", payload)?;
                        tickmark_dict.set_item("source", "parser")?;
                        parser_tickmarks.append(tickmark_dict)?;
                    }
                }
                f.set_item("parser_tickmarks", parser_tickmarks)?;

                let parser_kickoff_markers = PyList::empty_bound(py);
                let at_center = ball_pos.0.abs() <= KICKOFF_POSITION_TOLERANCE as f32
                    && ball_pos.1.abs() <= KICKOFF_POSITION_TOLERANCE as f32
                    && (ball_pos.2 - BALL_REST_HEIGHT as f32).abs()
                        <= KICKOFF_POSITION_TOLERANCE as f32;
                let ball_speed =
                    (ball_vel.0 * ball_vel.0 + ball_vel.1 * ball_vel.1 + ball_vel.2 * ball_vel.2)
                        .sqrt();
                let stationary = ball_speed <= BALL_STATIONARY_SPEED as f32;
                if at_center && stationary && !kickoff_active {
                    kickoff_active = true;
                    let marker = PyDict::new_bound(py);
                    marker.set_item("timestamp", nf.time as f64)?;
                    marker.set_item(
                        "phase",
                        infer_kickoff_phase(nf.time as f64, header_overtime, header_match_length),
                    )?;
                    marker.set_item("frame_index", frame_index)?;
                    marker.set_item("source", "parser")?;
                    parser_kickoff_markers.append(marker)?;
                }
                if !at_center || !stationary {
                    kickoff_active = false;
                }
                f.set_item("parser_kickoff_markers", parser_kickoff_markers)?;

                frames_out.append(f)?;
                frame_index += 1;
            }
        }

        // Resolve per-PRI camera/loadout buffers to header player indices. PRI->index
        // bindings accumulate across the whole replay (PRI name decode), so a player's
        // profile survives respawns even though their actor ids may have churned.
        // Iterate PRIs in a deterministic order so that, in the rare case two PRIs
        // resolve to the same header index (e.g. reconnect on a fresh channel), the
        // highest PRI id wins rather than HashMap iteration order. Camera and direct
        // loadout sort ascending and overwrite (highest is inserted last); the
        // team-loadout fallback sorts descending so its `or_insert_with` (first
        // write wins) also lands on the highest PRI.
        let mut camera_by_index: HashMap<usize, boxcars::CamSettings> = HashMap::new();
        let mut camera_entries: Vec<_> = camera_by_pri.iter().collect();
        camera_entries.sort_by_key(|(pri, _)| **pri);
        for (pri, cam) in camera_entries {
            if let Some(idx) = owner_to_player_index.get(pri) {
                camera_by_index.insert(*idx, *cam);
            }
        }
        let mut loadout_by_index: HashMap<usize, boxcars::Loadout> = HashMap::new();
        let mut loadout_entries: Vec<_> = loadout_by_pri.iter().collect();
        loadout_entries.sort_by_key(|(pri, _)| **pri);
        for (pri, loadout) in loadout_entries {
            if let Some(idx) = owner_to_player_index.get(pri) {
                loadout_by_index.insert(*idx, *loadout);
            }
        }
        // Fill in team loadouts for players who only had ClientLoadouts (not a
        // direct ClientLoadout). The player's team is known here, so blue/orange
        // resolves correctly. A direct Loadout, if present, takes priority.
        let mut team_loadout_entries: Vec<_> = team_loadout_by_pri.iter().collect();
        team_loadout_entries.sort_by_key(|(pri, _)| std::cmp::Reverse(**pri));
        for (pri, team_loadout) in team_loadout_entries {
            if let Some(idx) = owner_to_player_index.get(pri) {
                loadout_by_index.entry(*idx).or_insert_with(|| {
                    let team = header_players.get(*idx).map(|(_, team)| *team);
                    team_loadout_for(team, team_loadout)
                });
            }
        }

        let player_metadata = PyDict::new_bound(py);
        let mut metadata_indices: BTreeSet<usize> = BTreeSet::new();
        metadata_indices.extend(camera_by_index.keys().copied());
        metadata_indices.extend(loadout_by_index.keys().copied());
        for idx in metadata_indices {
            let entry = PyDict::new_bound(py);
            entry.set_item(
                "name",
                header_players.get(idx).map(|(name, _)| name.clone()),
            )?;
            match camera_by_index.get(&idx) {
                Some(cam) => {
                    let camera = PyDict::new_bound(py);
                    for (key, value) in cam_settings_pairs(cam) {
                        camera.set_item(key, value)?;
                    }
                    entry.set_item("camera", camera)?;
                }
                None => entry.set_item("camera", py.None())?,
            }
            match loadout_by_index.get(&idx) {
                Some(loadout) => {
                    let loadout_dict = PyDict::new_bound(py);
                    for (key, value) in loadout_pairs(loadout) {
                        loadout_dict.set_item(key, value)?;
                    }
                    entry.set_item("loadout", loadout_dict)?;
                }
                None => entry.set_item("loadout", py.None())?,
            }
            player_metadata.set_item(idx as i64, entry)?;
        }

        Ok((frames_out.into(), player_metadata.into()))
    })
}

#[pyfunction]
fn iter_frames(path: &str) -> PyResult<Py<PyAny>> {
    Ok(run_iter_frames(path)?.0)
}

#[pyfunction]
fn parse_network_with_diagnostics(path: &str) -> PyResult<PyObject> {
    Python::with_gil(|py| {
        let result = PyDict::new_bound(py);
        let diagnostics = PyDict::new_bound(py);
        diagnostics.set_item("attempted_backends", vec!["boxcars"])?;

        match run_iter_frames(path) {
            Ok((frames_any, player_metadata)) => {
                let frames_len = frames_any.bind(py).len().unwrap_or(0);
                diagnostics.set_item("status", "ok")?;
                diagnostics.set_item("error_code", py.None())?;
                diagnostics.set_item("error_detail", py.None())?;
                diagnostics.set_item("frames_emitted", frames_len as i64)?;
                result.set_item("frames", frames_any)?;
                result.set_item("player_metadata", player_metadata)?;
                result.set_item("diagnostics", diagnostics)?;
                Ok(result.to_object(py))
            }
            Err(primary_err) => {
                let primary_message = primary_err.to_string();
                let error_code = map_network_error_code(&primary_message);
                let mut detail = primary_message.clone();
                let fallback_frames = PyList::empty_bound(py);
                let mut fallback_frames_emitted: usize = 0;

                match read_file_bytes(path) {
                    Ok(data) => match ParserBuilder::new(&data)
                        .ignore_network_data_on_error()
                        .parse()
                    {
                        Ok(replay) => {
                            if let Some(net) = replay.network_frames {
                                for nf in net.frames {
                                    let f = PyDict::new_bound(py);
                                    f.set_item("timestamp", nf.time as f64)?;
                                    f.set_item("delta", nf.delta as f64)?;

                                    let ball = PyDict::new_bound(py);
                                    let bpos = PyDict::new_bound(py);
                                    bpos.set_item("x", 0.0f64)?;
                                    bpos.set_item("y", 0.0f64)?;
                                    bpos.set_item("z", 93.15f64)?;
                                    let bvel = PyDict::new_bound(py);
                                    bvel.set_item("x", 0.0f64)?;
                                    bvel.set_item("y", 0.0f64)?;
                                    bvel.set_item("z", 0.0f64)?;
                                    let bang = PyDict::new_bound(py);
                                    bang.set_item("x", 0.0f64)?;
                                    bang.set_item("y", 0.0f64)?;
                                    bang.set_item("z", 0.0f64)?;
                                    ball.set_item("position", bpos)?;
                                    ball.set_item("velocity", bvel)?;
                                    ball.set_item("angular_velocity", bang)?;
                                    ball.set_item("sleeping", false)?;
                                    f.set_item("ball", ball)?;
                                    f.set_item("players", PyList::empty_bound(py))?;
                                    f.set_item("boost_pad_events", PyList::empty_bound(py))?;
                                    f.set_item("component_events", PyList::empty_bound(py))?;
                                    f.set_item("parser_touch_events", PyList::empty_bound(py))?;
                                    f.set_item("parser_demo_events", PyList::empty_bound(py))?;
                                    f.set_item("parser_stat_events", PyList::empty_bound(py))?;
                                    f.set_item("parser_tickmarks", PyList::empty_bound(py))?;
                                    f.set_item("parser_kickoff_markers", PyList::empty_bound(py))?;

                                    let parser_meta = PyDict::new_bound(py);
                                    parser_meta.set_item(
                                        "classification_source",
                                        "fallback_unclassified",
                                    )?;
                                    f.set_item("_parser_meta", parser_meta)?;
                                    fallback_frames.append(f)?;
                                }
                            }
                            fallback_frames_emitted = fallback_frames.len();
                        }
                        Err(fallback_err) => {
                            detail = format!(
                                "{}; fallback_ignore_network_data_on_error: {}",
                                detail, fallback_err
                            );
                        }
                    },
                    Err(read_err) => {
                        detail = format!("{}; fallback_read_error: {}", detail, read_err);
                    }
                }

                diagnostics.set_item("status", "degraded")?;
                diagnostics.set_item("error_code", error_code)?;
                diagnostics.set_item("error_detail", detail)?;
                diagnostics.set_item("frames_emitted", fallback_frames_emitted as i64)?;
                result.set_item("frames", fallback_frames)?;
                result.set_item("player_metadata", PyDict::new_bound(py))?;
                result.set_item("diagnostics", diagnostics)?;
                Ok(result.to_object(py))
            }
        }
    })
}

/// Debug harness: expose early-frame actor mappings and attribute kinds to Python.
#[pyfunction]
pub fn debug_first_frames(path: &str, max_frames: usize) -> PyResult<Py<PyAny>> {
    Python::with_gil(|py| {
        let data = read_file_bytes(path)?;
        let replay = ParserBuilder::new(&data)
            .must_parse_network_data()
            .parse()
            .map_err(|e| PyValueError::new_err(format!("Failed to parse network frames: {e}")))?;

        let out = PyList::empty_bound(py);
        let objects = &replay.objects;

        let mut actor_object_name: HashMap<i32, String> = HashMap::new();
        let mut component_owner: HashMap<i32, i32> = HashMap::new();
        let mut boost_actor_ids: HashSet<i32> = HashSet::new();

        fn resolve_actor(component_owner: &HashMap<i32, i32>, actor: i32) -> (i32, Vec<i32>) {
            let mut current = actor;
            let mut chain: Vec<i32> = Vec::new();
            let mut guard = 0;
            while let Some(owner) = component_owner.get(&current) {
                chain.push(*owner);
                if *owner == current {
                    break;
                }
                current = *owner;
                guard += 1;
                if guard > 12 {
                    break;
                }
            }
            (current, chain)
        }

        fn pickup_state_label(raw: u8) -> &'static str {
            match raw {
                0 | 255 => "RESPAWNED",
                1..=3 => "COLLECTED",
                _ => "UNKNOWN",
            }
        }

        if let Some(net) = replay.network_frames {
            for (frame_idx, nf) in net.frames.iter().enumerate() {
                if frame_idx >= max_frames {
                    break;
                }

                let frame_dict = PyDict::new_bound(py);
                frame_dict.set_item("frame_index", frame_idx as i64)?;
                frame_dict.set_item("timestamp", nf.time as f64)?;

                let new_actors_py = PyList::empty_bound(py);
                let updated_py = PyList::empty_bound(py);
                let boost_events_py = PyList::empty_bound(py);

                for deleted in &nf.deleted_actors {
                    let aid: i32 = (*deleted).into();
                    actor_object_name.remove(&aid);
                    boost_actor_ids.remove(&aid);
                    component_owner.retain(|comp, owner| *comp != aid && *owner != aid);
                }

                for na in &nf.new_actors {
                    let oid_usize: usize = na.object_id.into();
                    let object_name = objects
                        .get(oid_usize)
                        .cloned()
                        .unwrap_or_else(|| format!("object_id:{}", oid_usize));
                    let actor_id: i32 = na.actor_id.into();
                    let object_id: i32 = na.object_id.into();

                    actor_object_name.insert(actor_id, object_name.clone());
                    let is_boost_actor = object_name.contains("VehiclePickup_Boost_TA");
                    if is_boost_actor {
                        boost_actor_ids.insert(actor_id);
                    }

                    let actor_dict = PyDict::new_bound(py);
                    actor_dict.set_item("actor_id", actor_id as i64)?;
                    actor_dict.set_item("object_id", object_id as i64)?;
                    actor_dict.set_item("object_name", object_name.clone())?;

                    let trajectory_dict = PyDict::new_bound(py);
                    if let Some(loc) = na.initial_trajectory.location {
                        let loc_world = PyDict::new_bound(py);
                        loc_world.set_item("x", (loc.x as f64) / 100.0)?;
                        loc_world.set_item("y", (loc.y as f64) / 100.0)?;
                        loc_world.set_item("z", (loc.z as f64) / 100.0)?;
                        let loc_raw = PyDict::new_bound(py);
                        loc_raw.set_item("x", loc.x)?;
                        loc_raw.set_item("y", loc.y)?;
                        loc_raw.set_item("z", loc.z)?;
                        trajectory_dict.set_item("location", loc_world)?;
                        trajectory_dict.set_item("location_raw", loc_raw)?;
                    }
                    if let Some(rot) = na.initial_trajectory.rotation {
                        let rot_dict = PyDict::new_bound(py);
                        if let Some(yaw) = rot.yaw {
                            rot_dict.set_item("yaw", yaw)?;
                        }
                        if let Some(pitch) = rot.pitch {
                            rot_dict.set_item("pitch", pitch)?;
                        }
                        if let Some(roll) = rot.roll {
                            rot_dict.set_item("roll", roll)?;
                        }
                        if !rot_dict.is_empty() {
                            trajectory_dict.set_item("rotation", rot_dict)?;
                        }
                    }
                    if !trajectory_dict.is_empty() {
                        actor_dict.set_item("initial_trajectory", trajectory_dict)?;
                    }

                    new_actors_py.append(actor_dict)?;

                    if is_boost_actor {
                        let event = PyDict::new_bound(py);
                        event.set_item("event", "trajectory")?;
                        event.set_item("actor_id", actor_id as i64)?;
                        event.set_item("object_name", object_name)?;
                        event.set_item("timestamp", nf.time as f64)?;
                        if let Some(loc) = na.initial_trajectory.location {
                            let loc_dict = PyDict::new_bound(py);
                            loc_dict.set_item("x", (loc.x as f64) / 100.0)?;
                            loc_dict.set_item("y", (loc.y as f64) / 100.0)?;
                            loc_dict.set_item("z", (loc.z as f64) / 100.0)?;
                            event.set_item("location", loc_dict)?;
                        }
                        boost_events_py.append(event)?;
                    }
                }

                for ua in &nf.updated_actors {
                    let actor_id: i32 = ua.actor_id.into();
                    let attribute_repr = format!("{:?}", ua.attribute);
                    let update_dict = PyDict::new_bound(py);
                    update_dict.set_item("actor_id", actor_id as i64)?;
                    update_dict.set_item("attribute", attribute_repr)?;
                    if let Some(obj) = actor_object_name.get(&actor_id) {
                        update_dict.set_item("object_name", obj)?;
                    }

                    match &ua.attribute {
                        Attribute::ActiveActor(active) => {
                            let lower = actor_object_name
                                .get(&actor_id)
                                .map(|s| s.to_ascii_lowercase())
                                .unwrap_or_default();
                            if lower.contains("carcomponent") {
                                let owner_id: i32 = active.actor.into();
                                component_owner.insert(actor_id, owner_id);
                            }
                        }
                        Attribute::RigidBody(rb) => {
                            let detail = PyDict::new_bound(py);
                            detail.set_item("sleeping", rb.sleeping)?;
                            let loc_dict = PyDict::new_bound(py);
                            loc_dict.set_item("x", rb.location.x)?;
                            loc_dict.set_item("y", rb.location.y)?;
                            loc_dict.set_item("z", rb.location.z)?;
                            detail.set_item("location", loc_dict)?;
                            if let Some(lv) = rb.linear_velocity {
                                let vel_dict = PyDict::new_bound(py);
                                vel_dict.set_item("x", lv.x)?;
                                vel_dict.set_item("y", lv.y)?;
                                vel_dict.set_item("z", lv.z)?;
                                detail.set_item("linear_velocity", vel_dict)?;
                            }
                            if let Some(av) = rb.angular_velocity {
                                let ang_dict = PyDict::new_bound(py);
                                ang_dict.set_item("x", av.x)?;
                                ang_dict.set_item("y", av.y)?;
                                ang_dict.set_item("z", av.z)?;
                                detail.set_item("angular_velocity", ang_dict)?;
                            }
                            update_dict.set_item("detail", detail)?;
                            if boost_actor_ids.contains(&actor_id) {
                                let event = PyDict::new_bound(py);
                                event.set_item("event", "rigid_body")?;
                                event.set_item("actor_id", actor_id as i64)?;
                                if let Some(obj) = actor_object_name.get(&actor_id) {
                                    event.set_item("object_name", obj)?;
                                }
                                event.set_item("timestamp", nf.time as f64)?;
                                let loc_event = PyDict::new_bound(py);
                                loc_event.set_item("x", rb.location.x)?;
                                loc_event.set_item("y", rb.location.y)?;
                                loc_event.set_item("z", rb.location.z)?;
                                event.set_item("location", loc_event)?;
                                event.set_item("sleeping", rb.sleeping)?;
                                if let Some(lv) = rb.linear_velocity {
                                    let vel_dict = PyDict::new_bound(py);
                                    vel_dict.set_item("x", lv.x)?;
                                    vel_dict.set_item("y", lv.y)?;
                                    vel_dict.set_item("z", lv.z)?;
                                    event.set_item("linear_velocity", vel_dict)?;
                                }
                                if let Some(av) = rb.angular_velocity {
                                    let ang_dict = PyDict::new_bound(py);
                                    ang_dict.set_item("x", av.x)?;
                                    ang_dict.set_item("y", av.y)?;
                                    ang_dict.set_item("z", av.z)?;
                                    event.set_item("angular_velocity", ang_dict)?;
                                }
                                boost_events_py.append(event)?;
                            }
                        }
                        Attribute::Pickup(pickup) => {
                            let detail = PyDict::new_bound(py);
                            detail.set_item("picked_up", pickup.picked_up)?;
                            if let Some(instigator) = pickup.instigator {
                                let raw_actor: i32 = instigator.into();
                                detail.set_item("instigator_actor_id", raw_actor)?;
                                let (resolved, chain) = resolve_actor(&component_owner, raw_actor);
                                if resolved != raw_actor {
                                    detail.set_item("resolved_actor_id", resolved)?;
                                }
                                if !chain.is_empty() {
                                    let chain_py = PyList::empty_bound(py);
                                    for item in chain {
                                        chain_py.append(item as i64)?;
                                    }
                                    detail.set_item("owner_chain", chain_py)?;
                                }
                            }
                            update_dict.set_item("detail", detail)?;
                            if boost_actor_ids.contains(&actor_id) {
                                let event = PyDict::new_bound(py);
                                event.set_item("event", "pickup_state")?;
                                event.set_item("actor_id", actor_id as i64)?;
                                if let Some(obj) = actor_object_name.get(&actor_id) {
                                    event.set_item("object_name", obj)?;
                                }
                                event.set_item("timestamp", nf.time as f64)?;
                                event.set_item(
                                    "state",
                                    if pickup.picked_up {
                                        "COLLECTED"
                                    } else {
                                        "RESPAWNED"
                                    },
                                )?;
                                if let Some(instigator) = pickup.instigator {
                                    let raw_actor: i32 = instigator.into();
                                    event.set_item("instigator_actor_id", raw_actor)?;
                                    let (resolved, chain) =
                                        resolve_actor(&component_owner, raw_actor);
                                    if resolved != raw_actor {
                                        event.set_item("resolved_actor_id", resolved)?;
                                    }
                                    if !chain.is_empty() {
                                        let chain_py = PyList::empty_bound(py);
                                        for item in chain {
                                            chain_py.append(item as i64)?;
                                        }
                                        event.set_item("owner_chain", chain_py)?;
                                    }
                                }
                                boost_events_py.append(event)?;
                            }
                        }
                        Attribute::PickupNew(pickup_new) => {
                            let detail = PyDict::new_bound(py);
                            detail.set_item("raw_state", pickup_new.picked_up)?;
                            detail.set_item("state", pickup_state_label(pickup_new.picked_up))?;
                            if let Some(instigator) = pickup_new.instigator {
                                let raw_actor: i32 = instigator.into();
                                detail.set_item("instigator_actor_id", raw_actor)?;
                                let (resolved, chain) = resolve_actor(&component_owner, raw_actor);
                                if resolved != raw_actor {
                                    detail.set_item("resolved_actor_id", resolved)?;
                                }
                                if !chain.is_empty() {
                                    let chain_py = PyList::empty_bound(py);
                                    for item in chain {
                                        chain_py.append(item as i64)?;
                                    }
                                    detail.set_item("owner_chain", chain_py)?;
                                }
                            }
                            update_dict.set_item("detail", detail)?;
                            if boost_actor_ids.contains(&actor_id) {
                                let event = PyDict::new_bound(py);
                                event.set_item("event", "pickup_new")?;
                                event.set_item("actor_id", actor_id as i64)?;
                                if let Some(obj) = actor_object_name.get(&actor_id) {
                                    event.set_item("object_name", obj)?;
                                }
                                event.set_item("timestamp", nf.time as f64)?;
                                event.set_item("raw_state", pickup_new.picked_up)?;
                                event
                                    .set_item("state", pickup_state_label(pickup_new.picked_up))?;
                                if let Some(instigator) = pickup_new.instigator {
                                    let raw_actor: i32 = instigator.into();
                                    event.set_item("instigator_actor_id", raw_actor)?;
                                    let (resolved, chain) =
                                        resolve_actor(&component_owner, raw_actor);
                                    if resolved != raw_actor {
                                        event.set_item("resolved_actor_id", resolved)?;
                                    }
                                    if !chain.is_empty() {
                                        let chain_py = PyList::empty_bound(py);
                                        for item in chain {
                                            chain_py.append(item as i64)?;
                                        }
                                        event.set_item("owner_chain", chain_py)?;
                                    }
                                }
                                boost_events_py.append(event)?;
                            }
                        }
                        _ => {}
                    }

                    updated_py.append(update_dict)?;
                }

                frame_dict.set_item("new_actors", new_actors_py)?;
                frame_dict.set_item("updated_actors", updated_py)?;
                frame_dict.set_item("boost_events", boost_events_py)?;
                out.append(frame_dict)?;
            }
        }

        Ok(out.into())
    })
}

#[pyfunction]
fn net_frame_count(path: &str) -> PyResult<usize> {
    let data = read_file_bytes(path)?;
    let replay = ParserBuilder::new(&data)
        .must_parse_network_data()
        .parse()
        .map_err(|e| PyValueError::new_err(format!("Failed to parse network frames: {e}")))?;
    Ok(replay.network_frames.map(|nf| nf.frames.len()).unwrap_or(0))
}

#[pymodule]
fn rlreplay_rust(_py: Python, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(parse_header, m)?)?;
    m.add_function(wrap_pyfunction!(iter_frames, m)?)?;
    m.add_function(wrap_pyfunction!(parse_network_with_diagnostics, m)?)?;
    m.add_function(wrap_pyfunction!(header_property_keys, m)?)?;
    m.add_function(wrap_pyfunction!(header_property, m)?)?;
    m.add_function(wrap_pyfunction!(net_frame_count, m)?)?;
    m.add_function(wrap_pyfunction!(debug_first_frames, m)?)?;
    m.add("RUST_CORE", true)?;

    m.add(
        "__doc__",
        "Rust-backed RL replay parser (boxcars): header + network frames",
    )?;

    pyo3::prepare_freethreaded_python();
    Ok(())
}
