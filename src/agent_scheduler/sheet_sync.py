"""Google Sheets sync via gws CLI."""

import json
import shutil
import subprocess
from pathlib import Path

HEADER_COLUMNS = [
    "id", "enabled", "host", "cli", "model", "agent", "prompt",
    "project_dir", "schedule_type", "schedule_value", "order",
    "depends_on", "output_dir", "output_format", "output_filename",
    "cli_args",
]


def _run_gws(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(list(args), capture_output=True, text=True)


def _gws_error(result: subprocess.CompletedProcess) -> str:
    return (result.stderr or "").strip() or (result.stdout or "").strip()


def _parse_gws_response(stdout: str) -> dict:
    """Parse the JSON response from gws +read."""
    text = (stdout or "").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def check_gws_available() -> None:
    if not shutil.which("gws"):
        raise RuntimeError("gws CLI not found on PATH. Install it first.")
    result = _run_gws("gws", "auth", "status")
    if result.returncode != 0:
        raise RuntimeError("gws is not authorized. Run `gws auth login` first.")


def _read_sheet(sheet_id: str, worksheet_name: str) -> subprocess.CompletedProcess:
    return _run_gws(
        "gws", "sheets", "+read",
        "--spreadsheet", sheet_id,
        "--range", worksheet_name,
    )


def _rows_to_dicts(values: list[list[str]]) -> list[dict]:
    """Convert gws values array (header + rows) to list of dicts."""
    if len(values) < 2:
        return []
    headers = [h.strip() for h in values[0]]
    rows = []
    for row in values[1:]:
        # Pad short rows with empty strings
        padded = row + [""] * (len(headers) - len(row))
        rows.append(dict(zip(headers, padded)))
    return rows


def sync_sheet(sheet_id: str, worksheet_name: str, dest: Path) -> list[dict]:
    """Sync sheet to local JSON file. Returns list of row dicts."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    result = _read_sheet(sheet_id, worksheet_name)
    if result.returncode != 0:
        raise RuntimeError(f"gws sheet sync failed (exit {result.returncode}): {_gws_error(result)}")
    data = _parse_gws_response(result.stdout)
    values = data.get("values", [])
    if len(values) < 2:
        raise RuntimeError("Sheet has no task rows — only a header or is empty. Add tasks to the sheet first.")
    rows = _rows_to_dicts(values)
    tmp = dest.with_suffix(".tmp")
    tmp.write_text(json.dumps(rows, indent=2))
    shutil.move(str(tmp), str(dest))
    return rows


def is_sheet_empty(sheet_id: str, worksheet_name: str) -> bool:
    result = _read_sheet(sheet_id, worksheet_name)
    if result.returncode != 0:
        raise RuntimeError(f"gws sheet read failed (exit {result.returncode}): {_gws_error(result)}")
    data = _parse_gws_response(result.stdout)
    return "values" not in data


def write_header_row(sheet_id: str) -> None:
    row = json.dumps([HEADER_COLUMNS])
    result = _run_gws(
        "gws", "sheets", "+append",
        "--spreadsheet", sheet_id,
        "--json-values", row,
    )
    if result.returncode != 0:
        raise RuntimeError(f"gws header write failed (exit {result.returncode}): {_gws_error(result)}")
