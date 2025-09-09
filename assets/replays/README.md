# Local Replay Fixtures

This repository does not include real Rocket League replay files. To work with local fixtures:

- Do not commit replay binaries to git. If you must keep large sample files locally, use Git LFS and add them to `.gitignore` for normal commits.
- Place any personal or sample replays under `assets/replays/local/` on your machine. This path is intentionally ignored and not required for tests.
- Tests use synthetic frames and header-only fallbacks; no network or replay downloads are needed.

Recommended workflow:
- Keep a small set of local replays for manual experiments only.
- Use the CLI `rlcoach analyze` on these local files and inspect JSON outputs separately.

Notes:
- Golden tests in `tests/test_goldens.py` compare deterministic JSON outputs for synthetic inputs; they do not require real replays.
- Keep replay files under 50MB when experimenting to lower I/O overhead.

