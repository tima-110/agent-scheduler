"""Claude Code CLI runner."""

from ..config import TaskEntry
from .base import AgentRunner


class ClaudeCodeRunner(AgentRunner):
    def build_command(self, task: TaskEntry) -> list[str]:
        cmd = ["claude", "--model", task.model, "--print", task.prompt]
        if task.agent:
            cmd.extend(["--agent", task.agent])
        return cmd
