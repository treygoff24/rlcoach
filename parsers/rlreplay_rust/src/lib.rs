use pyo3::exceptions::{PyIOError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use std::fs::File;
use std::io::Read;
use std::collections::HashMap;

// Boxcars parsing
use boxcars::{ParserBuilder, HeaderProp, Replay};

fn read_file_bytes(path: &str) -> PyResult<Vec<u8>> {
    let mut file = File::open(path).map_err(|e| PyIOError::new_err(format!(
        "Failed to open replay file '{}': {}",
        path, e
    )))?;
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
    let head = if bytes.len() > 2048 { &bytes[..2048] } else { bytes };
    needles.iter().any(|n| head.windows(n.len()).any(|w| w == *n))
}

#[pyfunction]
fn parse_header(path: &str) -> PyResult<PyObject> {
    Python::with_gil(|py| {
        let data = read_file_bytes(path)?;
        if data.len() < 100 { return Err(PyValueError::new_err("File too short to be a valid replay")); }

        // Parsed fields
        let mut playlist_id: Option<String> = None;
        let mut map_name: Option<String> = None;
        let mut team0_score: i64 = 0;
        let mut team1_score: i64 = 0;
        let mut match_length: f64 = 0.0;
        let mut players_vec: Vec<(String, i64)> = Vec::new();
        let mut team_size: i64 = 0;
        let mut warnings_vec: Vec<String> = Vec::new();

        // Helper: get prop by key
        fn find_prop<'a>(props: &'a Vec<(String, HeaderProp)>, key: &str) -> Option<&'a HeaderProp> {
            props.iter().find(|(k, _)| k == key).map(|(_, v)| v)
        }

        match ParserBuilder::new(&data).never_parse_network_data().parse() {
            Ok(Replay { properties, .. }) => {
                if let Some(p) = find_prop(&properties, "MapName") { if let Some(s) = p.as_string() { map_name = Some(s.to_string()); } }
                if let Some(p) = find_prop(&properties, "PlaylistID") { if let Some(s) = p.as_string() { playlist_id = Some(s.to_string()); } }
                if let Some(p) = find_prop(&properties, "NumFrames") { if let Some(fr) = p.as_i32() { match_length = (fr as f64) / 30.0; } }
                if let Some(p) = find_prop(&properties, "Team0Score") { if let Some(s0) = p.as_i32() { team0_score = s0 as i64; } }
                if let Some(p) = find_prop(&properties, "Team1Score") { if let Some(s1) = p.as_i32() { team1_score = s1 as i64; } }

                if let Some(p) = find_prop(&properties, "PlayerStats") {
                    if let Some(arr) = p.as_array() {
                        for entry in arr {
                            // Each entry is Vec<(String, HeaderProp)>
                            let mut name: Option<String> = None;
                            let mut team: i64 = 0;
                            for (k, v) in entry {
                                match (k.as_str(), v) {
                                    ("Name", hp) | ("PlayerName", hp) => {
                                        if let Some(s) = hp.as_string() { name = Some(s.to_string()); }
                                    }
                                    ("Team", hp) | ("PlayerTeam", hp) => {
                                        if let Some(t) = hp.as_i32() { team = t as i64; }
                                    }
                                    _ => {}
                                }
                            }
                            if let Some(n) = name { players_vec.push((n, team)); }
                        }
                    }
                }

                if !players_vec.is_empty() {
                    let mut team_counts: HashMap<i64, i64> = HashMap::new();
                    for (_, t) in &players_vec { *team_counts.entry(*t).or_insert(0) += 1; }
                    team_size = team_counts.values().cloned().max().unwrap_or(1);
                } else {
                    warnings_vec.push("boxcars_no_playerstats".to_string());
                }
            }
            Err(e) => {
                warnings_vec.push(format!("boxcars_parse_error: {}", e));
                let looks_like = looks_like_replay_header(&data);
                if !looks_like { warnings_vec.push("rust_core_suspect_format".to_string()); }
                players_vec.push(("Unknown Player 1".to_string(), 0));
                players_vec.push(("Unknown Player 2".to_string(), 1));
                team_size = 1;
            }
        }

        // Build Python dict
        let header = PyDict::new(py);
        header.set_item("playlist_id", playlist_id.unwrap_or_else(|| "unknown".to_string()))?;
        header.set_item("map_name", map_name.unwrap_or_else(|| "unknown".to_string()))?;
        header.set_item("team_size", team_size)?;
        header.set_item("team0_score", team0_score)?;
        header.set_item("team1_score", team1_score)?;
        header.set_item("match_length", match_length)?;

        let players = PyList::empty(py);
        for (name, team) in players_vec { let p = PyDict::new(py); p.set_item("name", name)?; p.set_item("team", team)?; players.append(p)?; }
        header.set_item("players", players)?;
        let warnings = PyList::empty(py);
        warnings.append("parsed_with_rust_core")?;
        for w in warnings_vec { warnings.append(w)?; }
        header.set_item("quality_warnings", warnings)?;

        Ok(header.to_object(py))
    })
}

#[pyfunction]
fn iter_frames(_path: &str) -> PyResult<Py<PyAny>> {
    // Minimal iterator that yields zero frames; serves as stub
    Python::with_gil(|py| {
        let empty = PyList::empty(py);
        Ok(empty.into())
    })
}

#[pymodule]
fn rlreplay_rust(py: Python, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(parse_header, m)?)?;
    m.add_function(wrap_pyfunction!(iter_frames, m)?)?;
    // Expose a simple health flag
    m.add("RUST_CORE", true)?;

    // Module docstring
    m.add("__doc__", "Rust stub for RL replay parsing (header + frame iterator stub)")?;

    // Ensure module is treated as Python extension module
    pyo3::prepare_freethreaded_python();
    Ok(())
}
