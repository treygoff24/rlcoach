# src/rlcoach/db/session.py
"""Database session management."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base

_engine: Engine | None = None
_SessionFactory: sessionmaker | None = None


def get_engine() -> Engine:
    """Get the database engine (must call init_db first)."""
    if _engine is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _engine


def init_db(db_path: Path) -> Engine:
    """Initialize the database, creating tables if needed.

    Args:
        db_path: Path to SQLite database file

    Returns:
        SQLAlchemy engine
    """
    global _engine, _SessionFactory

    db_path.parent.mkdir(parents=True, exist_ok=True)

    _engine = create_engine(
        f"sqlite:///{db_path}",
        echo=False,
        # SQLite-specific optimizations
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(_engine)

    _SessionFactory = sessionmaker(bind=_engine, expire_on_commit=False)

    return _engine


def reset_engine() -> None:
    """Reset the global engine (for testing)."""
    global _engine, _SessionFactory
    if _engine:
        _engine.dispose()
    _engine = None
    _SessionFactory = None


def get_session() -> Generator[Session, None, None]:
    """Get a database session (for use with FastAPI Depends)."""
    if _SessionFactory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")

    session = _SessionFactory()
    try:
        yield session
    finally:
        session.close()


def create_session() -> Session:
    """Create a database session directly (for scripts/CLI).

    Remember to close the session when done!
    """
    if _SessionFactory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _SessionFactory()
