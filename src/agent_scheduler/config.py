"""Pydantic models for task configuration and app settings."""

import csv
import socket
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, field_validator
from pydantic_settings import BaseSettings


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
    model: str
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

    def runs_on_this_host(self) -> bool:
        if not self.host:
            return True
        return socket.gethostname() in self.host


class AppConfig(BaseSettings):
    google_sheet_id: str = ""
    google_sheet_name: str = "Sheet1"
    tasks_csv: Path = Path("~/.local/share/agent-scheduler/tasks.csv")
    output_dir: Path = Path("~/agent-output")
    state_db: Path = Path("~/.local/share/agent-scheduler/state.db")
    log_file: Path = Path("~/.local/log/agent-scheduler.log")
    schedule_backend: str = "auto"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    def resolve_paths(self) -> "AppConfig":
        return self.model_copy(update={
            "tasks_csv": self.tasks_csv.expanduser(),
            "output_dir": self.output_dir.expanduser(),
            "state_db": self.state_db.expanduser(),
            "log_file": self.log_file.expanduser(),
        })


def load_tasks(csv_path: Path) -> list[TaskEntry]:
    tasks = []
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Strip whitespace from keys and values
            cleaned = {k.strip(): v.strip() if v else v for k, v in row.items()}
            tasks.append(TaskEntry(**cleaned))
    return tasks
