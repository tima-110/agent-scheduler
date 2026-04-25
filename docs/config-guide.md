# Configuration Guide

This guide covers how to set up the Google Sheet, deploy the GAS Web App, configure `config.toml`, and define tasks for agent-handler.

## Table of Contents

- [Google Apps Script Setup](#google-apps-script-setup)
- [Google Sheet Setup](#google-sheet-setup)
- [Column Reference](#column-reference)
- [Schedule Types](#schedule-types)
- [Execution Order and Dependencies](#execution-order-and-dependencies)
- [Output Configuration](#output-configuration)
- [Multi-Host Setup](#multi-host-setup)
- [Configuration File (config.toml)](#configuration-file-configtoml)
- [Example Task Rows](#example-task-rows)
- [Validation](#validation)

---

## Google Apps Script Setup

agent-handler communicates with Google Sheets through a Web App deployed from within the sheet itself. This is a **one-time setup per spreadsheet**. Once deployed, any machine can sync and update tasks via HTTPS without installing any Google-specific tooling.

### Steps

1. **Create a new Google Sheet** (or open an existing one) that will hold your tasks.

2. Go to **Extensions → Apps Script**.

3. Delete the default `Code.gs` content and paste in the contents of [`docs/gas-script.js`](gas-script.js) from this repo.

4. At the top of the script, set `API_KEY` to a secret string of your choosing:
   ```javascript
   const API_KEY = "my-secret-key";
   ```

5. Click **Deploy → New deployment**:
   - Type: **Web app**
   - Execute as: **Me**
   - Who has access: **Anyone**

6. Click **Deploy**. Copy the deployment URL — it looks like:
   ```
   https://script.google.com/macros/s/AKfycb.../exec
   ```

7. Add the URL and your key to `config.toml` under `[sheets]`:
   ```toml
   [sheets]
   gas_url = "https://script.google.com/macros/s/AKfycb.../exec"
   gas_api_key = "my-secret-key"
   name = "Sheet1"
   ```

> **Env var alternative:** Set `AGENT_HANDLER_GAS_KEY` in the environment instead of storing the key in config.toml. The env var takes effect when `gas_api_key` is blank in config.

### Redeploying after script changes

If you update `gas-script.js`, you must create a **new deployment** (not a new version of the existing one) to get a new URL. Update `gas_url` in config accordingly. The old URL continues working until you delete the old deployment.

### Security notes

- GET endpoints (read-only) are open — anyone with the URL can read your task list.
- POST endpoints (write operations) require the `apiKey` in the request body.
- Keep the URL confidential if your task configs are sensitive.

---

## Google Sheet Setup

> **Quick path:** Run `agent-handler init` for interactive guided setup. The steps below are for manual configuration or reference.

After deploying the GAS script:

1. **Add the header row** to your sheet. The easiest way is:
   ```bash
   agent-handler setup-sheet
   ```
   Or run `agent-handler init` and choose to write the header when prompted.

   The expected column names are:
   ```
   id | enabled | host | cli | model | agent | prompt | project_dir | schedule_type | schedule_value | order | depends_on | output_dir | output_format | output_filename | cli_args
   ```

2. **Add task rows** using `agent-handler task add` or by editing the sheet directly.

3. **Sync** to pull the sheet to your local machine:
   ```bash
   agent-handler sync
   ```

---

## Column Reference

| Column | Type | Required | Description | Example |
|--------|------|----------|-------------|---------|
| `id` | string | Yes | Unique task identifier slug. Used in dependency references, output filenames, and run state. | `fetch-docs` |
| `enabled` | boolean | Yes | `true` or `false`. Disabled tasks are skipped entirely. | `true` |
| `host` | string | No | Comma-separated hostnames. Task runs only on listed hosts. **Blank = runs on all hosts.** | `macbook-pro,dev-server` |
| `cli` | enum | Yes | Which agent CLI to invoke. One of: `claude-code`, `codex`, `gemini`, `opencode`. | `claude-code` |
| `model` | string | No | Model name passed to the CLI's `--model` flag. If blank, the CLI uses its own default. | `sonnet` |
| `agent` | string | No | Named agent/persona. Currently only used by Claude Code (`--agent` flag). | `reviewer` |
| `prompt` | string | Yes | The prompt text sent to the agent CLI. | `Review open PRs and summarize findings` |
| `project_dir` | path | Yes | Working directory for the CLI invocation. Supports `~`-relative paths. | `~/projects/my-app` |
| `schedule_type` | enum | Yes | `time` (run at a specific time) or `frequency` (run every N hours/minutes). | `frequency` |
| `schedule_value` | string | Yes | For `time`: `HH:MM` (24h). For `frequency`: `Nh` or `Nm`. | `09:00` or `1h` or `30m` |
| `order` | integer | No | Execution priority within a batch. Lower numbers run first. Ties run concurrently. Default: `0`. | `1` |
| `depends_on` | string | No | Comma-separated task `id`s. This task waits for all listed tasks to succeed. | `fetch-docs,lint-code` |
| `output_dir` | path | No | Where to write output files. `~`-relative. Falls back to `output_dir` in `config.toml`. | `~/agent-output/reviews` |
| `output_format` | enum | No | `text`, `json`, or `markdown`. Default: `text`. | `markdown` |
| `output_filename` | string | No | Filename template. Default: `{id}-{timestamp}.{ext}`. | `{id}-{timestamp}.{ext}` |
| `cli_args` | string | No | Extra CLI flags appended to the command. Parsed with shell-style splitting (supports quoted args). | `--max-budget-usd 0.50 --verbose` |

### Column Value Notes

- **Booleans** accept `true`/`false`, `yes`/`no`, `1`/`0` (case-insensitive).
- **Paths** with `~` are expanded to the user's home directory at runtime, so `~/projects/app` works correctly on every machine.
- **Comma-separated fields** (`host`, `depends_on`) are split on commas with whitespace trimmed. A blank cell means "none" (no host filter, no dependencies).

---

## Schedule Types

### `frequency` — Run every N hours/minutes

Set `schedule_type` to `frequency` and `schedule_value` to a duration:

| Value | Meaning |
|-------|---------|
| `30m` | Every 30 minutes |
| `1h` | Every hour |
| `2h` | Every 2 hours |
| `6h` | Every 6 hours |

A frequency task is **due** when `now - last_run >= interval`. If the task has never run, it is immediately due.

Since the orchestrator ticks every 30 minutes, the effective minimum frequency is ~30 minutes. A `15m` frequency will still only be checked every 30 minutes.

### `time` — Run at a specific time daily

Set `schedule_type` to `time` and `schedule_value` to a 24-hour time:

| Value | Meaning |
|-------|---------|
| `09:00` | 9:00 AM |
| `14:30` | 2:30 PM |
| `00:00` | Midnight |

A time task is **due** when the target time falls within the window `(last_run, now]`. With a 30-minute tick, a `09:00` task will fire during the tick that covers 9:00 AM (between 8:30 and 9:00, or 9:00 and 9:30 depending on tick alignment).

---

## Execution Order and Dependencies

### The `order` column

Tasks are grouped into **batches** based on their dependency graph. Within each batch, tasks are sorted by `order` (ascending). Tasks with the same order and no inter-dependencies run **concurrently** (up to 4 threads).

Example:

| Task | Order | Depends On |
|------|-------|------------|
| `sync-data` | 1 | — |
| `lint-code` | 1 | — |
| `analyze` | 2 | `sync-data` |
| `report` | 3 | `sync-data, analyze` |

Execution flow:
1. **Batch 1:** `sync-data` and `lint-code` run concurrently (both order 1, no shared deps)
2. **Batch 2:** `analyze` runs (depends on `sync-data`)
3. **Batch 3:** `report` runs (depends on both `sync-data` and `analyze`)

### Failure cascading

If a task **fails** (non-zero exit code), every task that depends on it — directly or transitively — is **skipped** and recorded with status `skipped` and reason `upstream failed`.

Tasks with **no dependency relationship** to the failure are unaffected. In the example above, if `sync-data` fails, then `analyze` and `report` are skipped, but `lint-code` still runs.

### Circular dependencies

Circular dependency chains (A depends on B, B depends on A) are caught by `agent-handler validate` and will cause an error. Fix these in the spreadsheet before running.

---

## Output Configuration

Each successful task writes the CLI's stdout verbatim to a file. The `output_format` setting controls the file extension and, for supported CLIs, is passed as a native flag so the CLI produces formatted output directly.

### `output_dir`

Per-task output directory. Supports `~`-relative paths. If blank, falls back to the global `output_dir` from `config.toml` (default: `~/agent-output`).

### `output_format`

| Format | Extension | CLI behavior |
|--------|-----------|-------------|
| `text` | `.txt` | No format flag passed; raw stdout saved as-is |
| `json` | `.json` | Format flag passed to CLI (see below); stdout saved as-is |
| `markdown` | `.md` | `--output-format markdown` passed to Claude Code and Gemini; stdout saved as-is |

The scheduler writes stdout verbatim — the CLI is responsible for producing the correct format. JSON output flag per CLI:

| CLI | Flag |
|-----|------|
| Claude Code | `--output-format json` |
| Gemini | `--output-format json` |
| Codex | `--json` (JSONL events) |
| OpenCode | `--format json` |

### `cli_args`

Freeform extra flags appended to the CLI command. Use this for any CLI-specific options not covered by other columns. Parsed with `shlex.split` so quoted arguments are handled correctly.

Examples:
- `--max-budget-usd 0.50` — limit API spend per run (Claude Code)
- `--full-auto` — enable automatic execution (Codex)
- `--json` — JSONL output (Codex exec)

### `output_filename`

A template string with these variables:

| Variable | Expands to | Example |
|----------|------------|---------|
| `{id}` | Task ID | `fetch-docs` |
| `{timestamp}` | `YYYYMMDDTHHMMSS` | `20260405T093000` |
| `{ext}` | File extension from format | `md` |

Default: `{id}-{timestamp}.{ext}` produces files like `fetch-docs-20260405T093000.md`.

The `{timestamp}` variable ensures filenames are collision-safe across runs. Always include it.

### Chaining output between tasks

agent-handler does **not** pipe output between tasks. If a downstream task needs upstream output, write the upstream prompt to produce output at a known path, and reference that path in the downstream prompt. For example:

| Task | Prompt |
|------|--------|
| `fetch-docs` | `Fetch API docs and write a summary to ~/agent-output/docs-latest.md` |
| `analyze` | `Read ~/agent-output/docs-latest.md and analyze for breaking changes` |

---

## Multi-Host Setup

A single Google Sheet can drive tasks across multiple machines. Each machine:

- **Filters tasks** using the `host` column
- **Maintains its own SQLite database** — run state is never shared
- **Expands `~` paths** independently per user

### Finding your hostname

```bash
agent-handler whoami
```

This prints the resolved hostname — either your config alias or the system default. Use this value in the `host` column.

### Host column patterns

| `host` value | Behavior |
|--------------|----------|
| *(blank)* | Runs on **all** machines |
| `macbook-pro` | Runs only on `macbook-pro` |
| `macbook-pro,dev-server` | Runs on `macbook-pro` and `dev-server` |

### Hostname aliases

System hostnames can be opaque (e.g., `BMC-C02DT03GML85`). Set a friendly alias in `config.toml`:

```toml
hostname = "my-macbook"
```

Use this alias in the sheet's `host` column instead of the raw system hostname. If unset, `socket.gethostname()` is used.

### Per-machine setup

Each machine needs:

1. `agent-handler` installed (`pipx install .`)
2. A `config.toml` pointing to the same GAS Web App URL (can be identical across machines — paths use `~`)
3. The relevant agent CLIs installed and authenticated
4. `agent-handler install` to set up the local schedule

No Google credentials or OAuth setup is required on each machine — all access goes through the GAS Web App URL.

---

## Configuration File (config.toml)

The config file lives at the platform-standard location:

- **macOS:** `~/Library/Application Support/agent-handler/config.toml`
- **Linux:** `~/.config/agent-handler/config.toml`

Override with `--config /path/to/config.toml` on any command.

Copy `config.example.toml` from the repo to get started:

```toml
# Hostname alias (optional — defaults to system hostname)
# hostname = "my-macbook"

[sheets]
gas_url = "https://script.google.com/macros/s/YOUR_DEPLOYMENT_ID/exec"
gas_api_key = "your-secret-key"   # or set AGENT_HANDLER_GAS_KEY env var
name = "Sheet1"

# [paths]
# tasks_csv = "~/custom/path/tasks.json"
# output_dir = "~/agent-output"
# state_db = "~/custom/path/state.db"
# log_file = "~/custom/path/agent-handler.log"

# [schedule]
# backend = "auto"
```

### Settings reference

| Section | Key | Default | Description |
|---------|-----|---------|-------------|
| *(top-level)* | `hostname` | system hostname | Friendly alias for task filtering |
| `[sheets]` | `gas_url` | *(none)* | Deployed GAS Web App URL |
| `[sheets]` | `gas_api_key` | *(none)* | API key for write operations (or `AGENT_HANDLER_GAS_KEY` env var) |
| `[sheets]` | `name` | `Sheet1` | Worksheet tab name |
| `[paths]` | `tasks_csv` | platform data dir / `tasks.json` | Where the synced tasks file is stored |
| `[paths]` | `output_dir` | `~/agent-output` | Default output directory |
| `[paths]` | `state_db` | platform data dir / `state.db` | SQLite database path |
| `[paths]` | `log_file` | platform log dir / `agent-handler.log` | Log file path |
| `[schedule]` | `backend` | `auto` | `auto`, `cron`, or `launchd` |

**Platform data dir:** macOS `~/Library/Application Support/agent-handler/`, Linux `~/.local/share/agent-handler/`
**Platform log dir:** macOS `~/Library/Logs/agent-handler/`, Linux `~/.local/state/agent-handler/log/`

---

## Example Task Rows

### Daily code review at 9 AM on all machines

| Column | Value |
|--------|-------|
| `id` | `daily-review` |
| `enabled` | `true` |
| `host` | *(blank)* |
| `cli` | `claude-code` |
| `model` | `sonnet` |
| `prompt` | `Review open PRs in this repo and write a summary of findings` |
| `project_dir` | `~/projects/my-app` |
| `schedule_type` | `time` |
| `schedule_value` | `09:00` |
| `order` | `1` |

### Hourly sync on a specific machine

| Column | Value |
|--------|-------|
| `id` | `sync-data` |
| `enabled` | `true` |
| `host` | `prod-server` |
| `cli` | `codex` |
| `model` | `o3` |
| `prompt` | `Pull latest data from the API and update local cache` |
| `project_dir` | `~/projects/data-pipeline` |
| `schedule_type` | `frequency` |
| `schedule_value` | `1h` |
| `order` | `1` |

### Two-step pipeline with dependency

| id | enabled | cli | schedule_type | schedule_value | order | depends_on |
|----|---------|-----|---------------|----------------|-------|------------|
| `fetch-data` | `true` | `claude-code` | `frequency` | `2h` | `1` | |
| `generate-report` | `true` | `gemini` | `frequency` | `2h` | `2` | `fetch-data` |

`generate-report` only runs if `fetch-data` succeeds. Both are checked every 2 hours.

---

## Validation

Run `agent-handler validate` to check your configuration before going live. It verifies:

| Check | What it catches |
|-------|-----------------|
| **Unique IDs** | Duplicate `id` values in the spreadsheet |
| **Dependency references** | `depends_on` referencing a task `id` that doesn't exist |
| **Circular dependencies** | A depends on B, B depends on A (directly or transitively) |
| **Path existence** | `project_dir` that doesn't exist on this machine |

Example output on success:

```
All checks passed.
```

Example output on failure:

```
Validation failed with 2 error(s):
  x Duplicate task ID: 'fetch-docs'
  x Task 'report' depends on unknown task 'missing-task'
```

Fix the errors in the Google Sheet, run `agent-handler sync` to re-pull, and validate again.
