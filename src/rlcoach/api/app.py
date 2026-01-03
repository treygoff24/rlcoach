# src/rlcoach/api/app.py
"""FastAPI application setup."""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .. import __version__
from ..config import ConfigError, RLCoachConfig, get_default_config_path, load_config
from ..db.session import create_session, init_db

# Global config - set on startup
_config: RLCoachConfig | None = None


def get_config() -> RLCoachConfig:
    """Get the current configuration."""
    if _config is None:
        raise RuntimeError("Configuration not initialized")
    return _config


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler for startup/shutdown."""
    global _config

    # Load configuration
    try:
        config_path = get_default_config_path()
        _config = load_config(config_path)
        _config.validate()

        # Initialize database
        init_db(_config.db_path)
    except (ConfigError, FileNotFoundError) as e:
        # Log but allow app to start in degraded mode
        import logging

        logging.warning(f"Config not loaded: {e}")

    yield

    # Cleanup on shutdown
    _config = None


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="RLCoach API",
        description="REST API for Rocket League coaching data",
        version=__version__,
        lifespan=lifespan,
    )

    # Configure CORS for local development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",  # Vite dev server
            "http://localhost:3000",  # Alternative port
            "http://127.0.0.1:5173",
            "http://127.0.0.1:3000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routes
    _register_routes(app)

    return app


def _register_routes(app: FastAPI) -> None:
    """Register all API routes."""
    from .routers import analysis_router, dashboard_router, games_router, players_router

    # Include routers
    app.include_router(games_router)
    app.include_router(dashboard_router)
    app.include_router(analysis_router)
    app.include_router(players_router)

    @app.get("/")
    async def root():
        """API information."""
        return {
            "name": "RLCoach API",
            "version": __version__,
            "docs": "/docs",
        }

    @app.get("/health")
    async def health():
        """Health check endpoint for container orchestration."""
        db_status = "not_initialized"
        redis_status = "not_configured"

        # Check database
        try:
            session = create_session()
            session.close()
            db_status = "connected"
        except Exception:
            db_status = "disconnected"

        # Check Redis if configured
        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            try:
                import redis

                r = redis.from_url(redis_url)
                r.ping()
                redis_status = "connected"
            except Exception:
                redis_status = "disconnected"

        overall_status = "healthy"
        if db_status != "connected":
            overall_status = "degraded"

        return {
            "status": overall_status,
            "service": "rlcoach-backend",
            "version": __version__,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "checks": {
                "database": db_status,
                "redis": redis_status,
            },
        }

    @app.get("/api/v1/health")
    async def api_health():
        """API health endpoint (mirrors /health for frontend proxy)."""
        return await health()


app = create_app()
