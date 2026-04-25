"""Tests for config.py — JSON parsing, host filtering, path expansion, TOML loading, secret resolution."""
from __future__ import annotations

import socket
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from agent_handler.config import (
    AppConfig,
    CLIChoice,
    GASConfig,
    OutputFormat,
    ScheduleType,
    TaskEntry,
    _resolve_secret,
    load_config,
    load_gas_config,
    load_tasks,
    read_keychain,
    write_keychain,
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
    assert cfg.google_sheet_name == "Sheet1"
    assert cfg.hostname is None
    assert cfg.schedule_backend == "auto"


def test_load_config_from_toml():
    content = b"""
hostname = "my-macbook"

[sheets]
gas_url = "https://script.google.com/macros/s/abc123/exec"
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
    assert cfg.google_sheet_name == "Tasks"
    assert cfg.hostname == "my-macbook"
    assert cfg.output_dir == Path("~/custom-output")
    assert cfg.schedule_backend == "launchd"
    Path(f.name).unlink()


def test_load_config_ignores_legacy_gas_api_key():
    """Old config files with gas_api_key should load without error."""
    content = b"""
[sheets]
gas_url = "https://example.com/exec"
gas_api_key = "old-key-in-file"
name = "Sheet1"
"""
    with tempfile.NamedTemporaryFile(suffix=".toml", delete=False) as f:
        f.write(content)
        f.flush()
        cfg = load_config(Path(f.name))

    assert cfg.gas_url == "https://example.com/exec"
    assert not hasattr(cfg, "gas_api_key") or "gas_api_key" not in cfg.model_fields
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


# --- Secret resolution ---

def test_resolve_secret_from_env(monkeypatch):
    monkeypatch.setenv("AGENT_HANDLER_GAS_KEY", "env-key")
    value, source = _resolve_secret("AGENT_HANDLER_GAS_KEY", "AGENT_HANDLER_GAS_KEY")
    assert value == "env-key"
    assert source == "env"


def test_resolve_secret_from_keychain(monkeypatch):
    monkeypatch.delenv("AGENT_HANDLER_GAS_KEY", raising=False)
    with patch("agent_handler.config.read_keychain", return_value="keychain-key"):
        value, source = _resolve_secret("AGENT_HANDLER_GAS_KEY", "AGENT_HANDLER_GAS_KEY")
    assert value == "keychain-key"
    assert source == "keychain"


def test_resolve_secret_missing(monkeypatch):
    monkeypatch.delenv("AGENT_HANDLER_GAS_KEY", raising=False)
    with patch("agent_handler.config.read_keychain", return_value=None):
        value, source = _resolve_secret("AGENT_HANDLER_GAS_KEY", "AGENT_HANDLER_GAS_KEY")
    assert value is None
    assert source is None


def test_resolve_secret_env_takes_precedence_over_keychain(monkeypatch):
    monkeypatch.setenv("AGENT_HANDLER_GAS_KEY", "env-key")
    with patch("agent_handler.config.read_keychain", return_value="keychain-key"):
        value, source = _resolve_secret("AGENT_HANDLER_GAS_KEY", "AGENT_HANDLER_GAS_KEY")
    assert value == "env-key"
    assert source == "env"


def test_load_gas_config_success(monkeypatch):
    monkeypatch.setenv("AGENT_HANDLER_GAS_KEY", "test-key")
    gas_cfg = load_gas_config("https://example.com/exec")
    assert gas_cfg.endpoint_url == "https://example.com/exec"
    assert gas_cfg.api_key == "test-key"


def test_load_gas_config_missing_key(monkeypatch):
    monkeypatch.delenv("AGENT_HANDLER_GAS_KEY", raising=False)
    with patch("agent_handler.config.read_keychain", return_value=None):
        with pytest.raises(RuntimeError, match="Missing GAS API key"):
            load_gas_config("https://example.com/exec")


def test_load_gas_config_missing_url():
    with pytest.raises(RuntimeError, match="gas_url is not set"):
        load_gas_config("")


def test_read_keychain_returns_none_on_missing_binary():
    with patch("agent_handler.config.subprocess.run", side_effect=FileNotFoundError):
        assert read_keychain("TEST_ACCOUNT") is None


def test_write_keychain_raises_on_failure():
    with patch("agent_handler.config.subprocess.run") as mock_run:
        mock_run.side_effect = [
            type("Result", (), {"returncode": 0})(),  # delete succeeds
            type("Result", (), {"returncode": 1, "stderr": "denied"})(),  # add fails
        ]
        with pytest.raises(RuntimeError, match="Failed to write to keychain"):
            write_keychain("TEST_ACCOUNT", "test-password")
