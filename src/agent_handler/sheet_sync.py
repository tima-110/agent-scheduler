"""Google Sheets sync via GAS Web App."""

import json
import shutil
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HEADER_COLUMNS = [
    "id", "enabled", "host", "cli", "model", "agent", "prompt",
    "project_dir", "schedule_type", "schedule_value", "order",
    "depends_on", "output_dir", "output_format", "output_filename",
    "cli_args",
]


def _get(gas_url: str, params: dict) -> dict:
    url = gas_url + "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"GAS request failed (HTTP {e.code}): {e.reason}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"GAS request failed: {e.reason}") from e


def _post(gas_url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        gas_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"GAS request failed (HTTP {e.code}): {e.reason}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"GAS request failed: {e.reason}") from e


def check_gas_available(gas_url: str) -> None:
    """Verify the GAS Web App URL is reachable and responding."""
    if not gas_url:
        raise RuntimeError(
            "gas_url is not set in config.toml. "
            "Deploy the GAS script and set gas_url under [sheets]."
        )
    try:
        _get(gas_url, {"action": "isSheetEmpty"})
    except RuntimeError as e:
        raise RuntimeError(f"GAS Web App is not reachable at {gas_url!r}: {e}") from e


def sync_sheet(gas_url: str, sheet_name: str, dest: Path) -> list[dict]:
    """Sync sheet to local JSON file. Returns list of row dicts."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    rows = _get(gas_url, {"action": "getTasks", "sheet": sheet_name})
    if isinstance(rows, dict) and "error" in rows:
        raise RuntimeError(f"GAS getTasks failed: {rows['error']}")
    if not isinstance(rows, list):
        raise RuntimeError(f"GAS getTasks returned unexpected response: {rows!r}")
    if len(rows) == 0:
        raise RuntimeError(
            "Sheet has no task rows — only a header or is empty. Add tasks to the sheet first."
        )
    tmp = dest.with_suffix(".tmp")
    tmp.write_text(json.dumps(rows, indent=2))
    shutil.move(str(tmp), str(dest))
    return rows


def is_sheet_empty(gas_url: str, sheet_name: str) -> bool:
    result = _get(gas_url, {"action": "isSheetEmpty", "sheet": sheet_name})
    if "error" in result:
        raise RuntimeError(f"GAS isSheetEmpty failed: {result['error']}")
    return result.get("empty", True)


def write_header_row(gas_url: str, api_key: str, sheet_name: str) -> None:
    result = _post(gas_url, {"apiKey": api_key, "action": "writeHeader", "sheet": sheet_name})
    if not result.get("success"):
        raise RuntimeError(f"GAS writeHeader failed: {result.get('error', 'unknown error')}")


def read_sheet_rows(gas_url: str, sheet_name: str) -> tuple[list[str], list[list[str]]]:
    """Read sheet and return (headers, data_rows). Each data_row is a list of strings."""
    rows = _get(gas_url, {"action": "getTasks", "sheet": sheet_name})
    if isinstance(rows, dict) and "error" in rows:
        raise RuntimeError(f"GAS getTasks failed: {rows['error']}")
    if not isinstance(rows, list) or len(rows) == 0:
        return [], []
    headers = list(rows[0].keys())
    data_rows = [[str(r.get(h, "")) for h in headers] for r in rows]
    return headers, data_rows


def find_row_number_by_id(gas_url: str, api_key: str, sheet_name: str, task_id: str) -> int | None:
    """Find 1-based row number for a task ID. Header is row 1, first data row is 2."""
    result = _post(gas_url, {
        "apiKey": api_key,
        "action": "findRowById",
        "sheet": sheet_name,
        "taskId": task_id,
    })
    if not result.get("success"):
        raise RuntimeError(f"GAS findRowById failed: {result.get('error', 'unknown error')}")
    return result.get("rowNumber")


def append_row(gas_url: str, api_key: str, sheet_name: str, values: list[str]) -> None:
    result = _post(gas_url, {
        "apiKey": api_key,
        "action": "appendRow",
        "sheet": sheet_name,
        "values": values,
    })
    if not result.get("success"):
        raise RuntimeError(f"GAS appendRow failed: {result.get('error', 'unknown error')}")


def update_row(gas_url: str, api_key: str, sheet_name: str, row_number: int, values: list[str]) -> None:
    """Update a specific row in the sheet. row_number is 1-based."""
    result = _post(gas_url, {
        "apiKey": api_key,
        "action": "updateRow",
        "sheet": sheet_name,
        "rowNumber": row_number,
        "values": values,
    })
    if not result.get("success"):
        raise RuntimeError(f"GAS updateRow failed: {result.get('error', 'unknown error')}")


def clear_row(gas_url: str, api_key: str, sheet_name: str, row_number: int) -> None:
    """Clear a specific row in the sheet. row_number is 1-based."""
    result = _post(gas_url, {
        "apiKey": api_key,
        "action": "clearRow",
        "sheet": sheet_name,
        "rowNumber": row_number,
    })
    if not result.get("success"):
        raise RuntimeError(f"GAS clearRow failed: {result.get('error', 'unknown error')}")


def write_sample_row(gas_url: str, api_key: str, sheet_name: str, cli: str, project_dir: str) -> None:
    values = [
        "example-task", "true", "", cli, "", "",
        "Summarize recent changes in this project",
        project_dir, "frequency", "1h", "1",
        "", "", "text", "{id}-{timestamp}.{ext}", "",
    ]
    append_row(gas_url, api_key, sheet_name, values)
