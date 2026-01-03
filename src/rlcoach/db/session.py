# src/rlcoach/db/session.py
"""Database session management.

Supports both SQLite (local CLI, tests) and PostgreSQL (SaaS).
DATABASE_URL env var determines which backend to use.
"""

from __future__ import annotations

import os
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


def init_db(db_path: Path | None = None) -> Engine:
    """Initialize the database, creating tables if needed.

    Args:
        db_path: Path to SQLite database file (optional, ignored if DATABASE_URL set)

    Environment variables:
        DATABASE_URL: PostgreSQL connection string (takes precedence over db_path)

    Returns:
        SQLAlchemy engine
    """
    global _engine, _SessionFactory

    database_url = os.getenv("DATABASE_URL")

    if database_url:
        # PostgreSQL (SaaS mode)
        _engine = create_engine(
            database_url,
            echo=False,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,  # Verify connections before use
            pool_recycle=3600,  # Recycle connections after 1 hour
        )
    elif db_path:
        # SQLite (CLI mode)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(
            f"sqlite:///{db_path}",
            echo=False,
            connect_args={"check_same_thread": False},
        )
    else:
        # In-memory SQLite (tests)
        _engine = create_engine(
            "sqlite:///:memory:",
            echo=False,
            connect_args={"check_same_thread": False},
        )

    # Create tables (for dev/test; production uses Alembic migrations)
    if not database_url or os.getenv("AUTO_CREATE_TABLES"):
        Base.metadata.create_all(_engine)

    _SessionFactory = sessionmaker(bind=_engine, expire_on_commit=False)

    return _engine


def init_db_from_url(database_url: str) -> Engine:
    """Initialize database from explicit URL (for testing/scripts).

    Args:
        database_url: Full database connection URL

    Returns:
        SQLAlchemy engine
    """
    global _engine, _SessionFactory

    if database_url.startswith("postgresql"):
        _engine = create_engine(
            database_url,
            echo=False,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
        )
    else:
        # SQLite
        _engine = create_engine(
            database_url,
            echo=False,
            connect_args=(
                {"check_same_thread": False} if "sqlite" in database_url else {}
            ),
        )

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


def is_postgresql() -> bool:
    """Check if the current engine is PostgreSQL."""
    if _engine is None:
        return False
    return "postgresql" in str(_engine.url)


def get_database_info() -> dict:
    """Get info about the current database connection."""
    if _engine is None:
        return {"status": "not_initialized"}

    dialect = _engine.dialect.name
    return {
        "status": "connected",
        "dialect": dialect,
        "is_postgresql": dialect == "postgresql",
        "pool_size": getattr(_engine.pool, "size", lambda: None)(),
    }
