"""SQLite run state management."""

import socket
import sqlite3
from datetime import datetime
from pathlib import Path

_DEFAULT_DB = Path("~/.local/share/agent-scheduler/state.db")


def _connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = (db_path or _DEFAULT_DB).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(str(path))


def init_db(db_path: Path | None = None) -> None:
    with _connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                task_id     TEXT    NOT NULL,
                host        TEXT    NOT NULL,
                ran_at      TEXT    NOT NULL,
                status      TEXT    NOT NULL,
                exit_code   INTEGER,
                error_msg   TEXT,
                PRIMARY KEY (task_id, host, ran_at)
            )
        """)


def get_last_run(task_id: str, db_path: Path | None = None) -> datetime | None:
    hostname = socket.gethostname()
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT ran_at FROM runs WHERE task_id = ? AND host = ? ORDER BY ran_at DESC LIMIT 1",
            (task_id, hostname),
        ).fetchone()
    if row:
        return datetime.fromisoformat(row[0])
    return None


def record_run(
    task_id: str,
    status: str,
    exit_code: int | None = None,
    error_msg: str = "",
    db_path: Path | None = None,
) -> None:
    hostname = socket.gethostname()
    now = datetime.now().isoformat()
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO runs (task_id, host, ran_at, status, exit_code, error_msg) VALUES (?, ?, ?, ?, ?, ?)",
            (task_id, hostname, now, status, exit_code, error_msg),
        )


def get_all_runs(db_path: Path | None = None) -> list[dict]:
    hostname = socket.gethostname()
    with _connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT task_id, ran_at, status, exit_code, error_msg FROM runs WHERE host = ? ORDER BY ran_at DESC",
            (hostname,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_task_runs(task_id: str, db_path: Path | None = None) -> list[dict]:
    hostname = socket.gethostname()
    with _connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT ran_at, status, exit_code, error_msg FROM runs WHERE task_id = ? AND host = ? ORDER BY ran_at DESC",
            (task_id, hostname),
        ).fetchall()
    return [dict(r) for r in rows]
