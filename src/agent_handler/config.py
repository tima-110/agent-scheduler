"""Pydantic models for task configuration and app settings."""
from __future__ import annotations

import json
import logging
import os
import socket
import subprocess
import sys
import tomllib
from enum import Enum
from pathlib import Path

import platformdirs
from pydantic import BaseModel, field_validator

APP_NAME = "agent-handler"
KEYCHAIN_SERVICE = "agent-handler"

log = logging.getLogger(__name__)


class CLIChoice(str, Enum):
    claude_code = "claude-code"
    codex = "codex"
    gemini = "gemini"
    opencode = "opencode"


class ScheduleType(str, Enum):
    time = "time"
    frequency = "frequency"


class OutputFormat(str, Enum):
    text = "text"
    json = "json"
    markdown = "markdown"
    stream_json = "stream-json"


class TaskEntry(BaseModel):
    id: str
    enabled: bool
    host: list[str] = []
    cli: CLIChoice
    model: str = ""
    agent: str | None = None
    prompt: str
    project_dir: Path
    schedule_type: ScheduleType
    schedule_value: str
    order: int = 0
    depends_on: list[str] = []
    output_dir: Path | None = None
    output_format: OutputFormat = OutputFormat.text
    output_filename: str = "{id}-{timestamp}.{ext}"
    cli_args: str = ""

    @field_validator("depends_on", "host", mode="before")
    @classmethod
    def parse_csv_list(cls, v):
        if not v:
            return []
        if isinstance(v, list):
            return v
        return [x.strip() for x in str(v).split(",") if x.strip()]

    @field_validator("project_dir", "output_dir", mode="before")
    @classmethod
    def expand_path(cls, v):
        return Path(v).expanduser() if v else v

    @field_validator("enabled", mode="before")
    @classmethod
    def parse_bool(cls, v):
        if isinstance(v, str):
            return v.strip().lower() in ("true", "1", "yes")
        return bool(v)

    @field_validator("order", mode="before")
    @classmethod
    def parse_order(cls, v):
        if not v or (isinstance(v, str) and not v.strip()):
            return 0
        return int(v)

    def runs_on_this_host(self, hostname: str) -> bool:
        if not self.host:
            return True
        return hostname in self.host


def _default_data_dir() -> Path:
    return Path(platformdirs.user_data_dir(APP_NAME))


def _default_config_dir() -> Path:
    return Path(platformdirs.user_config_dir(APP_NAME))


def _default_log_dir() -> Path:
    return Path(platformdirs.user_log_dir(APP_NAME))


class AppConfig(BaseModel):
    gas_url: str = ""
    google_sheet_name: str = "Sheet1"
    hostname: str | None = None
    tasks_csv: Path = None
    output_dir: Path = Path("~/agent-output")
    state_db: Path = None
    log_file: Path = None
    schedule_backend: str = "auto"

    def model_post_init(self, __context):
        if self.tasks_csv is None:
            self.tasks_csv = _default_data_dir() / "tasks.json"
        if self.state_db is None:
            self.state_db = _default_data_dir() / "state.db"
        if self.log_file is None:
            self.log_file = _default_log_dir() / "agent-handler.log"

    def get_hostname(self) -> str:
        return self.hostname or socket.gethostname()

    def resolve_paths(self) -> "AppConfig":
        return self.model_copy(update={
            "tasks_csv": self.tasks_csv.expanduser(),
            "output_dir": self.output_dir.expanduser(),
            "state_db": self.state_db.expanduser(),
            "log_file": self.log_file.expanduser(),
        })


def default_config_path() -> Path:
    return _default_config_dir() / "config.toml"


def load_config(path: Path | None = None) -> AppConfig:
    config_path = path or default_config_path()
    if not config_path.exists():
        return AppConfig()

    with open(config_path, "rb") as f:
        raw = tomllib.load(f)

    flat = {}
    # [sheets] section
    sheets = raw.get("sheets", {})
    if "gas_url" in sheets:
        flat["gas_url"] = sheets["gas_url"]
    if "name" in sheets:
        flat["google_sheet_name"] = sheets["name"]

    # top-level hostname
    if "hostname" in raw:
        flat["hostname"] = raw["hostname"]

    # [paths] section
    paths = raw.get("paths", {})
    for key in ("tasks_csv", "output_dir", "state_db", "log_file"):
        if key in paths:
            flat[key] = Path(paths[key])

    # [schedule] section
    schedule = raw.get("schedule", {})
    if "backend" in schedule:
        flat["schedule_backend"] = schedule["backend"]

    return AppConfig(**flat)


def load_tasks(tasks_path: Path) -> list[TaskEntry]:
    with open(tasks_path) as f:
        rows = json.load(f)
    tasks = []
    for row in rows:
        cleaned = {k.strip(): v.strip() if isinstance(v, str) else v for k, v in row.items()}
        tasks.append(TaskEntry(**cleaned))
    return tasks


# ------------------------------------------------------------------
# GAS credentials: keychain + env var resolution
# ------------------------------------------------------------------

class GASConfig(BaseModel):
    """GAS API connection settings — resolved at runtime, never from TOML."""

    endpoint_url: str
    api_key: str


def read_keychain(account: str) -> str | None:
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-a", account, "-w"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def write_keychain(account: str, password: str) -> None:
    subprocess.run(
        ["security", "delete-generic-password", "-s", KEYCHAIN_SERVICE, "-a", account],
        capture_output=True, timeout=5,
    )
    result = subprocess.run(
        ["security", "add-generic-password", "-s", KEYCHAIN_SERVICE, "-a", account, "-w", password],
        capture_output=True, text=True, timeout=5,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to write to keychain: {result.stderr.strip()}")


def _resolve_secret(env_var: str, keychain_account: str) -> tuple[str, str] | tuple[None, None]:
    value = os.environ.get(env_var)
    if value:
        return value, "env"
    value = read_keychain(keychain_account)
    if value:
        return value, "keychain"
    return None, None


def load_gas_config(gas_url: str) -> GASConfig:
    if not gas_url:
        raise RuntimeError(
            "gas_url is not set in config.toml. "
            "Deploy the GAS script and set gas_url under [sheets]."
        )
    key, _ = _resolve_secret("AGENT_HANDLER_GAS_KEY", "AGENT_HANDLER_GAS_KEY")
    if not key:
        raise RuntimeError(
            "Missing GAS API key. "
            "Set via env var AGENT_HANDLER_GAS_KEY or run: agent-handler set-credentials"
        )
    return GASConfig(endpoint_url=gas_url, api_key=key)


# ------------------------------------------------------------------
# Logging setup
# ------------------------------------------------------------------

def setup_logging(verbose: bool = False, debug: bool = False) -> None:
    level = logging.DEBUG if debug else (logging.INFO if verbose else logging.WARNING)
    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(levelname)-7s  %(message)s",
        stream=sys.stderr,
    )
