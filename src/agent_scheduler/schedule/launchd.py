"""launchd schedule backend for macOS."""

import plistlib
import subprocess
from pathlib import Path

import platformdirs

LABEL = "com.agent-scheduler"
PLIST_PATH = Path("~/Library/LaunchAgents") / f"{LABEL}.plist"


def _log_dir() -> Path:
    return Path(platformdirs.user_log_dir("agent-scheduler"))


def _plist_content(executable: str) -> dict:
    log_dir = _log_dir()
    return {
        "Label": LABEL,
        "ProgramArguments": [executable, "run", "--no-sync"],
        "StartInterval": 1800,
        "WorkingDirectory": str(Path.home()),
        "EnvironmentVariables": {
            "PATH": "/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin",
        },
        "StandardOutPath": str(log_dir / "stdout.log"),
        "StandardErrorPath": str(log_dir / "stderr.log"),
    }


def install_launchd(executable: str = "agent-scheduler") -> None:
    plist_path = PLIST_PATH.expanduser()
    plist_path.parent.mkdir(parents=True, exist_ok=True)

    if plist_path.exists():
        subprocess.run(
            ["launchctl", "unload", "-w", str(plist_path)],
            capture_output=True,
        )

    content = _plist_content(executable)
    with open(plist_path, "wb") as f:
        plistlib.dump(content, f)

    _log_dir().mkdir(parents=True, exist_ok=True)

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
