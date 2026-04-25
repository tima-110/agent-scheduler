"""Output file writing."""

from datetime import datetime
from pathlib import Path

from ..config import TaskEntry


def write_output(raw_stdout: str, task: TaskEntry, global_output_dir: Path, hostname: str) -> Path:
    dest = (task.output_dir or global_output_dir).expanduser()
    dest.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    ext = {"text": "txt", "json": "json", "markdown": "md", "stream-json": "jsonl"}[task.output_format.value]
    filename = task.output_filename.format(id=task.id, timestamp=timestamp, ext=ext)

    path = dest / filename
    path.write_text(raw_stdout)
    return path
