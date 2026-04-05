"""Schedule backend management."""

import platform
from pathlib import Path

from .cron import install_cron, uninstall_cron
from .launchd import install_launchd, uninstall_launchd


def detect_backend() -> str:
    if platform.system() == "Darwin":
        return "launchd"
    return "cron"


def install_schedule(backend: str = "auto", executable: str = "agent-scheduler"):
    if backend == "auto":
        backend = detect_backend()
    if backend == "launchd":
        install_launchd(executable)
    else:
        install_cron(executable)


def uninstall_schedule(backend: str = "auto"):
    if backend == "auto":
        backend = detect_backend()
    if backend == "launchd":
        uninstall_launchd()
    else:
        uninstall_cron()
