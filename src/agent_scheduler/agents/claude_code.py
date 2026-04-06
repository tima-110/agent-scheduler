"""Claude Code CLI runner."""

from ..config import TaskEntry
from .base import AgentRunner


class ClaudeCodeRunner(AgentRunner):
    def build_command(self, task: TaskEntry) -> list[str]:
        cmd = ["claude"]
        if task.model:
            cmd.extend(["--model", task.model])
        if task.output_format.value != "text":
            cmd.extend(["--output-format", task.output_format.value])
        cmd.extend(["--print", task.prompt])
        if task.agent:
            cmd.extend(["--agent", task.agent])
        return cmd
