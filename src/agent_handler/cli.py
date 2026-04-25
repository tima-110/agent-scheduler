"""CLI application — typer app with all subcommands."""

import socket
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from .config import AppConfig, CLIChoice, OutputFormat, ScheduleType, default_config_path, load_config, load_tasks
from .schedule import install_schedule, uninstall_schedule
from .scheduler import run_pass
from .sheet_sync import (
    HEADER_COLUMNS,
    append_row,
    check_gas_available,
    clear_row,
    find_row_number_by_id,
    is_sheet_empty,
    read_sheet_rows,
    sync_sheet,
    update_row,
    write_header_row,
    write_sample_row,
)
from .state import get_task_runs, init_db
from .validate import print_validation

app = typer.Typer(name="agent-handler", help="Scheduled execution of AI coding agent CLIs.")
task_app = typer.Typer(help="Manage task rows in the Google Sheet.")
app.add_typer(task_app, name="task")
console = Console()


def _get_config(config_path: Optional[Path] = None) -> AppConfig:
    cfg = load_config(config_path)
    return cfg.resolve_paths()


@app.command()
def sync(
    config: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to config.toml"),
):
    """Pull Google Sheet to local tasks JSON."""
    cfg = _get_config(config)
    sync_sheet(cfg.gas_url, cfg.google_sheet_name, cfg.tasks_csv)
    console.print(f"[green]Synced to {cfg.tasks_csv}[/green]")


@app.command()
def run(
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    csv_path: Optional[Path] = typer.Option(None, "--csv", "-f", help="Path to tasks JSON"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions without executing"),
    no_sync: bool = typer.Option(False, "--no-sync", help="Skip Google Sheet sync"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Execute one full scheduling pass."""
    cfg = _get_config(config)
    csv_file = csv_path or cfg.tasks_csv
    hostname = cfg.get_hostname()

    if not no_sync:
        try:
            sync_sheet(cfg.gas_url, cfg.google_sheet_name, csv_file)
        except Exception as e:
            console.print(f"[yellow]Sync failed, using local tasks file: {e}[/yellow]")

    init_db(cfg.state_db)
    tasks = load_tasks(csv_file)
    run_pass(tasks, dry_run=dry_run, db_path=cfg.state_db, hostname=hostname, output_dir=cfg.output_dir)


@app.command()
def install(
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    backend: str = typer.Option("auto", "--backend", help="Schedule backend: auto, cron, launchd"),
):
    """Verify prerequisites and install the 30-min orchestrator schedule entry."""
    cfg = _get_config(config)
    init_db(cfg.state_db)

    import shutil
    executable = shutil.which("agent-handler") or "agent-handler"
    install_schedule(backend=backend or cfg.schedule_backend, executable=executable)
    console.print("[green]Schedule installed.[/green]")


@app.command()
def uninstall(
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    backend: str = typer.Option("auto", "--backend", help="Schedule backend: auto, cron, launchd"),
):
    """Remove the orchestrator schedule entry."""
    cfg = _get_config(config)
    uninstall_schedule(backend=backend or cfg.schedule_backend)
    console.print("[green]Schedule removed.[/green]")


@app.command()
def status(
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    csv_path: Optional[Path] = typer.Option(None, "--csv", "-f"),
):
    """Show schedule entry status and last run per task."""
    cfg = _get_config(config)
    csv_file = csv_path or cfg.tasks_csv
    hostname = cfg.get_hostname()

    from .schedule.cron import is_installed as cron_installed
    from .schedule.launchd import is_installed as launchd_installed

    if launchd_installed():
        console.print("[green]launchd[/green] schedule is active")
    elif cron_installed():
        console.print("[green]cron[/green] schedule is active")
    else:
        console.print("[yellow]No schedule installed[/yellow]")

    init_db(cfg.state_db)
    tasks = load_tasks(csv_file)

    table = Table(title="Last Run Status")
    table.add_column("Task ID")
    table.add_column("Enabled")
    table.add_column("Last Run")
    table.add_column("Status")

    for t in tasks:
        if not t.runs_on_this_host(hostname):
            continue
        runs = get_task_runs(t.id, db_path=cfg.state_db, hostname=hostname)
        if runs:
            last = runs[0]
            table.add_row(t.id, str(t.enabled), last["ran_at"], last["status"])
        else:
            table.add_row(t.id, str(t.enabled), "—", "—")

    console.print(table)


@app.command(name="list")
def list_tasks(
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    csv_path: Optional[Path] = typer.Option(None, "--csv", "-f"),
):
    """Show a rich table of tasks applicable to this host."""
    cfg = _get_config(config)
    csv_file = csv_path or cfg.tasks_csv
    hostname = cfg.get_hostname()

    tasks = load_tasks(csv_file)

    table = Table(title="Tasks for this host")
    table.add_column("ID")
    table.add_column("CLI")
    table.add_column("Model")
    table.add_column("Schedule")
    table.add_column("Order")
    table.add_column("Depends On")
    table.add_column("Enabled")

    for t in tasks:
        if not t.runs_on_this_host(hostname):
            continue
        sched = f"{t.schedule_type.value}: {t.schedule_value}"
        deps = ", ".join(t.depends_on) if t.depends_on else "—"
        table.add_row(t.id, t.cli.value, t.model, sched, str(t.order), deps, str(t.enabled))

    console.print(table)


@app.command()
def validate(
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    csv_path: Optional[Path] = typer.Option(None, "--csv", "-f"),
):
    """Validate task configuration: unique IDs, dependency refs, cycles, paths."""
    cfg = _get_config(config)
    csv_file = csv_path or cfg.tasks_csv
    tasks = load_tasks(csv_file)
    ok = print_validation(tasks)
    if not ok:
        raise typer.Exit(code=1)


@app.command()
def whoami(
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
):
    """Print the hostname used for task filtering."""
    cfg = _get_config(config)
    resolved = cfg.get_hostname()
    system = socket.gethostname()

    if cfg.hostname:
        console.print(f"Hostname:        [bold]{resolved}[/bold] (from config)")
        console.print(f"System hostname: {system}")
    else:
        console.print(f"Hostname: [bold]{resolved}[/bold] (system default)")
    console.print(f"\nUse this value in the [bold]host[/bold] column of your Google Sheet.")


@app.command()
def init():
    """Interactive guided setup — create config, verify GAS endpoint, test sheet connectivity."""
    config_path = default_config_path()
    console.print(f"\n[bold]agent-handler init[/bold]")
    console.print(f"Config location: [cyan]{config_path}[/cyan]\n")

    # Check for existing config
    if config_path.exists():
        overwrite = typer.confirm("Config file already exists. Overwrite?", default=False)
        if not overwrite:
            console.print("Keeping existing config.")
            raise typer.Exit()

    # Prompt for settings
    console.print("[dim]Tip: Deploy docs/gas-script.js from your Google Sheet (Extensions → Apps Script)[/dim]")
    gas_url = typer.prompt("GAS Web App URL")
    gas_api_key = typer.prompt("GAS API key", hide_input=True)
    sheet_name = typer.prompt("Worksheet name", default="Sheet1")

    system_hostname = socket.gethostname()
    console.print(f"\nSystem hostname: [bold]{system_hostname}[/bold]")
    use_alias = typer.confirm("Set a friendly hostname alias?", default=False)
    hostname_alias = None
    if use_alias:
        hostname_alias = typer.prompt("Hostname alias")

    # Write config
    config_path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    if hostname_alias:
        lines.append(f'hostname = "{hostname_alias}"')
        lines.append("")
    lines.append("[sheets]")
    lines.append(f'gas_url = "{gas_url}"')
    lines.append(f'gas_api_key = "{gas_api_key}"')
    lines.append(f'name = "{sheet_name}"')
    config_path.write_text("\n".join(lines) + "\n")
    console.print(f"\n[green]Config written to {config_path}[/green]")

    # Load the config we just wrote
    cfg = load_config(config_path).resolve_paths()
    resolved_hostname = cfg.get_hostname()
    console.print(f"Hostname: [bold]{resolved_hostname}[/bold]")

    # Verify GAS endpoint
    console.print("\n[bold]Checking GAS Web App...[/bold]")
    try:
        check_gas_available(cfg.gas_url)
        console.print("[green]GAS Web App is reachable.[/green]")
    except RuntimeError as e:
        console.print(f"[yellow]{e}[/yellow]")
        console.print("[yellow]You can still configure tasks, but sync/run will fail until the GAS endpoint is reachable.[/yellow]")
        init_db(cfg.state_db)
        console.print(f"\n[green]Setup complete.[/green] Fix the GAS URL, then run [bold]agent-handler sync[/bold].")
        return

    # Test sheet connectivity
    console.print("\n[bold]Testing sheet connectivity...[/bold]")
    task_count = 0
    try:
        empty = is_sheet_empty(cfg.gas_url, cfg.google_sheet_name)
        if empty:
            console.print("[yellow]Sheet is empty — no header row found.[/yellow]")
            if typer.confirm("Write the header row now?", default=True):
                write_header_row(cfg.gas_url, cfg.gas_api_key, cfg.google_sheet_name)
                console.print("[green]Header row written.[/green]")
                if typer.confirm("Add a sample task row as a template?", default=True):
                    cli_choice = typer.prompt(
                        "Which CLI will you use?",
                        type=typer.Choice(["claude-code", "codex", "gemini", "opencode"]),
                        default="claude-code",
                    )
                    project_dir = typer.prompt("Project directory", default="~/projects/example")
                    write_sample_row(cfg.gas_url, cfg.gas_api_key, cfg.google_sheet_name, cli_choice, project_dir)
                    console.print("[green]Sample task row written.[/green]")
            else:
                console.print("Skipped. Add the header row manually or run [bold]agent-handler setup-sheet[/bold].")
        else:
            sync_sheet(cfg.gas_url, cfg.google_sheet_name, cfg.tasks_csv)
            tasks = load_tasks(cfg.tasks_csv)
            task_count = len(tasks)
            console.print(f"[green]Synced {task_count} task(s) from the sheet.[/green]")
    except Exception as e:
        console.print(f"[red]Sheet access failed: {e}[/red]")
        console.print("[yellow]Check your GAS URL and worksheet name, then try [bold]agent-handler sync[/bold].[/yellow]")
        init_db(cfg.state_db)
        return

    # Init state DB
    init_db(cfg.state_db)

    # Summary
    console.print(f"\n[bold green]Setup complete![/bold green]")
    console.print(f"  Config:   {config_path}")
    console.print(f"  Hostname: {resolved_hostname}")
    console.print(f"  Tasks:    {task_count} found")
    console.print(f"  JSON:     {cfg.tasks_csv}")
    console.print(f"  State DB: {cfg.state_db}")
    console.print(f"\nNext steps:")
    console.print(f"  agent-handler list       — view tasks for this host")
    console.print(f"  agent-handler validate   — check for config errors")
    console.print(f"  agent-handler run --dry-run — preview execution")
    console.print(f"  agent-handler install    — set up the 30-min schedule")


@app.command(name="setup-sheet")
def setup_sheet(
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
):
    """Write the header row to an empty Google Sheet."""
    cfg = _get_config(config)

    try:
        empty = is_sheet_empty(cfg.gas_url, cfg.google_sheet_name)
    except Exception as e:
        console.print(f"[red]Could not read sheet: {e}[/red]")
        raise typer.Exit(code=1)

    if not empty:
        console.print("[yellow]Sheet already has data. Header row not written.[/yellow]")
        console.print("To avoid duplicating headers, clear the sheet first if you want to reset it.")
        raise typer.Exit(code=1)

    write_header_row(cfg.gas_url, cfg.gas_api_key, cfg.google_sheet_name)
    console.print("[green]Header row written to the sheet.[/green]")


# --- Task management subcommands ---

def _prompt_task_fields(defaults: dict | None = None) -> list[str]:
    """Prompt for each task field interactively. Returns a row as list of strings."""
    d = defaults or {}
    task_id = typer.prompt("Task ID", default=d.get("id", ""))
    enabled = typer.prompt("Enabled", default=d.get("enabled", "true"))
    host = typer.prompt("Host (comma-separated, blank=all)", default=d.get("host", ""))
    cli = typer.prompt(
        "CLI",
        type=typer.Choice([c.value for c in CLIChoice]),
        default=d.get("cli", "claude-code"),
    )
    model = typer.prompt("Model (blank=CLI default)", default=d.get("model", ""))
    agent = typer.prompt("Agent (blank=none)", default=d.get("agent", ""))
    prompt = typer.prompt("Prompt", default=d.get("prompt", ""))
    project_dir = typer.prompt("Project directory", default=d.get("project_dir", "~/projects/example"))
    schedule_type = typer.prompt(
        "Schedule type",
        type=typer.Choice([s.value for s in ScheduleType]),
        default=d.get("schedule_type", "frequency"),
    )
    schedule_value = typer.prompt("Schedule value", default=d.get("schedule_value", "1h"))
    order = typer.prompt("Order", default=d.get("order", "0"))
    depends_on = typer.prompt("Depends on (comma-separated IDs)", default=d.get("depends_on", ""))
    output_dir = typer.prompt("Output directory (blank=global default)", default=d.get("output_dir", ""))
    output_format = typer.prompt(
        "Output format",
        type=typer.Choice([f.value for f in OutputFormat]),
        default=d.get("output_format", "text"),
    )
    output_filename = typer.prompt("Output filename template", default=d.get("output_filename", "{id}-{timestamp}.{ext}"))
    cli_args = typer.prompt("Extra CLI args", default=d.get("cli_args", ""))

    return [
        task_id, enabled, host, cli, model, agent, prompt,
        project_dir, schedule_type, schedule_value, order,
        depends_on, output_dir, output_format, output_filename, cli_args,
    ]


@task_app.command(name="add")
def task_add(
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
):
    """Add a new task row to the Google Sheet."""
    cfg = _get_config(config)

    console.print("\n[bold]Add a new task[/bold]\n")
    values = _prompt_task_fields()
    task_id = values[0]

    # Check for duplicate ID
    headers, rows = read_sheet_rows(cfg.gas_url, cfg.google_sheet_name)
    if headers:
        id_idx = headers.index("id") if "id" in headers else 0
        existing_ids = [r[id_idx].strip() for r in rows if len(r) > id_idx]
        if task_id in existing_ids:
            console.print(f"[red]Task ID '{task_id}' already exists.[/red]")
            raise typer.Exit(code=1)

    append_row(cfg.gas_url, cfg.gas_api_key, cfg.google_sheet_name, values)
    console.print(f"[green]Task '{task_id}' added to the sheet.[/green]")


@task_app.command(name="edit")
def task_edit(
    task_id: str = typer.Argument(help="ID of the task to edit"),
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
):
    """Edit an existing task row in the Google Sheet."""
    cfg = _get_config(config)

    row_num = find_row_number_by_id(cfg.gas_url, cfg.gas_api_key, cfg.google_sheet_name, task_id)
    if row_num is None:
        console.print(f"[red]Task '{task_id}' not found in the sheet.[/red]")
        raise typer.Exit(code=1)

    # Get current values
    headers, rows = read_sheet_rows(cfg.gas_url, cfg.google_sheet_name)
    current_row = rows[row_num - 2]  # -2: header offset + 0-indexing
    padded = current_row + [""] * (len(headers) - len(current_row))
    current = dict(zip(headers, padded))

    console.print(f"\n[bold]Editing task '{task_id}'[/bold]")
    console.print("[dim]Press Enter to keep current value.[/dim]\n")
    values = _prompt_task_fields(defaults=current)

    update_row(cfg.gas_url, cfg.gas_api_key, cfg.google_sheet_name, row_num, values)
    console.print(f"[green]Task '{task_id}' updated.[/green]")


@task_app.command(name="remove")
def task_remove(
    task_id: str = typer.Argument(help="ID of the task to remove"),
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
):
    """Remove a task row from the Google Sheet."""
    cfg = _get_config(config)

    row_num = find_row_number_by_id(cfg.gas_url, cfg.gas_api_key, cfg.google_sheet_name, task_id)
    if row_num is None:
        console.print(f"[red]Task '{task_id}' not found in the sheet.[/red]")
        raise typer.Exit(code=1)

    if not typer.confirm(f"Remove task '{task_id}' (row {row_num})?", default=False):
        console.print("Cancelled.")
        raise typer.Exit()

    clear_row(cfg.gas_url, cfg.gas_api_key, cfg.google_sheet_name, row_num)
    console.print(f"[green]Task '{task_id}' removed from the sheet.[/green]")
