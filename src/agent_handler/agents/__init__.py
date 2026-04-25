"""Agent CLI runners."""
from __future__ import annotations

from .base import AgentResult, AgentRunner
from .claude_code import ClaudeCodeRunner
from .codex import CodexRunner
from .gemini import GeminiRunner
from .opencode import OpenCodeRunner
from ..config import CLIChoice


def get_runner(cli: CLIChoice) -> AgentRunner:
    runners = {
        CLIChoice.claude_code: ClaudeCodeRunner,
        CLIChoice.codex: CodexRunner,
        CLIChoice.gemini: GeminiRunner,
        CLIChoice.opencode: OpenCodeRunner,
    }
    return runners[cli]()
