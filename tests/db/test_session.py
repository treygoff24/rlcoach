# tests/db/test_session.py
import pytest
from sqlalchemy import inspect

from rlcoach.db.session import create_session, init_db, reset_engine


@pytest.fixture(autouse=True)
def reset_db():
    """Reset global engine between tests."""
    yield
    reset_engine()


def test_init_db_creates_tables(tmp_path):
    db_path = tmp_path / "test.db"
    engine = init_db(db_path)

    assert db_path.exists()

    inspector = inspect(engine)
    tables = inspector.get_table_names()
    assert "replays" in tables
    assert "benchmarks" in tables


def test_create_session_works_after_init(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)

    session = create_session()
    assert session is not None
    session.close()


def test_create_session_fails_without_init():
    with pytest.raises(RuntimeError, match="not initialized"):
        create_session()
