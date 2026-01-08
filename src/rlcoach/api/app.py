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

# Default CORS origins for development
DEFAULT_CORS_ORIGINS = [
    "http://localhost:5173",  # Vite dev server
    "http://localhost:3000",  # Alternative port
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
]


def get_config() -> RLCoachConfig:
    """Get the current configuration."""
    if _config is None:
        raise RuntimeError("Configuration not initialized")
    return _config


def _get_cors_origins() -> list[str]:
    """Get CORS allowed origins from environment or defaults."""
    cors_origins = os.getenv("CORS_ORIGINS")
    if cors_origins:
        # Comma-separated list of origins
        return [origin.strip() for origin in cors_origins.split(",") if origin.strip()]
    return DEFAULT_CORS_ORIGINS


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler for startup/shutdown."""
    global _config
    import logging

    logger = logging.getLogger(__name__)

    # Check for SaaS mode via DATABASE_URL
    database_url = os.getenv("DATABASE_URL")

    if database_url:
        # SaaS mode: use DATABASE_URL, don't require config file
        logger.info("SaaS mode: initializing database from DATABASE_URL")
        init_db()  # Will use DATABASE_URL automatically
    else:
        # CLI mode: try to load config file
        try:
            config_path = get_default_config_path()
            _config = load_config(config_path)
            _config.validate()
            init_db(_config.db_path)
            logger.info(f"CLI mode: loaded config from {config_path}")
        except (ConfigError, FileNotFoundError) as e:
            # No config and no DATABASE_URL - use in-memory for development
            logger.warning(f"Config not loaded and no DATABASE_URL: {e}")
            logger.warning("Using in-memory database (data will not persist)")
            init_db()  # Will use in-memory SQLite

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

    # Configure CORS - use environment variable or defaults
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_get_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routes
    _register_routes(app)

    return app


def _register_routes(app: FastAPI) -> None:
    """Register all API routes."""
    import logging

    logger = logging.getLogger(__name__)

    from .routers import (
        billing_router,
        coach_router,
        gdpr_router,
        replays_router,
        users_router,
        webhook_router,
    )

    # SaaS API routers (always included)
    app.include_router(users_router)
    app.include_router(replays_router)
    app.include_router(coach_router)
    app.include_router(billing_router)
    app.include_router(gdpr_router)  # GDPR removal requests (public, no auth)
    app.include_router(webhook_router)  # Stripe webhooks at /stripe/webhook

    # CLI-local routers - only include when NOT in SaaS mode
    # SECURITY: These routers have NO authentication and expose ALL data
    # They are only safe for local CLI usage, never in production
    is_saas_mode = os.getenv("SAAS_MODE", "false").lower() in ("true", "1", "yes")
    is_production = os.getenv("ENVIRONMENT", "development").lower() == "production"

    # SECURITY: Block CLI routers in production even if SAAS_MODE is misconfigured
    if is_production and not is_saas_mode:
        logger.critical(
            "SECURITY: Production environment detected without SAAS_MODE=true. "
            "CLI-local routers will NOT be loaded. Set SAAS_MODE=true for production."
        )
        # Force SaaS mode in production for safety
        is_saas_mode = True

    if not is_saas_mode:
        logger.info("Loading CLI-local routers (development mode only)")
        from .routers import (
            analysis_router,
            dashboard_router,
            games_router,
            players_router,
        )

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
