"""Task configuration validation."""
from __future__ import annotations

from graphlib import CycleError, TopologicalSorter

from rich.console import Console

from .config import TaskEntry

console = Console()


def validate_tasks(tasks: list[TaskEntry]) -> list[str]:
    errors: list[str] = []

    # Unique IDs
    ids = [t.id for t in tasks]
    seen = set()
    for tid in ids:
        if tid in seen:
            errors.append(f"Duplicate task ID: {tid!r}")
        seen.add(tid)

    id_set = set(ids)

    # depends_on references exist
    for t in tasks:
        for dep in t.depends_on:
            if dep not in id_set:
                errors.append(f"Task {t.id!r} depends on unknown task {dep!r}")

    # Cycle detection
    graph = {t.id: set(t.depends_on) for t in tasks}
    try:
        sorter = TopologicalSorter(graph)
        sorter.prepare()
    except CycleError as e:
        errors.append(f"Circular dependency detected: {e}")

    # project_dir existence
    for t in tasks:
        if not t.project_dir.exists():
            errors.append(f"Task {t.id!r}: project_dir does not exist: {t.project_dir}")

    return errors


def print_validation(tasks: list[TaskEntry]) -> bool:
    errors = validate_tasks(tasks)
    if errors:
        console.print(f"[red]Validation failed with {len(errors)} error(s):[/red]")
        for err in errors:
            console.print(f"  [red]x[/red] {err}")
        return False
    console.print("[green]All checks passed.[/green]")
    return True
