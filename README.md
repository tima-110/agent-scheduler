# agent-handler

Scheduled execution of AI coding agent CLIs from a shared Google Sheet.

agent-handler reads a task configuration spreadsheet, syncs it locally as JSON, resolves execution order and dependencies, runs the appropriate agent CLI (Claude Code, Codex CLI, Gemini CLI, or OpenCode), and records results in a local SQLite database. A single Google Sheet drives multiple machines — each host filters tasks by hostname and maintains independent state.

## Supported CLIs

| CLI | Command shape |
|-----|---------------|
| [Claude Code](https://docs.anthropic.com/en/docs/claude-code) | `claude [--model <model>] [--output-format json] --print "<prompt>"` |
| [Codex CLI](https://github.com/openai/codex) | `codex exec [--model <model>] [--json] "<prompt>"` |
| [Gemini CLI](https://github.com/google-gemini/gemini-cli) | `gemini [--model <model>] [--output-format json] -p "<prompt>"` |
| [OpenCode](https://github.com/opencode-ai/opencode) | `opencode run [--model <model>] [--format json] "<prompt>"` |

`--model` is only passed when set in the task config. Extra flags can be added via the `cli_args` column.

## Prerequisites

- **Python 3.11+**
- **A Google Sheet** with the agent-handler GAS script deployed (see [Google Apps Script Setup](#google-apps-script-setup) below)
- **Agent CLIs** — whichever you plan to use must be installed and pre-authenticated on each host
- Each agent CLI must be on `PATH` in the environment where the scheduler runs (relevant for cron/launchd)

## Google Apps Script Setup

This is a one-time setup per spreadsheet. It deploys a lightweight JSON API directly from your Google Sheet, eliminating any third-party CLI dependency.

1. **Create a new Google Sheet** (or open an existing one) that will hold your tasks.

2. Open **Extensions → Apps Script**.

3. Delete the default `Code.gs` content and paste in the contents of [`docs/gas-script.js`](docs/gas-script.js) from this repo.

4. Set the `API_KEY` constant at the top of the script to a secret string of your choosing.

5. Click **Deploy → New deployment**:
   - Type: **Web app**
   - Execute as: **Me**
   - Who has access: **Anyone**

6. Click **Deploy** and copy the deployment URL.

7. Add the URL and your API key to `config.toml`:
   ```toml
   [sheets]
   gas_url = "<paste deployment URL here>"
   gas_api_key = "<same key from the script>"
   name = "Sheet1"
   ```

> **Tip:** You can also set `AGENT_HANDLER_GAS_KEY` as an environment variable instead of storing the key in config.toml.

## Installation

```bash
# With pipx (recommended)
pipx install .

# Or with pip in a venv
pip install -e .
```

## Quick Start

```bash
# 1. Deploy docs/gas-script.js to your Google Sheet (see above)

# 2. Run the guided setup (creates config, tests endpoint, verifies sheet access)
agent-handler init

# 3. Validate your task configuration
agent-handler validate

# 4. Preview what would run
agent-handler run --dry-run

# 5. Run a scheduling pass manually
agent-handler run --no-sync

# 6. Install the 30-minute orchestrator schedule
agent-handler install
```

The `init` command prompts for your GAS Web App URL, API key, and worksheet name, then writes `config.toml`, verifies the endpoint is reachable, and confirms it can read the sheet. See [docs/config-guide.md](docs/config-guide.md) for manual setup and the full column reference.

## CLI Reference

### `agent-handler init`

Interactive guided setup. Prompts for GAS Web App URL, API key, worksheet name, and optional hostname alias. Creates `config.toml`, verifies the GAS endpoint, tests sheet connectivity, and initializes the state database.

```
agent-handler init
```

### `agent-handler sync`

Pull the Google Sheet to a local JSON file.

```
agent-handler sync [--config/-c PATH]
```

### `agent-handler run`

Execute one full scheduling pass — sync, filter, and run due tasks.

```
agent-handler run [--config/-c PATH] [--csv/-f PATH] [--dry-run] [--no-sync] [--verbose/-v]
```

| Flag | Description |
|------|-------------|
| `--dry-run` | Print intended actions with zero side effects |
| `--no-sync` | Skip the Google Sheet sync step (use local tasks file as-is) |
| `--csv/-f` | Override the tasks file path from config |
| `--verbose/-v` | Verbose output |

### `agent-handler install`

Verify prerequisites and install a 30-minute orchestrator schedule entry.

```
agent-handler install [--config/-c PATH] [--backend auto|cron|launchd]
```

Auto-detects the backend: **launchd** on macOS, **cron** elsewhere. The installed job runs `agent-handler run --no-sync` every 30 minutes.

### `agent-handler uninstall`

Remove the orchestrator schedule entry.

```
agent-handler uninstall [--config/-c PATH] [--backend auto|cron|launchd]
```

### `agent-handler status`

Show whether the schedule is active and the last run result per task.

```
agent-handler status [--config/-c PATH] [--csv/-f PATH]
```

### `agent-handler list`

Display a rich table of all tasks applicable to this host.

```
agent-handler list [--config/-c PATH] [--csv/-f PATH]
```

### `agent-handler validate`

Check task configuration for errors. Exits with code 1 on failure.

```
agent-handler validate [--config/-c PATH] [--csv/-f PATH]
```

Checks:
- Unique task IDs
- All `depends_on` references resolve to existing task IDs
- No circular dependencies
- `project_dir` paths exist on this machine

### `agent-handler whoami`

Print the hostname used for task filtering.

```
agent-handler whoami [--config/-c PATH]
```

Shows the resolved hostname (from `config.toml` alias or system default). Use this value in the `host` column of your Google Sheet.

## How It Works

### Scheduling

The orchestrator runs every **30 minutes** via cron or launchd. Each pass:

1. **Sync** — pulls the Google Sheet via the GAS Web App to a local JSON file (skipped with `--no-sync`)
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

Each successful task's stdout is written to a file in the configured output directory. The `output_format` setting controls the file extension and, for supported CLIs, is passed as a flag to the CLI itself (e.g. `--output-format json` for Claude Code) so the CLI produces native formatted output. The scheduler writes stdout verbatim to the output file. The scheduler never pipes output between tasks — if a downstream task needs upstream output, its prompt should reference the expected file path.

## Multi-Machine Setup

A single Google Sheet can drive multiple machines. Each machine:

- Filters tasks by the `host` column (comma-separated hostnames; blank = all hosts)
- Maintains its own SQLite database (platform-standard location)
- Uses `~`-relative paths that expand correctly per machine

Find your machine's hostname with:

```bash
agent-handler whoami
```

You can set a friendly alias in `config.toml` so you don't have to use the raw system hostname:

```toml
hostname = "my-macbook"
```

### Per-machine setup

Each machine needs:

1. `agent-handler` installed (`pipx install .`)
2. A `config.toml` pointing to the same GAS Web App URL (can be identical across machines — paths use `~`)
3. The relevant agent CLIs installed and authenticated
4. `agent-handler install` to set up the local schedule

## Configuration

Configuration lives in a `config.toml` file at the platform-standard location:

- **macOS:** `~/Library/Application Support/agent-handler/config.toml`
- **Linux:** `~/.config/agent-handler/config.toml`

Override with `--config /path/to/config.toml` on any command.

See [docs/config-guide.md](docs/config-guide.md) for the full spreadsheet column reference, config.toml options, example task rows, and multi-host patterns.

## Development

```bash
# Install in editable mode
pip install -e .

# Run tests
pytest tests/ -v
```

## Architecture

```
Google Sheet  ──GAS Web App──>  HTTP JSON  ──load_tasks()──>  TaskEntry models
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
