use pyo3::exceptions::{PyIOError, PyValueError};
use pyo3::prelude::*;
use std::fs::File;
use std::io::Read;

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
    let gil = Python::acquire_gil();
    let py = gil.python();

    let data = read_file_bytes(path)?;
    if data.len() < 100 {
        return Err(PyValueError::new_err("File too short to be a valid replay"));
    }
    let looks_like = looks_like_replay_header(&data);

    // Build a minimal header dict; values are placeholders but deterministic
    let header = PyDict::new(py);
    header.set_item("playlist_id", if looks_like { "unknown" } else { "invalid" })?;
    header.set_item("map_name", if looks_like { "unknown" } else { "invalid" })?;
    header.set_item("team_size", 1i64)?;
    header.set_item("team0_score", 0i64)?;
    header.set_item("team1_score", 0i64)?;
    header.set_item("match_length", 0.0f64)?;

    // Players: two placeholders with team 0/1
    let p0 = PyDict::new(py);
    p0.set_item("name", "Unknown Player 1")?;
    p0.set_item("team", 0i64)?;
    let p1 = PyDict::new(py);
    p1.set_item("name", "Unknown Player 2")?;
    p1.set_item("team", 1i64)?;
    let players = PyList::empty(py);
    players.append(p0)?;
    players.append(p1)?;
    header.set_item("players", players)?;

    // Quality warnings include that this came from the Rust core (stub)
    let warnings = PyList::empty(py);
    warnings.append("rust_core_stub_header")?;
    if !looks_like {
        warnings.append("rust_core_suspect_format")?;
    }
    header.set_item("quality_warnings", warnings)?;

    Ok(header.to_object(py))
}

#[pyfunction]
fn iter_frames(_path: &str) -> PyResult<Py<PyAny>> {
    // Minimal iterator that yields zero frames; serves as stub
    Python::with_gil(|py| {
        let generator = pyo3::types::PyIterator::from_object(py, PyList::empty(py))?;
        Ok(generator.into())
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

