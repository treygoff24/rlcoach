**Offline UI (CLI Viewer)**

- Purpose: Quickly inspect a generated replay report JSON on your local machine, no network usage.

**Run**
- `python -m rlcoach.ui view examples/replay_report.success.json`

**What It Shows**
- Playlist, map, team size, duration/frames.
- Teams with scores and player IDs.
- Players with display names and teams.
- A few key metrics per team (goals, shots, saves, avg speed, avg boost).

**Notes**
- The CLI reads a local JSON file and prints a deterministic summary.
- Desktop UI scaffolding (e.g., Tauri/Electron) can be added later; this CLI keeps footprint minimal.

