"""Boundary and isolation coverage for scheduled account deletion."""

from datetime import datetime, timedelta, timezone

from rlcoach.db.models import User
from rlcoach.db.session import create_session, init_db, reset_engine
from rlcoach.worker import tasks


def test_scheduled_deletion_only_processes_requests_at_least_30_days_old(
    monkeypatch, tmp_path
):
    init_db(tmp_path / "deletion-boundary.db")
    session = create_session()
    old_id = "00000000-0000-0000-0000-000000000001"
    recent_id = "00000000-0000-0000-0000-000000000002"
    session.add_all(
        [
            User(
                id=old_id,
                email="old@example.com",
                deletion_requested_at=datetime.now(timezone.utc) - timedelta(days=31),
            ),
            User(
                id=recent_id,
                email="recent@example.com",
                deletion_requested_at=datetime.now(timezone.utc) - timedelta(days=29),
            ),
        ]
    )
    session.commit()
    monkeypatch.setattr("rlcoach.db.session.create_session", lambda: session)

    result = tasks.process_scheduled_deletions.run()

    verify = create_session()
    try:
        assert result["deleted_count"] == 1
        assert verify.get(User, old_id).email is None
        recent = verify.get(User, recent_id)
        assert recent.email == "recent@example.com"
        assert recent.deletion_requested_at is not None
    finally:
        verify.close()
        reset_engine()
