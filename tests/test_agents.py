"""Tests for agent runners — command construction."""
from __future__ import annotations

from pathlib import Path

from agent_handler.agents import get_runner
from agent_handler.agents.claude_code import ClaudeCodeRunner
from agent_handler.agents.codex import CodexRunner
from agent_handler.agents.gemini import GeminiRunner
from agent_handler.agents.opencode import OpenCodeRunner
from agent_handler.config import CLIChoice, OutputFormat, ScheduleType, TaskEntry


def _task(cli, model="sonnet", agent=None, prompt="do something", output_format=OutputFormat.text):
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
        output_format=output_format,
    )


def test_claude_code_command():
    t = _task(CLIChoice.claude_code, model="sonnet", prompt="analyze this")
    runner = ClaudeCodeRunner()
    cmd = runner.build_command(t)
    assert cmd == ["claude", "--model", "sonnet", "--print", "analyze this"]


def test_claude_code_no_model():
    t = _task(CLIChoice.claude_code, model="", prompt="analyze this")
    runner = ClaudeCodeRunner()
    cmd = runner.build_command(t)
    assert cmd == ["claude", "--print", "analyze this"]


def test_claude_code_json_output_format():
    t = _task(CLIChoice.claude_code, model="sonnet", prompt="analyze", output_format=OutputFormat.json)
    runner = ClaudeCodeRunner()
    cmd = runner.build_command(t)
    assert cmd == ["claude", "--model", "sonnet", "--output-format", "json", "--print", "analyze"]


def test_claude_code_text_output_format_no_flag():
    t = _task(CLIChoice.claude_code, model="sonnet", prompt="analyze", output_format=OutputFormat.text)
    runner = ClaudeCodeRunner()
    cmd = runner.build_command(t)
    assert "--output-format" not in cmd


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
    assert cmd == ["codex", "exec", "--model", "o3", "analyze"]


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


def test_cli_args_appended():
    t = _task(CLIChoice.claude_code, model="sonnet", prompt="analyze")
    t.cli_args = '--max-budget-usd 0.50 --verbose'
    runner = ClaudeCodeRunner()
    cmd = runner.full_command(t)
    assert cmd[-3:] == ["--max-budget-usd", "0.50", "--verbose"]


def test_cli_args_empty_no_change():
    t = _task(CLIChoice.claude_code, model="sonnet", prompt="analyze")
    runner = ClaudeCodeRunner()
    assert runner.full_command(t) == runner.build_command(t)


def test_get_runner_factory():
    assert isinstance(get_runner(CLIChoice.claude_code), ClaudeCodeRunner)
    assert isinstance(get_runner(CLIChoice.codex), CodexRunner)
    assert isinstance(get_runner(CLIChoice.gemini), GeminiRunner)
    assert isinstance(get_runner(CLIChoice.opencode), OpenCodeRunner)
