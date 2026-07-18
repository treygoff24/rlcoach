"""Failure-path harnesses for destructive deployment scripts."""

from __future__ import annotations

import os
import subprocess


def test_backup_stops_when_pg_dump_fails(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    docker = fake_bin / "docker"
    docker.write_text("#!/bin/sh\nexit 42\n", encoding="utf-8")
    docker.chmod(0o755)
    backup_dir = tmp_path / "backups"

    result = subprocess.run(
        ["bash", "scripts/backup.sh"],
        cwd=os.getcwd(),
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "BACKUP_DIR": str(backup_dir),
        },
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "Backup Complete" not in result.stdout
