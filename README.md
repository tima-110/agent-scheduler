# agent-scheduler

Scheduled execution of AI coding agent CLIs from a shared Google Sheet.

agent-scheduler reads a task configuration spreadsheet, syncs it locally as CSV, resolves execution order and dependencies, runs the appropriate agent CLI (Claude Code, Codex CLI, Gemini CLI, or OpenCode), and records results in a local SQLite database. A single Google Sheet drives multiple machines — each host filters tasks by hostname and maintains independent state.

## Supported CLIs

| CLI | Command shape |
|-----|---------------|
| [Claude Code](https://docs.anthropic.com/en/docs/claude-code) | `claude --model <model> --print "<prompt>"` |
| [Codex CLI](https://github.com/openai/codex) | `codex --model <model> "<prompt>"` |
| [Gemini CLI](https://github.com/google-gemini/gemini-cli) | `gemini --model <model> -p "<prompt>"` |
| [OpenCode](https://github.com/opencode-ai/opencode) | `opencode run --model <model> "<prompt>"` |

## Prerequisites

- **Python 3.11+**
- **[gws CLI](https://github.com/nicholasgasior/gws)** — installed and authorized (`gws auth login`)
- **Agent CLIs** — whichever you plan to use must be installed and pre-authenticated on each host
- Each agent CLI must be on `PATH` in the environment where the scheduler runs (relevant for cron/launchd)

## Installation

```bash
# With pipx (recommended)
pipx install .

# Or with pip in a venv
pip install -e .
```

## Quick Start

```bash
# 1. Configure
cp .env.example .env
# Edit .env — set GOOGLE_SHEET_ID to your spreadsheet ID

# 2. Set up your Google Sheet (see docs/config-guide.md)

# 3. Sync the spreadsheet to local CSV
agent-scheduler sync

# 4. Validate your task configuration
agent-scheduler validate

# 5. Preview what would run
agent-scheduler run --dry-run

# 6. Run a scheduling pass manually
agent-scheduler run --no-sync

# 7. Install the 30-minute orchestrator schedule
agent-scheduler install
```

## CLI Reference

### `agent-scheduler sync`

Pull the Google Sheet to a local CSV file.

```
agent-scheduler sync [--config/-c PATH]
```

### `agent-scheduler run`

Execute one full scheduling pass — sync, filter, and run due tasks.

```
agent-scheduler run [--config/-c PATH] [--csv/-f PATH] [--dry-run] [--no-sync] [--verbose/-v]
```

| Flag | Description |
|------|-------------|
| `--dry-run` | Print intended actions with zero side effects |
| `--no-sync` | Skip the Google Sheet sync step (use local CSV as-is) |
| `--csv/-f` | Override the CSV path from config |
| `--verbose/-v` | Verbose output |

### `agent-scheduler install`

Verify prerequisites and install a 30-minute orchestrator schedule entry.

```
agent-scheduler install [--config/-c PATH] [--backend auto|cron|launchd]
```

Auto-detects the backend: **launchd** on macOS, **cron** elsewhere. The installed job runs `agent-scheduler run --no-sync` every 30 minutes.

### `agent-scheduler uninstall`

Remove the orchestrator schedule entry.

```
agent-scheduler uninstall [--config/-c PATH] [--backend auto|cron|launchd]
```

### `agent-scheduler status`

Show whether the schedule is active and the last run result per task.

```
agent-scheduler status [--config/-c PATH] [--csv/-f PATH]
```

### `agent-scheduler list`

Display a rich table of all tasks applicable to this host.

```
agent-scheduler list [--config/-c PATH] [--csv/-f PATH]
```

### `agent-scheduler validate`

Check task configuration for errors. Exits with code 1 on failure.

```
agent-scheduler validate [--config/-c PATH] [--csv/-f PATH]
```

Checks:
- Unique task IDs
- All `depends_on` references resolve to existing task IDs
- No circular dependencies
- `project_dir` paths exist on this machine

## How It Works

### Scheduling

The orchestrator runs every **30 minutes** via cron or launchd. Each pass:

1. **Sync** — pulls the Google Sheet to a local CSV (skipped with `--no-sync`)
2. **Filter** — keeps only tasks that are `enabled=true` and match this host
3. **Due check** — determines which tasks are due based on their schedule type
4. **Topological sort** — groups tasks into ordered batches using `depends_on` and `order`
5. **Execute** — runs each batch concurrently (up to 4 threads), cascading failures to dependents
6. **Record** — writes results to the local SQLite database

### Schedule Types

- **`frequency`** — run every N hours/minutes (e.g., `1h`, `30m`). Due when `now - last_run >= interval`.
- **`time`** — run at a specific time daily (e.g., `09:00`). Due when the target time falls within the window since last run.

### Execution Order and Dependencies

Tasks are sorted into batches by `depends_on` (topological sort) and `order` (within a batch). Tasks in the same batch with no inter-dependencies run **concurrently** via `ThreadPoolExecutor(max_workers=4)`.

If a task fails, all tasks that transitively depend on it are **skipped** and recorded as such. Tasks with no dependency relationship to the failure are unaffected.

### Output

Each successful task's stdout is written to a file in the configured output directory. Output format (`text`, `json`, `markdown`) and filename template are configurable per task. The scheduler never pipes output between tasks — if a downstream task needs upstream output, its prompt should reference the expected file path.

## Multi-Machine Setup

A single Google Sheet can drive multiple machines. Each machine:

- Filters tasks by the `host` column (comma-separated hostnames; blank = all hosts)
- Maintains its own SQLite database at `~/.local/share/agent-scheduler/state.db`
- Uses `~`-relative paths that expand correctly per machine

Find your machine's hostname with:

```bash
python3 -c "import socket; print(socket.gethostname())"
```

## Configuration

See [docs/config-guide.md](docs/config-guide.md) for the full spreadsheet column reference, `.env` options, example task rows, and multi-host patterns.

## Development

```bash
# Install in editable mode
pip install -e .

# Run tests
pytest tests/ -v
```

## Architecture

```
Google Sheet  ──gws CLI──>  local CSV  ──load_tasks()──>  TaskEntry models
                                                                │
                           SQLite DB  <──record_run()──  scheduler.run_pass()
                                                                │
                                                    ┌───────────┼───────────┐
                                                    v           v           v
                                              batch 1      batch 2      batch N
                                             (concurrent)  (concurrent)  (concurrent)
                                                    │           │           │
                                                    v           v           v
                                              AgentRunner  AgentRunner  AgentRunner
                                              (subprocess)  (subprocess)  (subprocess)
                                                    │           │           │
                                                    v           v           v
                                              output/writer  output/writer  output/writer
```
