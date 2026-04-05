"""Output formatting and file writing."""

import json
import socket
from datetime import datetime
from pathlib import Path

from ..config import TaskEntry


def write_output(raw_stdout: str, task: TaskEntry, global_output_dir: Path) -> Path:
    dest = (task.output_dir or global_output_dir).expanduser()
    dest.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    ext = {"text": "txt", "json": "json", "markdown": "md"}[task.output_format.value]
    filename = task.output_filename.format(id=task.id, timestamp=timestamp, ext=ext)

    content = {
        "text": raw_stdout,
        "markdown": f"# {task.id} — {timestamp}\n\n{raw_stdout}",
        "json": json.dumps(
            {
                "task_id": task.id,
                "host": socket.gethostname(),
                "ran_at": timestamp,
                "output": raw_stdout,
            },
            indent=2,
        ),
    }[task.output_format.value]

    path = dest / filename
    path.write_text(content)
    return path
