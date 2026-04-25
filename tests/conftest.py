"""Shared test fixtures."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


@pytest.fixture
def tmp_config(tmp_path: Path) -> Path:
    cfg = tmp_path / "config.toml"
    cfg.write_text('[sheets]\ngas_url = "https://example.com/exec"\nname = "Sheet1"\n')
    return cfg


@pytest.fixture
def memory_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn
