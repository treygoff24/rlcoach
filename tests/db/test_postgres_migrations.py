"""Optional destructive PostgreSQL migration smoke test."""

from __future__ import annotations

import os
import subprocess
import sys
import uuid

import psycopg2
import pytest
from psycopg2 import sql


def test_postgres_migrations_upgrade_clean_database_to_head():
    admin_url = os.getenv("TEST_POSTGRES_ADMIN_URL")
    if not admin_url:
        pytest.skip("set TEST_POSTGRES_ADMIN_URL to run PostgreSQL migration smoke")

    database_name = f"rlcoach_migration_{uuid.uuid4().hex}"
    admin = psycopg2.connect(admin_url)
    admin.autocommit = True
    try:
        with admin.cursor() as cursor:
            cursor.execute(
                sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name))
            )

        database_url = admin_url.rsplit("/", 1)[0] + f"/{database_name}"
        env = {**os.environ, "DATABASE_URL": database_url, "PYTHONPATH": "src"}
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            check=True,
            env=env,
            capture_output=True,
            text=True,
        )

        migrated = psycopg2.connect(database_url)
        try:
            with migrated.cursor() as cursor:
                cursor.execute("SELECT version_num FROM alembic_version")
                assert cursor.fetchone() == ("004_coach_token_reservations",)
                cursor.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'coach_messages' "
                    "AND column_name = 'content_json'"
                )
                assert cursor.fetchone() == ("content_json",)
        finally:
            migrated.close()
    finally:
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (database_name,),
            )
            cursor.execute(
                sql.SQL("DROP DATABASE IF EXISTS {}").format(
                    sql.Identifier(database_name)
                )
            )
        admin.close()
