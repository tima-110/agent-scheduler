"""OpenCode CLI runner."""

from ..config import TaskEntry
from .base import AgentRunner


class OpenCodeRunner(AgentRunner):
    def build_command(self, task: TaskEntry) -> list[str]:
        cmd = ["opencode", "run"]
        if task.model:
            cmd.extend(["--model", task.model])
        if task.output_format.value == "json":
            cmd.extend(["--format", "json"])
        cmd.append(task.prompt)
        return cmd
