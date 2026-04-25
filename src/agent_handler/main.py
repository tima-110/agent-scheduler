"""Entry point for agent-handler."""
from __future__ import annotations

import sys


def main() -> None:
    try:
        from agent_handler.cli import app
    except PermissionError:
        print("Error: cannot access current directory.", file=sys.stderr)
        sys.exit(1)
    app()
