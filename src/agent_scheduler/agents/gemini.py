"""Gemini CLI runner."""

from ..config import TaskEntry
from .base import AgentRunner


class GeminiRunner(AgentRunner):
    def build_command(self, task: TaskEntry) -> list[str]:
        cmd = ["gemini"]
        if task.model:
            cmd.extend(["--model", task.model])
        if task.output_format.value != "text":
            cmd.extend(["--output-format", task.output_format.value])
        cmd.extend(["-p", task.prompt])
        return cmd
