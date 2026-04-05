"""Abstract base for agent CLI runners."""

import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..config import TaskEntry
from ..output.writer import write_output


@dataclass
class AgentResult:
    task_id: str
    exit_code: int
    status: str  # 'success' | 'failed'
    error_msg: str = ""


class AgentRunner(ABC):
    @abstractmethod
    def build_command(self, task: TaskEntry) -> list[str]: ...

    def run(self, task: TaskEntry, output_dir=None, hostname: str = "", dry_run: bool = False) -> AgentResult:
        cmd = self.build_command(task)
        if dry_run:
            return AgentResult(task.id, 0, "success")

        result = subprocess.run(
            cmd, cwd=task.project_dir,
            capture_output=True, text=True,
        )
        status = "success" if result.returncode == 0 else "failed"
        if status == "success" and output_dir:
            write_output(result.stdout, task, output_dir, hostname)
        return AgentResult(task.id, result.returncode, status, result.stderr)
