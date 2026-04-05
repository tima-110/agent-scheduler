"""CLI application — typer app with all subcommands."""

from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from .config import AppConfig, load_tasks
from .schedule import install_schedule, uninstall_schedule
from .scheduler import run_pass
from .sheet_sync import check_gws_available, sync_sheet
from .state import get_last_run, get_task_runs, init_db
from .validate import print_validation

load_dotenv()

app = typer.Typer(name="agent-scheduler", help="Scheduled execution of AI coding agent CLIs.")
console = Console()


def _get_config(config_path: Optional[Path] = None) -> AppConfig:
    if config_path:
        cfg = AppConfig(_env_file=str(config_path))
    else:
        cfg = AppConfig()
    return cfg.resolve_paths()


@app.command()
def sync(
    config: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to .env config file"),
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

    if not no_sync:
        try:
            sync_sheet(cfg.google_sheet_id, cfg.google_sheet_name, csv_file)
        except Exception as e:
            console.print(f"[yellow]Sync failed, using local CSV: {e}[/yellow]")

    init_db(cfg.state_db)
    tasks = load_tasks(csv_file)
    run_pass(tasks, dry_run=dry_run, db_path=cfg.state_db, output_dir=cfg.output_dir)


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
        if not t.runs_on_this_host():
            continue
        runs = get_task_runs(t.id, db_path=cfg.state_db)
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
        if not t.runs_on_this_host():
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
