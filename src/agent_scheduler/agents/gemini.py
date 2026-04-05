"""Gemini CLI runner."""

from ..config import TaskEntry
from .base import AgentRunner


class GeminiRunner(AgentRunner):
    def build_command(self, task: TaskEntry) -> list[str]:
        return ["gemini", "--model", task.model, "-p", task.prompt]
