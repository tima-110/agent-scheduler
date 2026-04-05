"""Tests for config.py — CSV parsing, host filtering, path expansion."""

import socket
from pathlib import Path

import pytest

from agent_scheduler.config import (
    CLIChoice,
    OutputFormat,
    ScheduleType,
    TaskEntry,
    load_tasks,
)

FIXTURE = Path(__file__).parent / "fixtures" / "sample.csv"


def test_load_tasks_count():
    tasks = load_tasks(FIXTURE)
    assert len(tasks) == 4


def test_task_fields():
    tasks = load_tasks(FIXTURE)
    t = tasks[0]
    assert t.id == "fetch-docs"
    assert t.enabled is True
    assert t.cli == CLIChoice.claude_code
    assert t.model == "sonnet"
    assert t.schedule_type == ScheduleType.frequency
    assert t.schedule_value == "1h"
    assert t.order == 1
    assert t.output_format == OutputFormat.markdown


def test_depends_on_parsing():
    tasks = load_tasks(FIXTURE)
    t = tasks[1]  # analyze-code depends on fetch-docs
    assert t.depends_on == ["fetch-docs"]


def test_empty_depends_on():
    tasks = load_tasks(FIXTURE)
    t = tasks[0]  # fetch-docs has no deps
    assert t.depends_on == []


def test_disabled_task():
    tasks = load_tasks(FIXTURE)
    t = tasks[3]
    assert t.enabled is False


def test_host_filtering_empty_runs_everywhere():
    tasks = load_tasks(FIXTURE)
    for t in tasks:
        assert t.runs_on_this_host() is True  # all have empty host


def test_host_filtering_specific():
    t = TaskEntry(
        id="test",
        enabled=True,
        host=[socket.gethostname()],
        cli=CLIChoice.claude_code,
        model="sonnet",
        prompt="test",
        project_dir=Path("/tmp"),
        schedule_type=ScheduleType.frequency,
        schedule_value="1h",
    )
    assert t.runs_on_this_host() is True


def test_host_filtering_other():
    t = TaskEntry(
        id="test",
        enabled=True,
        host=["other-host"],
        cli=CLIChoice.claude_code,
        model="sonnet",
        prompt="test",
        project_dir=Path("/tmp"),
        schedule_type=ScheduleType.frequency,
        schedule_value="1h",
    )
    assert t.runs_on_this_host() is False


def test_path_expansion():
    tasks = load_tasks(FIXTURE)
    t = tasks[0]
    assert "~" not in str(t.project_dir)
    assert t.project_dir.is_absolute()
