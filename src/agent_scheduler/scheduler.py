"""Orchestrator: filter, sort, execute task batches."""

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from graphlib import TopologicalSorter
from pathlib import Path

from rich.console import Console

from .agents import get_runner
from .config import ScheduleType, TaskEntry
from .state import get_last_run, record_run

console = Console()


def parse_interval(value: str) -> timedelta:
    m = re.fullmatch(r"(\d+)\s*(h|m)", value.strip(), re.IGNORECASE)
    if not m:
        raise ValueError(f"Invalid frequency: {value!r}. Expected format like '1h' or '30m'.")
    amount, unit = int(m.group(1)), m.group(2).lower()
    return timedelta(hours=amount) if unit == "h" else timedelta(minutes=amount)


def parse_hhmm(value: str, date) -> datetime:
    h, m = value.strip().split(":")
    return datetime.combine(date, datetime.strptime(f"{h}:{m}", "%H:%M").time())


def is_due(task: TaskEntry, now: datetime, *, db_path: Path, hostname: str) -> bool:
    last = get_last_run(task.id, db_path=db_path, hostname=hostname)
    if task.schedule_type == ScheduleType.frequency:
        interval = parse_interval(task.schedule_value)
        return last is None or (now - last) >= interval
    else:
        target = parse_hhmm(task.schedule_value, now.date())
        window_start = last or (now - timedelta(minutes=30))
        return window_start < target <= now


def topological_batches(tasks: list[TaskEntry]) -> list[list[TaskEntry]]:
    task_map = {t.id: t for t in tasks}
    graph = {}
    for t in tasks:
        deps = [d for d in t.depends_on if d in task_map]
        graph[t.id] = set(deps)

    sorter = TopologicalSorter(graph)
    sorter.prepare()
    batches = []
    while sorter.is_active():
        ready = sorter.get_ready()
        batch = [task_map[tid] for tid in ready]
        batch.sort(key=lambda t: t.order)
        batches.append(batch)
        for tid in ready:
            sorter.done(tid)
    return batches


def run_pass(
    tasks: list[TaskEntry],
    *,
    dry_run: bool = False,
    db_path: Path,
    hostname: str,
    output_dir: Path,
) -> dict[str, str]:
    now = datetime.now()
    results: dict[str, str] = {}

    eligible = [t for t in tasks if t.enabled and t.runs_on_this_host(hostname)]
    due = [t for t in eligible if is_due(t, now, db_path=db_path, hostname=hostname)]

    if not due:
        console.print("[dim]No tasks due.[/dim]")
        return results

    batches = topological_batches(due)
    failed: set[str] = set()

    for batch in batches:
        runnable = []
        for task in batch:
            if any(dep in failed for dep in task.depends_on):
                failed.add(task.id)
                results[task.id] = "skipped"
                record_run(task.id, "skipped", None, "upstream failed", db_path=db_path, hostname=hostname)
                console.print(f"[yellow]SKIPPED[/yellow] {task.id} (upstream failed)")
            else:
                runnable.append(task)

        if not runnable:
            continue

        if dry_run:
            for task in runnable:
                runner = get_runner(task.cli)
                cmd = runner.full_command(task)
                console.print(f"[cyan]\\[DRY RUN][/cyan] {task.id}: {' '.join(cmd)}")
                results[task.id] = "dry_run"
            continue

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {}
            for task in runnable:
                runner = get_runner(task.cli)
                futures[pool.submit(runner.run, task, output_dir, hostname)] = task

            for future in futures:
                task = futures[future]
                result = future.result()
                results[task.id] = result.status
                if result.exit_code != 0:
                    failed.add(task.id)
                record_run(
                    task.id, result.status, result.exit_code, result.error_msg,
                    db_path=db_path, hostname=hostname,
                )
                style = "[green]SUCCESS[/green]" if result.status == "success" else "[red]FAILED[/red]"
                console.print(f"{style} {task.id}")

    return results
