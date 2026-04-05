"""launchd schedule backend for macOS."""

import plistlib
import subprocess
from pathlib import Path

LABEL = "com.agent-scheduler"
PLIST_PATH = Path("~/Library/LaunchAgents") / f"{LABEL}.plist"


def _plist_content(executable: str) -> dict:
    return {
        "Label": LABEL,
        "ProgramArguments": [executable, "run", "--no-sync"],
        "StartInterval": 1800,
        "WorkingDirectory": str(Path.home()),
        "EnvironmentVariables": {
            "PATH": "/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin",
        },
        "StandardOutPath": str(Path("~/.local/log/agent-scheduler-stdout.log").expanduser()),
        "StandardErrorPath": str(Path("~/.local/log/agent-scheduler-stderr.log").expanduser()),
    }


def install_launchd(executable: str = "agent-scheduler") -> None:
    plist_path = PLIST_PATH.expanduser()
    plist_path.parent.mkdir(parents=True, exist_ok=True)

    # Unload first if already loaded
    if plist_path.exists():
        subprocess.run(
            ["launchctl", "unload", "-w", str(plist_path)],
            capture_output=True,
        )

    content = _plist_content(executable)
    with open(plist_path, "wb") as f:
        plistlib.dump(content, f)

    # Create log directory
    Path("~/.local/log").expanduser().mkdir(parents=True, exist_ok=True)

    subprocess.run(
        ["launchctl", "load", "-w", str(plist_path)],
        check=True,
    )


def uninstall_launchd() -> None:
    plist_path = PLIST_PATH.expanduser()
    if plist_path.exists():
        subprocess.run(
            ["launchctl", "unload", "-w", str(plist_path)],
            capture_output=True,
        )
        plist_path.unlink()


def is_installed() -> bool:
    return PLIST_PATH.expanduser().exists()
