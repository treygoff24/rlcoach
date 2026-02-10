"""Unit tests for worker task helpers and branches."""

from __future__ import annotations

import os
import subprocess
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from rlcoach.db.models import (
    CoachMessage,
    CoachNote,
    CoachSession,
    UploadedReplay,
    User,
)
from rlcoach.db.session import create_session, init_db, reset_engine
from rlcoach.worker import tasks


@pytest.fixture
def db_session(tmp_path):
    init_db(tmp_path / "worker.db")
    session = create_session()
    yield session
    session.close()
    reset_engine()


def _uuid(n: int) -> str:
    return f"00000000-0000-0000-0000-{n:012d}"


def test_sanitize_error_message_redacts_and_truncates():
    raw = "/Users/alice/dev password=abc secret=xyz api_key=123 /tmp/foo"
    safe = tasks._sanitize_error_message(raw)
    assert "/Users/alice" not in safe
    assert "password=abc" not in safe
    assert "secret=xyz" not in safe
    assert "api_key=123" not in safe
    assert len(safe) <= tasks.ERROR_MESSAGE_MAX_LENGTH


def test_uuid_and_path_helpers(tmp_path):
    assert tasks._is_valid_uuid(_uuid(1)) is True
    assert tasks._is_valid_uuid("bad") is False

    root = tmp_path / "uploads"
    root.mkdir()
    inside = root / "a.replay"
    inside.write_text("x", encoding="utf-8")
    outside = tmp_path / "outside.replay"
    outside.write_text("x", encoding="utf-8")

    assert tasks._is_path_within_directory(inside, root) is True
    assert tasks._is_path_within_directory(outside, root) is False


def test_run_parser_subprocess_branches(monkeypatch, tmp_path):
    replay_path = tmp_path / "r.replay"
    replay_path.write_text("x", encoding="utf-8")
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    monkeypatch.setattr(tasks, "set_memory_limit", lambda: None)

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_a, **_k: SimpleNamespace(returncode=0, stderr=""),
    )
    ok = tasks._run_parser_subprocess(replay_path, output_dir, _uuid(9))
    assert ok["status"] == "success"

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_a, **_k: SimpleNamespace(returncode=1, stderr="failure"),
    )
    failed = tasks._run_parser_subprocess(replay_path, output_dir, _uuid(10))
    assert failed["status"] == "failed"
    assert failed["error"] == "failure"

    def raise_timeout(*_a, **_k):
        raise subprocess.TimeoutExpired(cmd="x", timeout=30)

    monkeypatch.setattr(subprocess, "run", raise_timeout)
    timeout = tasks._run_parser_subprocess(replay_path, output_dir, _uuid(11))
    assert timeout["error"].startswith("Parser timeout")

    monkeypatch.setattr(
        subprocess, "run", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    exc = tasks._run_parser_subprocess(replay_path, output_dir, _uuid(12))
    assert exc["status"] == "failed"
    assert "boom" in exc["error"]


def test_process_replay_invalid_uuid():
    result = tasks.process_replay.run("not-a-uuid")
    assert result["status"] == "failed"
    assert "Invalid upload ID format" in result["error"]


def test_process_replay_not_found(monkeypatch, db_session):
    monkeypatch.setattr(tasks, "get_db_session", lambda: db_session)
    result = tasks.process_replay.run(_uuid(100))
    assert result["status"] == "failed"
    assert result["error"] == "Upload not found"


def test_process_replay_invalid_user_and_path_and_missing_file(
    monkeypatch, db_session, tmp_path
):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setenv("UPLOAD_DIR", str(upload_dir))
    monkeypatch.setattr(tasks, "get_db_session", lambda: db_session)

    bad_user = User(id="bad-user", email="bad@example.com")
    db_session.add(bad_user)
    db_session.add(
        UploadedReplay(
            id=_uuid(101),
            user_id="bad-user",
            filename="bad.replay",
            file_hash="h1",
            file_size_bytes=1234,
            storage_path=str(upload_dir / "bad.replay"),
            status="pending",
        )
    )
    db_session.commit()
    result = tasks.process_replay.run(_uuid(101))
    assert result["status"] == "failed"
    assert "Invalid user ID format" in result["error"]

    good_user_id = _uuid(102)
    db_session.add(User(id=good_user_id, email="good@example.com"))
    db_session.add(
        UploadedReplay(
            id=_uuid(103),
            user_id=good_user_id,
            filename="x.replay",
            file_hash="h2",
            file_size_bytes=1234,
            storage_path=str(tmp_path / "outside.replay"),
            status="pending",
        )
    )
    db_session.commit()
    result = tasks.process_replay.run(_uuid(103))
    assert result["error"] == "Invalid storage path"

    db_session.add(
        UploadedReplay(
            id=_uuid(104),
            user_id=good_user_id,
            filename="x2.replay",
            file_hash="h3",
            file_size_bytes=1234,
            storage_path=str(upload_dir / "missing.replay"),
            status="pending",
        )
    )
    db_session.commit()
    result = tasks.process_replay.run(_uuid(104))
    assert result["error"] == "File not found"


def test_process_replay_success_and_failure_paths(monkeypatch, db_session, tmp_path):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    replay_file = upload_dir / "ok.replay"
    replay_file.write_bytes(b"ok")
    monkeypatch.setattr(tasks, "STORAGE_PATH", tmp_path / "storage")

    user_id = _uuid(200)
    upload_id = _uuid(201)
    db_session.add(User(id=user_id, email="u@example.com"))
    db_session.add(
        UploadedReplay(
            id=upload_id,
            user_id=user_id,
            filename="ok.replay",
            file_hash="hash",
            file_size_bytes=2,
            storage_path=str(replay_file),
            status="pending",
        )
    )
    db_session.commit()

    monkeypatch.setenv("UPLOAD_DIR", str(upload_dir))
    monkeypatch.setattr(tasks, "get_db_session", lambda: db_session)
    monkeypatch.setattr(
        tasks,
        "_run_parser_subprocess",
        lambda *_a, **_k: {
            "status": "success",
            "output_path": str(tmp_path / "missing.json"),
        },
    )
    ok = tasks.process_replay.run(upload_id)
    assert ok["status"] == "success"

    upload_id2 = _uuid(202)
    db_session.add(
        UploadedReplay(
            id=upload_id2,
            user_id=user_id,
            filename="bad.replay",
            file_hash="hash2",
            file_size_bytes=2,
            storage_path=str(replay_file),
            status="pending",
        )
    )
    db_session.commit()

    monkeypatch.setattr(
        tasks,
        "_run_parser_subprocess",
        lambda *_a, **_k: {"status": "failed", "error": "secret=abc /Users/name"},
    )
    failed = tasks.process_replay.run(upload_id2)
    assert failed["status"] == "failed"
    upload = db_session.query(UploadedReplay).filter_by(id=upload_id2).first()
    assert upload is not None
    assert "secret=abc" not in (upload.error_message or "")


def test_cleanup_temp_files_and_disk_checks(monkeypatch, tmp_path):
    temp_dir = tmp_path / "temp"
    temp_dir.mkdir()
    old_file = temp_dir / "old.tmp"
    old_file.write_text("x", encoding="utf-8")
    new_file = temp_dir / "new.tmp"
    new_file.write_text("x", encoding="utf-8")

    old_time = datetime.now(timezone.utc).timestamp() - 48 * 3600
    os.utime(old_file, (old_time, old_time))
    monkeypatch.setattr(tasks, "TEMP_PATH", temp_dir)

    cleaned = tasks.cleanup_temp_files.run(max_age_hours=24)
    assert cleaned["status"] == "success"
    assert cleaned["deleted_count"] == 1
    assert new_file.exists() is True

    monkeypatch.setattr("shutil.disk_usage", lambda _p: (100, 50, 50))
    disk = tasks.check_disk_usage.run()
    assert disk["status"] == "success"
    assert disk["usage_percent"] == 50.0

    monkeypatch.setattr(
        "shutil.disk_usage", lambda _p: (_ for _ in ()).throw(RuntimeError("disk"))
    )
    failed = tasks.check_disk_usage.run()
    assert failed["status"] == "failed"


def test_queue_and_upload_backpressure(monkeypatch):
    monkeypatch.setattr(tasks, "get_queue_length", lambda: 5)
    monkeypatch.setattr("shutil.disk_usage", lambda _p: (100, 10, 90))
    ok, reason = tasks.can_accept_upload()
    assert ok is True
    assert reason is None

    monkeypatch.setattr(tasks, "get_queue_length", lambda: 1001)
    ok, reason = tasks.can_accept_upload()
    assert ok is False
    assert "queue full" in (reason or "").lower()

    monkeypatch.setattr("shutil.disk_usage", lambda _p: (100, 95, 5))
    monkeypatch.setattr(tasks, "get_queue_length", lambda: 0)
    ok, reason = tasks.can_accept_upload()
    assert ok is False
    assert "disk space low" in (reason or "").lower()


def test_migrate_to_cold_storage_branches(monkeypatch, tmp_path):
    monkeypatch.delenv("BACKBLAZE_KEY_ID", raising=False)
    monkeypatch.delenv("BACKBLAZE_APPLICATION_KEY", raising=False)
    monkeypatch.delenv("BACKBLAZE_BUCKET_NAME", raising=False)
    result = tasks.migrate_to_cold_storage.run(_uuid(500), str(tmp_path / "x.replay"))
    assert result["status"] == "failed"

    monkeypatch.setenv("BACKBLAZE_KEY_ID", "k")
    monkeypatch.setenv("BACKBLAZE_APPLICATION_KEY", "a")
    monkeypatch.setenv("BACKBLAZE_BUCKET_NAME", "b")
    # Force ImportError branch even if b2sdk is installed.
    monkeypatch.setitem(__import__("sys").modules, "b2sdk", None)
    monkeypatch.setitem(__import__("sys").modules, "b2sdk.v2", None)
    result = tasks.migrate_to_cold_storage.run(_uuid(501), str(tmp_path / "x.replay"))
    assert result["status"] == "failed"


def test_process_scheduled_deletions(monkeypatch, db_session):
    user = User(
        id=_uuid(900),
        email="delete@example.com",
        display_name="Delete Me",
        deletion_requested_at=datetime.now(timezone.utc) - timedelta(days=31),
    )
    session_row = CoachSession(id=_uuid(901), user_id=user.id)
    note = CoachNote(id=_uuid(902), user_id=user.id, content="n", source="coach")
    msg = CoachMessage(
        id=_uuid(903), session_id=session_row.id, role="user", content="m"
    )
    db_session.add_all([user, session_row, note, msg])
    db_session.commit()

    monkeypatch.setattr("rlcoach.db.session.create_session", lambda: db_session)
    result = tasks.process_scheduled_deletions.run()
    assert result["status"] == "success"
    assert result["deleted_count"] == 1

    verify = create_session()
    try:
        refreshed = verify.query(User).filter(User.id == user.id).one()
        assert refreshed.email is None
        assert (refreshed.display_name or "").startswith("Deleted User")
        assert verify.query(CoachNote).filter(CoachNote.user_id == user.id).count() == 0
    finally:
        verify.close()
