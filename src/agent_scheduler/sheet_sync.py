"""Google Sheets sync via gws CLI."""

import shutil
import subprocess
from pathlib import Path


def check_gws_available() -> None:
    if not shutil.which("gws"):
        raise RuntimeError("gws CLI not found on PATH. Install it first.")
    result = subprocess.run(
        ["gws", "auth", "status"], capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError("gws is not authorized. Run `gws auth login` first.")


def sync_sheet(sheet_id: str, worksheet_name: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            "gws", "sheets", "export",
            "--id", sheet_id,
            "--sheet", worksheet_name,
            "--format", "csv",
        ],
        capture_output=True, text=True, check=True,
    )
    tmp = dest.with_suffix(".tmp")
    tmp.write_text(result.stdout)
    shutil.move(str(tmp), str(dest))
