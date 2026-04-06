"""Pydantic models for task configuration and app settings."""

import json
import socket
import tomllib
from enum import Enum
from pathlib import Path
from typing import Optional

import platformdirs
from pydantic import BaseModel, field_validator

APP_NAME = "agent-scheduler"


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


class TaskEntry(BaseModel):
    id: str
    enabled: bool
    host: list[str] = []
    cli: CLIChoice
    model: str = ""
    agent: Optional[str] = None
    prompt: str
    project_dir: Path
    schedule_type: ScheduleType
    schedule_value: str
    order: int = 0
    depends_on: list[str] = []
    output_dir: Optional[Path] = None
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
    google_sheet_id: str = ""
    google_sheet_name: str = "Sheet1"
    hostname: Optional[str] = None
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
            self.log_file = _default_log_dir() / "agent-scheduler.log"

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
    if "id" in sheets:
        flat["google_sheet_id"] = sheets["id"]
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
