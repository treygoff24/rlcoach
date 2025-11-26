mod pads;

use pyo3::exceptions::{PyIOError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet};
use std::fs::File;
use std::io::Read;

// Boxcars parsing
use boxcars::{Attribute, NewActor, Vector3f};
use boxcars::{HeaderProp, ParserBuilder, Replay};

use pads::{PadEvent, PadRegistry};

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
            let list = PyList::empty(py);
            for inner in arr {
                let dict = PyDict::new(py);
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
            let dict = PyDict::new(py);
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
            let dict = PyDict::new(py);
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

        // Parsed fields
        let mut playlist_id: Option<String> = None;
        let mut map_name: Option<String> = None;
        let mut team0_score: i64 = 0;
        let mut team1_score: i64 = 0;
        let mut match_length: f64 = 0.0;
        let mut players_vec: Vec<(String, i64)> = Vec::new();
        let mut players_meta: Vec<PyObject> = Vec::new();
        let highlights_list = PyList::empty(py);
        let mut team_size: i64 = 0;
        let mut warnings_vec: Vec<String> = Vec::new();

        // Helper: get prop by key
        fn find_prop<'a>(
            props: &'a Vec<(String, HeaderProp)>,
            key: &str,
        ) -> Option<&'a HeaderProp> {
            props.iter().find(|(k, _)| k == key).map(|(_, v)| v)
        }

        // Prepare a goals list to populate if available
        let goals_list = PyList::empty(py);

        match ParserBuilder::new(&data).never_parse_network_data().parse() {
            Ok(Replay { properties, .. }) => {
                if let Some(p) = find_prop(&properties, "MapName") {
                    if let Some(s) = p.as_string() {
                        map_name = Some(s.to_string());
                    }
                }
                if let Some(p) = find_prop(&properties, "PlaylistID") {
                    if let Some(s) = p.as_string() {
                        playlist_id = Some(s.to_string());
                    }
                }
                if let Some(p) = find_prop(&properties, "BuildVersion") {
                    if let Some(s) = p.as_string() {
                        warnings_vec.push(format!("build_version:{}", s));
                    }
                }
                if let Some(p) = find_prop(&properties, "NumFrames") {
                    if let Some(fr) = p.as_i32() {
                        match_length = (fr as f64) / 30.0;
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
                            let stats_dict = PyDict::new(py);
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
                                let player_dict = PyDict::new(py);
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
                            let g = PyDict::new(py);
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
                            let h = PyDict::new(py);
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

        // Build Python dict
        let header = PyDict::new(py);
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

        if players_meta.is_empty() {
            let players = PyList::empty(py);
            for (name, team) in &players_vec {
                let p = PyDict::new(py);
                p.set_item("name", name)?;
                p.set_item("team", team)?;
                players.append(p)?;
            }
            header.set_item("players", players)?;
        } else {
            header.set_item("players", PyList::new(py, players_meta))?;
        }
        // Engine build (if captured in warnings)
        if let Some(build) = warnings_vec
            .iter()
            .find_map(|w| w.strip_prefix("build_version:"))
        {
            header.set_item("engine_build", build)?;
        }
        // Goals & highlights lists
        header.set_item("goals", goals_list)?;
        header.set_item("highlights", highlights_list)?;
        let warnings = PyList::empty(py);
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

    // Roll (x-axis rotation)
    let sinr_cosp = 2.0 * (w * x + y * z);
    let cosr_cosp = 1.0 - 2.0 * (x * x + y * y);
    let roll = sinr_cosp.atan2(cosr_cosp);

    // Pitch (y-axis rotation)
    let sinp = 2.0 * (w * y - z * x);
    let pitch = if sinp.abs() >= 1.0 {
        std::f64::consts::FRAC_PI_2.copysign(sinp)
    } else {
        sinp.asin()
    };

    // Yaw (z-axis rotation)
    let siny_cosp = 2.0 * (w * z + x * y);
    let cosy_cosp = 1.0 - 2.0 * (y * y + z * z);
    let yaw = siny_cosp.atan2(cosy_cosp);

    (roll, pitch, yaw)
}

#[pyfunction]
fn iter_frames(path: &str) -> PyResult<Py<PyAny>> {
    Python::with_gil(|py| {
        let data = read_file_bytes(path)?;
        // Parse with network data enabled
        let replay = ParserBuilder::new(&data)
            .must_parse_network_data()
            .parse()
            .map_err(|e| PyValueError::new_err(format!("Failed to parse network frames: {e}")))?;

        // Header-derived players with teams for mapping
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

        // Build mapping structures we maintain across frames
        let objects = &replay.objects;
        let mut actor_object_name: HashMap<i32, String> = HashMap::new();
        #[derive(Clone, Default)]
        struct ActorKind {
            is_ball: bool,
            is_car: bool,
        }
        let mut actor_kind: HashMap<i32, ActorKind> = HashMap::new();
        let mut car_team: HashMap<i32, i64> = HashMap::new();
        let mut car_boost: HashMap<i32, i64> = HashMap::new(); // 0-100
        let mut car_pos: HashMap<i32, (f32, f32, f32)> = HashMap::new();
        let mut car_vel: HashMap<i32, (f32, f32, f32)> = HashMap::new();
        let mut car_rot: HashMap<i32, (f32, f32, f32, f32)> = HashMap::new(); // quaternion (x,y,z,w)
        let mut car_demo: HashMap<i32, bool> = HashMap::new();
        let mut component_owner: HashMap<i32, i32> = HashMap::new();
        let mut pad_registry = PadRegistry::new();
        let mut ball_actor: Option<i32> = None;
        let mut ball_pos: (f32, f32, f32) = (0.0, 0.0, 93.15);
        let mut ball_vel: (f32, f32, f32) = (0.0, 0.0, 0.0);
        let mut ball_angvel: (f32, f32, f32) = (0.0, 0.0, 0.0);
        let mut actor_to_player_index: HashMap<i32, usize> = HashMap::new();
        let mut next_by_team: HashMap<i64, Vec<usize>> = HashMap::new();

        // Prepare per-team header order indices
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

        let frames_out = PyList::empty(py);

        // Helper: classify actors using object/class names
        fn classify_object_name(name: &str) -> ActorKind {
            let lname = name.to_ascii_lowercase();
            let is_ball =
                lname.contains("ball_ta") || lname.ends_with("ball") || lname.contains("ball_");
            let is_car = (lname.contains("archetypes.car.car_")
                || lname.contains("default__car_ta")
                || lname.contains("default__carbody"))
                && !lname.contains("carcomponent");
            ActorKind { is_ball, is_car }
        }

        if let Some(net) = replay.network_frames {
            for nf in net.frames {
                let mut frame_pad_events: Vec<PadEvent> = Vec::new();
                // Prune actors that were deleted before processing updates to avoid stale telemetry
                for deleted in nf.deleted_actors {
                    let aid: i32 = deleted.into();
                    let team_for_return = car_team.get(&aid).copied();
                    if ball_actor == Some(aid) {
                        ball_actor = None;
                        ball_pos = (0.0, 0.0, 93.15);
                        ball_vel = (0.0, 0.0, 0.0);
                        ball_angvel = (0.0, 0.0, 0.0);
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
                    car_team.remove(&aid);
                    car_boost.remove(&aid);
                    car_pos.remove(&aid);
                    car_vel.remove(&aid);
                    car_rot.remove(&aid);
                    car_demo.remove(&aid);
                    component_owner.retain(|comp, owner| *comp != aid && *owner != aid);
                    pad_registry.remove_actor(aid);
                }

                // Update actor_object_name mapping with new actors in this frame
                for NewActor {
                    actor_id,
                    object_id,
                    ..
                } in nf.new_actors
                {
                    let oid: usize = object_id.into();
                    let obj_name = objects.get(oid).cloned().unwrap_or_default();
                    let aid: i32 = actor_id.into();
                    actor_object_name.insert(aid, obj_name.clone());
                    let kind = classify_object_name(&obj_name);
                    if kind.is_ball {
                        ball_actor = Some(aid);
                        ball_pos = (0.0, 0.0, 93.15);
                        ball_vel = (0.0, 0.0, 0.0);
                        ball_angvel = (0.0, 0.0, 0.0);
                    }
                    if kind.is_ball || kind.is_car {
                        actor_kind.insert(aid, kind);
                    }
                    pad_registry.track_new_actor(aid, &obj_name);
                }

                // Process updates
                for upd in nf.updated_actors {
                    let aid: i32 = upd.actor_id.into();
                    match upd.attribute {
                        Attribute::ActiveActor(active) => {
                            let obj_name = actor_object_name.get(&aid).cloned().unwrap_or_default();
                            if obj_name.to_ascii_lowercase().contains("carcomponent") {
                                let owner_id: i32 = active.actor.into();
                                component_owner.insert(aid, owner_id);
                            }
                        }
                        // Primary physics carrier observed across builds
                        Attribute::RigidBody(rb) => {
                            let obj_name = actor_object_name.get(&aid).cloned().unwrap_or_default();
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
                            let is_ball = Some(aid) == ball_actor || obj_name.contains("Ball_TA");
                            if is_ball {
                                ball_actor = Some(aid);
                                ball_pos = (loc.x, loc.y, loc.z);
                                ball_vel = (vel.x, vel.y, vel.z);
                                ball_angvel = (ang.x, ang.y, ang.z);
                            } else {
                                car_pos.insert(aid, (loc.x, loc.y, loc.z));
                                car_vel.insert(aid, (vel.x, vel.y, vel.z));
                                // Extract quaternion rotation from RigidBody
                                let rot = rb.rotation;
                                car_rot.insert(aid, (rot.x, rot.y, rot.z, rot.w));
                            }
                            let events = pad_registry.update_position(aid, (loc.x, loc.y, loc.z));
                            frame_pad_events.extend(events);
                        }
                        // Some builds carry these separately
                        Attribute::Location(loc) => {
                            if Some(aid) == ball_actor {
                                ball_pos = (loc.x, loc.y, loc.z);
                            } else {
                                car_pos.insert(aid, (loc.x, loc.y, loc.z));
                            }
                            let events = pad_registry.update_position(aid, (loc.x, loc.y, loc.z));
                            frame_pad_events.extend(events);
                        }

                        Attribute::PickupNew(pickup) => {
                            let mut raw_actor_opt: Option<i32> = None;
                            let mut resolved_actor: Option<i32> = None;
                            if let Some(instigator) = pickup.instigator {
                                let raw_actor: i32 = instigator.into();
                                raw_actor_opt = Some(raw_actor);
                                let mut resolved = raw_actor;
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
                                resolved_actor = Some(resolved);
                            }

                            let events = pad_registry.handle_pickup(
                                aid,
                                pickup.picked_up,
                                nf.time as f32,
                                raw_actor_opt,
                                resolved_actor,
                                resolved_actor.and_then(|actor| car_pos.get(&actor).copied()),
                            );
                            frame_pad_events.extend(events);
                        }
                        // Team + visual paint data (use team assignment if present)
                        Attribute::TeamPaint(tp) => {
                            let t = (tp.team as i64).clamp(0, 1);
                            car_team.insert(aid, t);
                            if actor_kind
                                .get(&aid)
                                .map(|kind| !kind.is_car)
                                .unwrap_or(true)
                            {
                                continue;
                            }
                            if !actor_to_player_index.contains_key(&aid) {
                                if let Some(v) = next_by_team.get_mut(&t) {
                                    if let Some(idx) = v.first().cloned() {
                                        v.remove(0);
                                        actor_to_player_index.insert(aid, idx);
                                    }
                                }
                            }
                        }
                        // Boost value replication (0..=255) → scale to 0..=100
                        Attribute::ReplicatedBoost(rb) => {
                            let amt = ((rb.boost_amount as f64) * (100.0 / 255.0)).round() as i64;
                            let target = component_owner.get(&aid).cloned().unwrap_or(aid);
                            car_boost.insert(target, amt.clamp(0, 100));
                        }
                        // Demolition signals (varies by build)
                        Attribute::Demolish(_)
                        | Attribute::DemolishExtended(_)
                        | Attribute::DemolishFx(_) => {
                            car_demo.insert(aid, true);
                        }
                        // Note: Jump/Dodge/Throttle/Steer/Handbrake attributes are not directly
                        // exposed by boxcars 0.10.7. These mechanics will be inferred in Python
                        // from physics state changes and position/velocity derivatives.
                        _ => {}
                    }
                }

                frame_pad_events.extend(pad_registry.flush_ready_events());

                // Emit frame dict
                let f = PyDict::new(py);
                f.set_item("timestamp", nf.time as f64)?;
                let ball = PyDict::new(py);
                let bpos = PyDict::new(py);
                bpos.set_item("x", ball_pos.0)?;
                bpos.set_item("y", ball_pos.1)?;
                bpos.set_item("z", ball_pos.2)?;
                let bvel = PyDict::new(py);
                bvel.set_item("x", ball_vel.0)?;
                bvel.set_item("y", ball_vel.1)?;
                bvel.set_item("z", ball_vel.2)?;
                ball.set_item("position", bpos)?;
                ball.set_item("velocity", bvel)?;
                let ang = PyDict::new(py);
                ang.set_item("x", ball_angvel.0)?;
                ang.set_item("y", ball_angvel.1)?;
                ang.set_item("z", ball_angvel.2)?;
                ball.set_item("angular_velocity", ang)?;
                f.set_item("ball", ball)?;

                // Players: union of actors that have position or boost info
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
                // Filter using classification when available; otherwise keep for fallback
                actors = actors
                    .into_iter()
                    .filter(|aid| actor_kind.get(aid).map(|kind| kind.is_car).unwrap_or(false))
                    .collect();

                let mut players_map: BTreeMap<usize, PyObject> = BTreeMap::new();
                for aid in actors {
                    let (x, y, z) = car_pos.get(&aid).cloned().unwrap_or((0.0, 0.0, 17.0));
                    // Determine team: prefer decoded team_paint else infer by y position sign
                    let mut team = *car_team.get(&aid).unwrap_or(&-1);
                    if team < 0 {
                        team = if y > 0.0 { 1 } else { 0 };
                    }
                    // Assign player index if not assigned and team known
                    if !actor_to_player_index.contains_key(&aid) && team >= 0 {
                        if let Some(v) = next_by_team.get_mut(&team) {
                            if let Some(idx) = v.first().cloned() {
                                v.remove(0);
                                actor_to_player_index.insert(aid, idx);
                            }
                        }
                    }
                    if let Some(idx) = actor_to_player_index.get(&aid).cloned() {
                        let p = PyDict::new(py);
                        p.set_item("player_id", format!("player_{}", idx))?;
                        p.set_item("team", team)?;
                        let ppos = PyDict::new(py);
                        ppos.set_item("x", x)?;
                        ppos.set_item("y", y)?;
                        ppos.set_item("z", z)?;
                        let v = car_vel.get(&aid).cloned().unwrap_or((0.0, 0.0, 0.0));
                        let pvel = PyDict::new(py);
                        pvel.set_item("x", v.0)?;
                        pvel.set_item("y", v.1)?;
                        pvel.set_item("z", v.2)?;

                        // Use true quaternion rotation if available, else fallback to velocity approximation
                        let prot = PyDict::new(py);
                        if let Some(q) = car_rot.get(&aid) {
                            // Convert quaternion to euler angles (roll, pitch, yaw)
                            let (roll, pitch, yaw) = quat_to_euler(*q);
                            prot.set_item("pitch", pitch)?;
                            prot.set_item("yaw", yaw)?;
                            prot.set_item("roll", roll)?;
                            // Also include raw quaternion for precision work
                            let quat = PyDict::new(py);
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
                        p.set_item("rotation", prot)?;
                        let boost = *car_boost.get(&aid).unwrap_or(&33);
                        p.set_item("boost_amount", boost)?;
                        // Calculate speed for supersonic check
                        let speed = (v.0 * v.0 + v.1 * v.1 + v.2 * v.2).sqrt();
                        p.set_item("is_supersonic", speed > 2300.0)?;
                        p.set_item("is_on_ground", z <= 18.0)?;
                        p.set_item("is_demolished", *car_demo.get(&aid).unwrap_or(&false))?;

                        players_map.insert(idx, p.into_py(py));
                    }
                }
                let players = PyList::empty(py);
                for (_idx, pobj) in players_map.iter() {
                    players.append(pobj.as_ref(py))?;
                }
                f.set_item("players", players)?;

                let pad_list = PyList::empty(py);
                for event in frame_pad_events {
                    let pad_dict = PyDict::new(py);
                    pad_dict.set_item("pad_id", event.pad_id as i64)?;
                    pad_dict.set_item("is_big", event.is_big)?;
                    pad_dict.set_item("status", event.status.as_str())?;
                    pad_dict.set_item("object_name", event.object_name.clone())?;
                    pad_dict.set_item("raw_state", event.raw_state)?;
                    pad_dict.set_item("timestamp", event.timestamp as f64)?;

                    let pos_dict = PyDict::new(py);
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
                    if let Some(distance) = event.snap_distance {
                        pad_dict.set_item("snap_distance", distance as f64)?;
                    }

                    pad_list.append(pad_dict)?;
                }
                f.set_item("boost_pad_events", pad_list)?;

                frames_out.append(f)?;
            }
        }

        Ok(frames_out.into())
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

        let out = PyList::empty(py);
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
                1 | 2 | 3 => "COLLECTED",
                _ => "UNKNOWN",
            }
        }

        if let Some(net) = replay.network_frames {
            for (frame_idx, nf) in net.frames.iter().enumerate() {
                if frame_idx >= max_frames {
                    break;
                }

                let frame_dict = PyDict::new(py);
                frame_dict.set_item("frame_index", frame_idx as i64)?;
                frame_dict.set_item("timestamp", nf.time as f64)?;

                let new_actors_py = PyList::empty(py);
                let updated_py = PyList::empty(py);
                let boost_events_py = PyList::empty(py);

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

                    let actor_dict = PyDict::new(py);
                    actor_dict.set_item("actor_id", actor_id as i64)?;
                    actor_dict.set_item("object_id", object_id as i64)?;
                    actor_dict.set_item("object_name", object_name.clone())?;

                    let trajectory_dict = PyDict::new(py);
                    if let Some(loc) = na.initial_trajectory.location {
                        let loc_world = PyDict::new(py);
                        loc_world.set_item("x", (loc.x as f64) / 100.0)?;
                        loc_world.set_item("y", (loc.y as f64) / 100.0)?;
                        loc_world.set_item("z", (loc.z as f64) / 100.0)?;
                        let loc_raw = PyDict::new(py);
                        loc_raw.set_item("x", loc.x)?;
                        loc_raw.set_item("y", loc.y)?;
                        loc_raw.set_item("z", loc.z)?;
                        trajectory_dict.set_item("location", loc_world)?;
                        trajectory_dict.set_item("location_raw", loc_raw)?;
                    }
                    if let Some(rot) = na.initial_trajectory.rotation {
                        let rot_dict = PyDict::new(py);
                        if let Some(yaw) = rot.yaw {
                            rot_dict.set_item("yaw", yaw)?;
                        }
                        if let Some(pitch) = rot.pitch {
                            rot_dict.set_item("pitch", pitch)?;
                        }
                        if let Some(roll) = rot.roll {
                            rot_dict.set_item("roll", roll)?;
                        }
                        if rot_dict.len() > 0 {
                            trajectory_dict.set_item("rotation", rot_dict)?;
                        }
                    }
                    if trajectory_dict.len() > 0 {
                        actor_dict.set_item("initial_trajectory", trajectory_dict)?;
                    }

                    new_actors_py.append(actor_dict)?;

                    if is_boost_actor {
                        let event = PyDict::new(py);
                        event.set_item("event", "trajectory")?;
                        event.set_item("actor_id", actor_id as i64)?;
                        event.set_item("object_name", object_name)?;
                        event.set_item("timestamp", nf.time as f64)?;
                        if let Some(loc) = na.initial_trajectory.location {
                            let loc_dict = PyDict::new(py);
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
                    let update_dict = PyDict::new(py);
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
                            let detail = PyDict::new(py);
                            detail.set_item("sleeping", rb.sleeping)?;
                            let loc_dict = PyDict::new(py);
                            loc_dict.set_item("x", rb.location.x)?;
                            loc_dict.set_item("y", rb.location.y)?;
                            loc_dict.set_item("z", rb.location.z)?;
                            detail.set_item("location", loc_dict)?;
                            if let Some(lv) = rb.linear_velocity {
                                let vel_dict = PyDict::new(py);
                                vel_dict.set_item("x", lv.x)?;
                                vel_dict.set_item("y", lv.y)?;
                                vel_dict.set_item("z", lv.z)?;
                                detail.set_item("linear_velocity", vel_dict)?;
                            }
                            if let Some(av) = rb.angular_velocity {
                                let ang_dict = PyDict::new(py);
                                ang_dict.set_item("x", av.x)?;
                                ang_dict.set_item("y", av.y)?;
                                ang_dict.set_item("z", av.z)?;
                                detail.set_item("angular_velocity", ang_dict)?;
                            }
                            update_dict.set_item("detail", detail)?;
                            if boost_actor_ids.contains(&actor_id) {
                                let event = PyDict::new(py);
                                event.set_item("event", "rigid_body")?;
                                event.set_item("actor_id", actor_id as i64)?;
                                if let Some(obj) = actor_object_name.get(&actor_id) {
                                    event.set_item("object_name", obj)?;
                                }
                                event.set_item("timestamp", nf.time as f64)?;
                                let loc_event = PyDict::new(py);
                                loc_event.set_item("x", rb.location.x)?;
                                loc_event.set_item("y", rb.location.y)?;
                                loc_event.set_item("z", rb.location.z)?;
                                event.set_item("location", loc_event)?;
                                event.set_item("sleeping", rb.sleeping)?;
                                if let Some(lv) = rb.linear_velocity {
                                    let vel_dict = PyDict::new(py);
                                    vel_dict.set_item("x", lv.x)?;
                                    vel_dict.set_item("y", lv.y)?;
                                    vel_dict.set_item("z", lv.z)?;
                                    event.set_item("linear_velocity", vel_dict)?;
                                }
                                if let Some(av) = rb.angular_velocity {
                                    let ang_dict = PyDict::new(py);
                                    ang_dict.set_item("x", av.x)?;
                                    ang_dict.set_item("y", av.y)?;
                                    ang_dict.set_item("z", av.z)?;
                                    event.set_item("angular_velocity", ang_dict)?;
                                }
                                boost_events_py.append(event)?;
                            }
                        }
                        Attribute::Pickup(pickup) => {
                            let detail = PyDict::new(py);
                            detail.set_item("picked_up", pickup.picked_up)?;
                            if let Some(instigator) = pickup.instigator {
                                let raw_actor: i32 = instigator.into();
                                detail.set_item("instigator_actor_id", raw_actor)?;
                                let (resolved, chain) = resolve_actor(&component_owner, raw_actor);
                                if resolved != raw_actor {
                                    detail.set_item("resolved_actor_id", resolved)?;
                                }
                                if !chain.is_empty() {
                                    let chain_py = PyList::empty(py);
                                    for item in chain {
                                        chain_py.append(item as i64)?;
                                    }
                                    detail.set_item("owner_chain", chain_py)?;
                                }
                            }
                            update_dict.set_item("detail", detail)?;
                            if boost_actor_ids.contains(&actor_id) {
                                let event = PyDict::new(py);
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
                                        let chain_py = PyList::empty(py);
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
                            let detail = PyDict::new(py);
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
                                    let chain_py = PyList::empty(py);
                                    for item in chain {
                                        chain_py.append(item as i64)?;
                                    }
                                    detail.set_item("owner_chain", chain_py)?;
                                }
                            }
                            update_dict.set_item("detail", detail)?;
                            if boost_actor_ids.contains(&actor_id) {
                                let event = PyDict::new(py);
                                event.set_item("event", "pickup_new")?;
                                event.set_item("actor_id", actor_id as i64)?;
                                if let Some(obj) = actor_object_name.get(&actor_id) {
                                    event.set_item("object_name", obj)?;
                                }
                                event.set_item("timestamp", nf.time as f64)?;
                                event.set_item("raw_state", pickup_new.picked_up)?;
                                event.set_item("state", pickup_state_label(pickup_new.picked_up))?;
                                if let Some(instigator) = pickup_new.instigator {
                                    let raw_actor: i32 = instigator.into();
                                    event.set_item("instigator_actor_id", raw_actor)?;
                                    let (resolved, chain) =
                                        resolve_actor(&component_owner, raw_actor);
                                    if resolved != raw_actor {
                                        event.set_item("resolved_actor_id", resolved)?;
                                    }
                                    if !chain.is_empty() {
                                        let chain_py = PyList::empty(py);
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
fn rlreplay_rust(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(parse_header, m)?)?;
    m.add_function(wrap_pyfunction!(iter_frames, m)?)?;
    m.add_function(wrap_pyfunction!(header_property_keys, m)?)?;
    m.add_function(wrap_pyfunction!(header_property, m)?)?;
    m.add_function(wrap_pyfunction!(net_frame_count, m)?)?;
    m.add_function(wrap_pyfunction!(debug_first_frames, m)?)?;
    // Expose a simple health flag
    m.add("RUST_CORE", true)?;

    // Module docstring
    m.add(
        "__doc__",
        "Rust-backed RL replay parser (boxcars): header + network frames",
    )?;

    // Ensure module is treated as Python extension module
    pyo3::prepare_freethreaded_python();
    Ok(())
}
