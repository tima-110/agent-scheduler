"""OpenCode CLI runner."""

from ..config import TaskEntry
from .base import AgentRunner


class OpenCodeRunner(AgentRunner):
    def build_command(self, task: TaskEntry) -> list[str]:
        return ["opencode", "run", "--model", task.model, task.prompt]
