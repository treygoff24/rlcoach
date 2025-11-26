use pyo3::prelude::*;
use pyo3::types::PyDict;
use std::env;
use std::path::PathBuf;
use rlreplay_rust::debug_first_frames;

fn print_usage(program: &str) {
    eprintln!(
        "Usage: {program} [--max-frames N] [--pretty] <replay.replay> [more.replay...]\n\
         Prints JSON debug telemetry for the first N frames (default 120)."
    );
}

fn run() -> Result<(), String> {
    pyo3::prepare_freethreaded_python();

    let mut max_frames: usize = 120;
    let mut pretty = false;
    let mut paths: Vec<PathBuf> = Vec::new();

    let mut args = env::args().skip(1);
    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--help" | "-h" => {
                print_usage(&env::args().next().unwrap_or_else(|| String::from("debug_first_frames")));
                return Ok(());
            }
            "--max-frames" => {
                let value = args
                    .next()
                    .ok_or_else(|| "expected value after --max-frames".to_string())?;
                max_frames = value
                    .parse::<usize>()
                    .map_err(|_| format!("invalid --max-frames value: {value}"))?;
            }
            "--pretty" => {
                pretty = true;
            }
            opt if opt.starts_with("--") => {
                return Err(format!("unknown option: {opt}"));
            }
            path => {
                paths.push(PathBuf::from(path));
            }
        }
    }

    if paths.is_empty() {
        print_usage(&env::args().next().unwrap_or_else(|| String::from("debug_first_frames")));
        return Err("no replay files provided".into());
    }

    for (idx, path) in paths.iter().enumerate() {
        let replay_path = path
            .to_str()
            .ok_or_else(|| format!("non-UTF8 path: {:?}", path))?;

        let frames = debug_first_frames(replay_path, max_frames)
            .map_err(|err| err.to_string())?;

        Python::with_gil(|py| -> PyResult<()> {
            let frames_obj = frames.as_ref(py);
            let json_mod = py.import("json")?;
            let dumps = json_mod.getattr("dumps")?;
            let json_str: String = if pretty {
                let kwargs = PyDict::new(py);
                kwargs.set_item("indent", 2)?;
                kwargs.set_item("sort_keys", true)?;
                dumps.call((frames_obj,), Some(kwargs))?.extract()?
            } else {
                dumps.call1((frames_obj,))?.extract()?
            };

            if idx > 0 {
                println!();
            }
            println!("{json_str}");
            Ok(())
        })
        .map_err(|err| err.to_string())?;
    }

    Ok(())
}

fn main() {
    if let Err(err) = run() {
        eprintln!("error: {err}");
        std::process::exit(1);
    }
}
