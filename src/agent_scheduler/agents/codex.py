"""Codex CLI runner."""

from ..config import TaskEntry
from .base import AgentRunner


class CodexRunner(AgentRunner):
    def build_command(self, task: TaskEntry) -> list[str]:
        cmd = ["codex"]
        if task.model:
            cmd.extend(["--model", task.model])
        cmd.append(task.prompt)
        return cmd
