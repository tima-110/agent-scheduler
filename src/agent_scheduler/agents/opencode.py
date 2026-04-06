"""OpenCode CLI runner."""

from ..config import TaskEntry
from .base import AgentRunner


class OpenCodeRunner(AgentRunner):
    def build_command(self, task: TaskEntry) -> list[str]:
        cmd = ["opencode", "run"]
        if task.model:
            cmd.extend(["--model", task.model])
        cmd.append(task.prompt)
        return cmd
