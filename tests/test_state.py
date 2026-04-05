"""Tests for state.py — SQLite operations with temp DB."""

import tempfile
from pathlib import Path

from agent_scheduler.state import get_last_run, init_db, record_run

HOSTNAME = "test-host"


def _temp_db() -> Path:
    return Path(tempfile.mktemp(suffix=".db"))


def test_init_db():
    db = _temp_db()
    init_db(db)
    assert db.exists()
    db.unlink()


def test_record_and_get_last_run():
    db = _temp_db()
    init_db(db)

    assert get_last_run("task-1", db_path=db, hostname=HOSTNAME) is None

    record_run("task-1", "success", 0, db_path=db, hostname=HOSTNAME)
    last = get_last_run("task-1", db_path=db, hostname=HOSTNAME)
    assert last is not None

    db.unlink()


def test_multiple_runs_returns_latest():
    db = _temp_db()
    init_db(db)

    record_run("task-1", "failed", 1, "error1", db_path=db, hostname=HOSTNAME)
    record_run("task-1", "success", 0, db_path=db, hostname=HOSTNAME)

    last = get_last_run("task-1", db_path=db, hostname=HOSTNAME)
    assert last is not None

    db.unlink()


def test_hostname_isolation():
    db = _temp_db()
    init_db(db)

    record_run("task-1", "success", 0, db_path=db, hostname="host-a")
    assert get_last_run("task-1", db_path=db, hostname="host-a") is not None
    assert get_last_run("task-1", db_path=db, hostname="host-b") is None

    db.unlink()
