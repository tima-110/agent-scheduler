"""Tests for scheduler.py — is_due, topological_batches, cascade failure."""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from agent_scheduler.config import CLIChoice, ScheduleType, TaskEntry
from agent_scheduler.scheduler import (
    is_due,
    parse_hhmm,
    parse_interval,
    topological_batches,
)
from agent_scheduler.state import init_db, record_run


def _task(id, schedule_type="frequency", schedule_value="1h", depends_on=None, order=0):
    return TaskEntry(
        id=id,
        enabled=True,
        cli=CLIChoice.claude_code,
        model="sonnet",
        prompt="test",
        project_dir=Path("/tmp"),
        schedule_type=ScheduleType(schedule_type),
        schedule_value=schedule_value,
        order=order,
        depends_on=depends_on or [],
    )


def test_parse_interval_hours():
    assert parse_interval("1h") == timedelta(hours=1)


def test_parse_interval_minutes():
    assert parse_interval("30m") == timedelta(minutes=30)


def test_parse_interval_invalid():
    with pytest.raises(ValueError):
        parse_interval("abc")


def test_parse_hhmm():
    from datetime import date
    result = parse_hhmm("14:30", date(2026, 1, 1))
    assert result.hour == 14
    assert result.minute == 30


def test_is_due_frequency_never_run():
    db = Path(tempfile.mktemp(suffix=".db"))
    init_db(db)
    t = _task("t1", schedule_value="1h")
    assert is_due(t, datetime.now(), db_path=db) is True
    db.unlink()


def test_is_due_frequency_not_yet():
    db = Path(tempfile.mktemp(suffix=".db"))
    init_db(db)
    t = _task("t1", schedule_value="1h")
    record_run("t1", "success", 0, db_path=db)
    # Just ran, so not due yet
    assert is_due(t, datetime.now(), db_path=db) is False
    db.unlink()


def test_is_due_frequency_overdue():
    db = Path(tempfile.mktemp(suffix=".db"))
    init_db(db)
    t = _task("t1", schedule_value="1h")
    record_run("t1", "success", 0, db_path=db)
    future = datetime.now() + timedelta(hours=2)
    assert is_due(t, future, db_path=db) is True
    db.unlink()


def test_topological_batches_no_deps():
    tasks = [_task("a", order=1), _task("b", order=2)]
    batches = topological_batches(tasks)
    # Both should be in one batch since no deps
    assert len(batches) == 1
    assert len(batches[0]) == 2


def test_topological_batches_with_deps():
    t1 = _task("a", order=1)
    t2 = _task("b", order=2, depends_on=["a"])
    batches = topological_batches([t1, t2])
    assert len(batches) == 2
    assert batches[0][0].id == "a"
    assert batches[1][0].id == "b"


def test_topological_batches_concurrent_same_order():
    t1 = _task("a", order=1)
    t2 = _task("b", order=1)
    t3 = _task("c", order=2, depends_on=["a", "b"])
    batches = topological_batches([t1, t2, t3])
    assert len(batches) == 2
    assert len(batches[0]) == 2  # a and b concurrent
