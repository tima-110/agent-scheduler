# Configuration Guide

This guide covers how to set up the Google Sheet, configure `.env`, and define tasks for agent-scheduler.

## Table of Contents

- [Google Sheet Setup](#google-sheet-setup)
- [Column Reference](#column-reference)
- [Schedule Types](#schedule-types)
- [Execution Order and Dependencies](#execution-order-and-dependencies)
- [Output Configuration](#output-configuration)
- [Multi-Host Setup](#multi-host-setup)
- [Environment Configuration (.env)](#environment-configuration-env)
- [Example Task Rows](#example-task-rows)
- [Validation](#validation)

---

## Google Sheet Setup

1. **Create a new Google Sheet** (or use an existing one).

2. **Add the header row** with exactly these column names. Column order is flexible — the CSV export uses headers, not position.

   ```
   id | enabled | host | cli | model | agent | prompt | project_dir | schedule_type | schedule_value | order | depends_on | output_dir | output_format | output_filename
   ```

3. **Share the sheet** with the Google account authorized in `gws`. The `gws` CLI handles authentication — no service accounts or API keys are stored by agent-scheduler.

4. **Copy the Sheet ID** from the URL. For a URL like:
   ```
   https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms/edit
   ```
   The sheet ID is: `1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms`

5. **Set `GOOGLE_SHEET_ID`** in your `.env` file to this value.

6. If your tasks are on a worksheet other than `Sheet1`, also set `GOOGLE_SHEET_NAME`.

---

## Column Reference

| Column | Type | Required | Description | Example |
|--------|------|----------|-------------|---------|
| `id` | string | Yes | Unique task identifier slug. Used in dependency references, output filenames, and run state. | `fetch-docs` |
| `enabled` | boolean | Yes | `true` or `false`. Disabled tasks are skipped entirely. | `true` |
| `host` | string | No | Comma-separated hostnames. Task runs only on listed hosts. **Blank = runs on all hosts.** | `macbook-pro,dev-server` |
| `cli` | enum | Yes | Which agent CLI to invoke. One of: `claude-code`, `codex`, `gemini`, `opencode`. | `claude-code` |
| `model` | string | Yes | Model name passed to the CLI's `--model` flag. | `sonnet` |
| `agent` | string | No | Named agent/persona. Currently only used by Claude Code (`--agent` flag). | `reviewer` |
| `prompt` | string | Yes | The prompt text sent to the agent CLI. | `Review open PRs and summarize findings` |
| `project_dir` | path | Yes | Working directory for the CLI invocation. Supports `~`-relative paths. | `~/projects/my-app` |
| `schedule_type` | enum | Yes | `time` (run at a specific time) or `frequency` (run every N hours/minutes). | `frequency` |
| `schedule_value` | string | Yes | For `time`: `HH:MM` (24h). For `frequency`: `Nh` or `Nm`. | `09:00` or `1h` or `30m` |
| `order` | integer | No | Execution priority within a batch. Lower numbers run first. Ties run concurrently. Default: `0`. | `1` |
| `depends_on` | string | No | Comma-separated task `id`s. This task waits for all listed tasks to succeed. | `fetch-docs,lint-code` |
| `output_dir` | path | No | Where to write output files. `~`-relative. Falls back to `OUTPUT_DIR` from `.env`. | `~/agent-output/reviews` |
| `output_format` | enum | No | `text`, `json`, or `markdown`. Default: `text`. | `markdown` |
| `output_filename` | string | No | Filename template. Default: `{id}-{timestamp}.{ext}`. | `{id}-{timestamp}.{ext}` |

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

Circular dependency chains (A depends on B, B depends on A) are caught by `agent-scheduler validate` and will cause an error. Fix these in the spreadsheet before running.

---

## Output Configuration

Each successful task writes its stdout to a file.

### `output_dir`

Per-task output directory. Supports `~`-relative paths. If blank, falls back to the global `OUTPUT_DIR` from `.env`.

### `output_format`

| Format | Extension | Content |
|--------|-----------|---------|
| `text` | `.txt` | Raw stdout |
| `markdown` | `.md` | `# {task_id} — {timestamp}` header + stdout |
| `json` | `.json` | Structured object with `task_id`, `host`, `ran_at`, `output` |

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

agent-scheduler does **not** pipe output between tasks. If a downstream task needs upstream output, write the upstream prompt to produce output at a known path, and reference that path in the downstream prompt. For example:

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
python3 -c "import socket; print(socket.gethostname())"
```

This is the value to put in the `host` column.

### Host column patterns

| `host` value | Behavior |
|--------------|----------|
| *(blank)* | Runs on **all** machines |
| `macbook-pro` | Runs only on `macbook-pro` |
| `macbook-pro,dev-server` | Runs on `macbook-pro` and `dev-server` |

### Per-machine setup

Each machine needs:

1. `agent-scheduler` installed (`pipx install .`)
2. A `.env` file (can be identical across machines — paths use `~`)
3. `gws` CLI authorized (`gws auth login`)
4. The relevant agent CLIs installed and authenticated
5. `agent-scheduler install` to set up the local schedule

---

## Environment Configuration (.env)

Copy `.env.example` to `.env` and edit:

```dotenv
# Google Sheets
GOOGLE_SHEET_ID=1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms
GOOGLE_SHEET_NAME=Sheet1

# Paths (all support ~)
TASKS_CSV=~/.local/share/agent-scheduler/tasks.csv
OUTPUT_DIR=~/agent-output
STATE_DB=~/.local/share/agent-scheduler/state.db
LOG_FILE=~/.local/log/agent-scheduler.log

# Schedule backend: auto | cron | launchd
SCHEDULE_BACKEND=auto
```

| Variable | Default | Description |
|----------|---------|-------------|
| `GOOGLE_SHEET_ID` | *(none)* | The ID from your Google Sheet URL |
| `GOOGLE_SHEET_NAME` | `Sheet1` | Worksheet tab name |
| `TASKS_CSV` | `~/.local/share/agent-scheduler/tasks.csv` | Where the synced CSV is stored locally |
| `OUTPUT_DIR` | `~/agent-output` | Default output directory (used when a task has no `output_dir`) |
| `STATE_DB` | `~/.local/share/agent-scheduler/state.db` | SQLite database path |
| `LOG_FILE` | `~/.local/log/agent-scheduler.log` | Log file path |
| `SCHEDULE_BACKEND` | `auto` | `auto` (launchd on macOS, cron elsewhere), `cron`, or `launchd` |

You can also pass `--config/-c` to any command to use an alternate `.env` file.

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

Run `agent-scheduler validate` to check your configuration before going live. It verifies:

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

Fix the errors in the Google Sheet, run `agent-scheduler sync`, and validate again.
