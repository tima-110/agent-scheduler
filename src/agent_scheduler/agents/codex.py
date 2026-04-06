"""Codex CLI runner."""

from ..config import TaskEntry
from .base import AgentRunner


class CodexRunner(AgentRunner):
    def build_command(self, task: TaskEntry) -> list[str]:
        cmd = ["codex", "exec"]
        if task.model:
            cmd.extend(["--model", task.model])
        if task.output_format.value == "json":
            cmd.append("--json")
        cmd.append(task.prompt)
        return cmd
