"""Tests for config.py — JSON parsing, host filtering, path expansion, TOML loading."""

import socket
import tempfile
from pathlib import Path

import pytest

from agent_handler.config import (
    AppConfig,
    CLIChoice,
    OutputFormat,
    ScheduleType,
    TaskEntry,
    load_config,
    load_tasks,
)

FIXTURE = Path(__file__).parent / "fixtures" / "sample.json"


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
    t = tasks[1]
    assert t.depends_on == ["fetch-docs"]


def test_empty_depends_on():
    tasks = load_tasks(FIXTURE)
    t = tasks[0]
    assert t.depends_on == []


def test_disabled_task():
    tasks = load_tasks(FIXTURE)
    t = tasks[3]
    assert t.enabled is False


def test_host_filtering_empty_runs_everywhere():
    tasks = load_tasks(FIXTURE)
    for t in tasks:
        assert t.runs_on_this_host("any-host") is True


def test_host_filtering_with_alias():
    t = TaskEntry(
        id="test",
        enabled=True,
        host=["my-laptop"],
        cli=CLIChoice.claude_code,
        model="sonnet",
        prompt="test",
        project_dir=Path("/tmp"),
        schedule_type=ScheduleType.frequency,
        schedule_value="1h",
    )
    assert t.runs_on_this_host("my-laptop") is True
    assert t.runs_on_this_host("other-host") is False


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
    assert t.runs_on_this_host(socket.gethostname()) is True


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
    assert t.runs_on_this_host("my-host") is False


def test_path_expansion():
    tasks = load_tasks(FIXTURE)
    t = tasks[0]
    assert "~" not in str(t.project_dir)
    assert t.project_dir.is_absolute()


# --- TOML config loading ---

def test_load_config_defaults_when_missing():
    cfg = load_config(Path("/nonexistent/config.toml"))
    assert cfg.gas_url == ""
    assert cfg.gas_api_key == ""
    assert cfg.google_sheet_name == "Sheet1"
    assert cfg.hostname is None
    assert cfg.schedule_backend == "auto"


def test_load_config_from_toml():
    content = b"""
hostname = "my-macbook"

[sheets]
gas_url = "https://script.google.com/macros/s/abc123/exec"
gas_api_key = "test-key"
name = "Tasks"

[paths]
output_dir = "~/custom-output"

[schedule]
backend = "launchd"
"""
    with tempfile.NamedTemporaryFile(suffix=".toml", delete=False) as f:
        f.write(content)
        f.flush()
        cfg = load_config(Path(f.name))

    assert cfg.gas_url == "https://script.google.com/macros/s/abc123/exec"
    assert cfg.gas_api_key == "test-key"
    assert cfg.google_sheet_name == "Tasks"
    assert cfg.hostname == "my-macbook"
    assert cfg.output_dir == Path("~/custom-output")
    assert cfg.schedule_backend == "launchd"
    Path(f.name).unlink()


def test_get_hostname_with_alias():
    cfg = AppConfig(hostname="my-laptop")
    assert cfg.get_hostname() == "my-laptop"


def test_get_hostname_without_alias():
    cfg = AppConfig()
    assert cfg.get_hostname() == socket.gethostname()


def test_default_paths_are_platform_appropriate():
    cfg = AppConfig()
    assert cfg.tasks_csv is not None
    assert cfg.state_db is not None
    assert cfg.log_file is not None
    assert str(cfg.tasks_csv).endswith("tasks.json")
    assert str(cfg.state_db).endswith("state.db")


def test_gas_api_key_from_env(monkeypatch):
    monkeypatch.setenv("AGENT_HANDLER_GAS_KEY", "env-key")
    cfg = AppConfig()
    assert cfg.gas_api_key == "env-key"


def test_gas_api_key_config_takes_precedence_over_env(monkeypatch):
    monkeypatch.setenv("AGENT_HANDLER_GAS_KEY", "env-key")
    cfg = AppConfig(gas_api_key="config-key")
    assert cfg.gas_api_key == "config-key"
