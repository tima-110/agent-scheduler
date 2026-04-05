"""Tests for agent runners — command construction."""

from pathlib import Path

from agent_scheduler.agents import get_runner
from agent_scheduler.agents.claude_code import ClaudeCodeRunner
from agent_scheduler.agents.codex import CodexRunner
from agent_scheduler.agents.gemini import GeminiRunner
from agent_scheduler.agents.opencode import OpenCodeRunner
from agent_scheduler.config import CLIChoice, ScheduleType, TaskEntry


def _task(cli, model="sonnet", agent=None, prompt="do something"):
    return TaskEntry(
        id="test-task",
        enabled=True,
        cli=cli,
        model=model,
        agent=agent,
        prompt=prompt,
        project_dir=Path("/tmp"),
        schedule_type=ScheduleType.frequency,
        schedule_value="1h",
    )


def test_claude_code_command():
    t = _task(CLIChoice.claude_code, model="sonnet", prompt="analyze this")
    runner = ClaudeCodeRunner()
    cmd = runner.build_command(t)
    assert cmd == ["claude", "--model", "sonnet", "--print", "analyze this"]


def test_claude_code_with_agent():
    t = _task(CLIChoice.claude_code, model="sonnet", agent="reviewer", prompt="review")
    runner = ClaudeCodeRunner()
    cmd = runner.build_command(t)
    assert "--agent" in cmd
    assert "reviewer" in cmd


def test_codex_command():
    t = _task(CLIChoice.codex, model="o3", prompt="analyze")
    runner = CodexRunner()
    cmd = runner.build_command(t)
    assert cmd == ["codex", "--model", "o3", "analyze"]


def test_gemini_command():
    t = _task(CLIChoice.gemini, model="gemini-2.5-pro", prompt="review PRs")
    runner = GeminiRunner()
    cmd = runner.build_command(t)
    assert cmd == ["gemini", "--model", "gemini-2.5-pro", "-p", "review PRs"]


def test_opencode_command():
    t = _task(CLIChoice.opencode, model="gpt-4.1", prompt="check code")
    runner = OpenCodeRunner()
    cmd = runner.build_command(t)
    assert cmd == ["opencode", "run", "--model", "gpt-4.1", "check code"]


def test_get_runner_factory():
    assert isinstance(get_runner(CLIChoice.claude_code), ClaudeCodeRunner)
    assert isinstance(get_runner(CLIChoice.codex), CodexRunner)
    assert isinstance(get_runner(CLIChoice.gemini), GeminiRunner)
    assert isinstance(get_runner(CLIChoice.opencode), OpenCodeRunner)
