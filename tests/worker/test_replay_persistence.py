"""Worker-to-database coverage for successful SaaS replay persistence."""

from __future__ import annotations

import json

from rlcoach.db.models import Replay, UploadedReplay, User, UserReplay
from rlcoach.db.session import create_session, init_db, reset_engine
from rlcoach.worker import tasks


def test_worker_persists_report_and_links_it_to_uploader(monkeypatch, tmp_path):
    init_db(tmp_path / "worker-persistence.db")
    session = create_session()
    user_id = "00000000-0000-0000-0000-000000000001"
    upload_id = "00000000-0000-0000-0000-000000000002"
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    replay_file = upload_dir / "match.replay"
    replay_file.write_bytes(b"replay")
    report_file = tmp_path / "report.json"
    report_file.write_text(
        json.dumps(
            {
                "replay_id": "persisted-replay",
                "source_file": str(replay_file),
                "metadata": {
                    "started_at_utc": "2026-07-17T12:00:00Z",
                    "map": "DFH Stadium",
                    "playlist": "DOUBLES",
                    "team_size": 2,
                    "duration_seconds": 300,
                },
                "teams": {"blue": {"score": 1}, "orange": {"score": 0}},
                "players": [
                    {
                        "player_id": "steam:player-1",
                        "display_name": "Uploader",
                        "team": "BLUE",
                    }
                ],
                "analysis": {"per_player": {}},
            }
        ),
        encoding="utf-8",
    )
    session.add(User(id=user_id, email="uploader@example.com"))
    session.add(
        UploadedReplay(
            id=upload_id,
            user_id=user_id,
            filename=replay_file.name,
            file_hash="worker-persistence-hash",
            file_size_bytes=replay_file.stat().st_size,
            storage_path=str(replay_file),
        )
    )
    session.commit()

    monkeypatch.setenv("UPLOAD_DIR", str(upload_dir))
    monkeypatch.setattr(tasks, "STORAGE_PATH", tmp_path / "storage")
    monkeypatch.setattr(tasks, "get_db_session", lambda: session)
    monkeypatch.setattr(
        tasks,
        "_run_parser_subprocess",
        lambda *_args: {"status": "success", "output_path": str(report_file)},
    )

    result = tasks.process_replay.run(upload_id)

    verify = create_session()
    try:
        assert result["status"] == "success"
        assert verify.get(Replay, "persisted-replay") is not None
        link = verify.query(UserReplay).one()
        assert (link.user_id, link.replay_id) == (user_id, "persisted-replay")
        upload = verify.get(UploadedReplay, upload_id)
        assert (upload.status, upload.replay_id) == (
            "completed",
            "persisted-replay",
        )
    finally:
        verify.close()
        session.close()
        reset_engine()
