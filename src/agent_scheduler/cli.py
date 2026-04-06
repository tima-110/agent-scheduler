"""CLI application — typer app with all subcommands."""

import socket
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from .config import AppConfig, default_config_path, load_config, load_tasks
from .schedule import install_schedule, uninstall_schedule
from .scheduler import run_pass
from .sheet_sync import check_gws_available, is_sheet_empty, sync_sheet, write_header_row
from .state import get_task_runs, init_db
from .validate import print_validation

app = typer.Typer(name="agent-scheduler", help="Scheduled execution of AI coding agent CLIs.")
console = Console()


def _get_config(config_path: Optional[Path] = None) -> AppConfig:
    cfg = load_config(config_path)
    return cfg.resolve_paths()


@app.command()
def sync(
    config: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to config.toml"),
):
    """Pull Google Sheet to local tasks CSV."""
    cfg = _get_config(config)
    check_gws_available()
    sync_sheet(cfg.google_sheet_id, cfg.google_sheet_name, cfg.tasks_csv)
    console.print(f"[green]Synced to {cfg.tasks_csv}[/green]")


@app.command()
def run(
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    csv_path: Optional[Path] = typer.Option(None, "--csv", "-f", help="Path to tasks CSV"),
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
            sync_sheet(cfg.google_sheet_id, cfg.google_sheet_name, csv_file)
        except Exception as e:
            console.print(f"[yellow]Sync failed, using local CSV: {e}[/yellow]")

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
    check_gws_available()
    init_db(cfg.state_db)

    import shutil
    executable = shutil.which("agent-scheduler") or "agent-scheduler"
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
    """Interactive guided setup — create config, verify gws, test sheet connectivity."""
    config_path = default_config_path()
    console.print(f"\n[bold]agent-scheduler init[/bold]")
    console.print(f"Config location: [cyan]{config_path}[/cyan]\n")

    # Check for existing config
    if config_path.exists():
        overwrite = typer.confirm("Config file already exists. Overwrite?", default=False)
        if not overwrite:
            console.print("Keeping existing config.")
            raise typer.Exit()

    # Prompt for settings
    console.print("[dim]Tip: Find the Sheet ID in the URL between /d/ and /edit[/dim]")
    sheet_id = typer.prompt("Google Sheet ID")
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
    lines.append(f'id = "{sheet_id}"')
    lines.append(f'name = "{sheet_name}"')
    config_path.write_text("\n".join(lines) + "\n")
    console.print(f"\n[green]Config written to {config_path}[/green]")

    # Load the config we just wrote
    cfg = load_config(config_path).resolve_paths()
    resolved_hostname = cfg.get_hostname()
    console.print(f"Hostname: [bold]{resolved_hostname}[/bold]")

    # Verify gws
    console.print("\n[bold]Checking gws CLI...[/bold]")
    try:
        check_gws_available()
        console.print("[green]gws is installed and authorized.[/green]")
    except RuntimeError as e:
        console.print(f"[yellow]{e}[/yellow]")
        console.print("[yellow]You can still configure tasks, but sync/run will fail until gws is set up.[/yellow]")
        init_db(cfg.state_db)
        console.print(f"\n[green]Setup complete.[/green] Run [bold]gws auth login[/bold], then [bold]agent-scheduler sync[/bold].")
        return

    # Test sheet connectivity
    console.print("\n[bold]Testing sheet connectivity...[/bold]")
    task_count = 0
    try:
        empty = is_sheet_empty(cfg.google_sheet_id, cfg.google_sheet_name)
        if empty:
            console.print("[yellow]Sheet is empty — no header row found.[/yellow]")
            if typer.confirm("Write the header row now?", default=True):
                write_header_row(cfg.google_sheet_id)
                console.print("[green]Header row written.[/green]")
            else:
                console.print("Skipped. Add the header row manually or run [bold]agent-scheduler setup-sheet[/bold].")
        else:
            sync_sheet(cfg.google_sheet_id, cfg.google_sheet_name, cfg.tasks_csv)
            tasks = load_tasks(cfg.tasks_csv)
            task_count = len(tasks)
            console.print(f"[green]Synced {task_count} task(s) from the sheet.[/green]")
    except Exception as e:
        console.print(f"[red]Sheet access failed: {e}[/red]")
        console.print("[yellow]Check your Sheet ID and worksheet name, then try [bold]agent-scheduler sync[/bold].[/yellow]")
        init_db(cfg.state_db)
        return

    # Init state DB
    init_db(cfg.state_db)

    # Summary
    console.print(f"\n[bold green]Setup complete![/bold green]")
    console.print(f"  Config:   {config_path}")
    console.print(f"  Hostname: {resolved_hostname}")
    console.print(f"  Tasks:    {task_count} found")
    console.print(f"  CSV:      {cfg.tasks_csv}")
    console.print(f"  State DB: {cfg.state_db}")
    console.print(f"\nNext steps:")
    console.print(f"  agent-scheduler list       — view tasks for this host")
    console.print(f"  agent-scheduler validate   — check for config errors")
    console.print(f"  agent-scheduler run --dry-run — preview execution")
    console.print(f"  agent-scheduler install    — set up the 30-min schedule")


@app.command(name="setup-sheet")
def setup_sheet(
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
):
    """Write the header row to an empty Google Sheet."""
    cfg = _get_config(config)
    check_gws_available()

    try:
        empty = is_sheet_empty(cfg.google_sheet_id, cfg.google_sheet_name)
    except Exception as e:
        console.print(f"[red]Could not read sheet: {e}[/red]")
        raise typer.Exit(code=1)

    if not empty:
        console.print("[yellow]Sheet already has data. Header row not written.[/yellow]")
        console.print("To avoid duplicating headers, clear the sheet first if you want to reset it.")
        raise typer.Exit(code=1)

    write_header_row(cfg.google_sheet_id)
    console.print("[green]Header row written to the sheet.[/green]")
