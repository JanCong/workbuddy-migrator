from __future__ import annotations

import sqlite3
from pathlib import Path

from .models import SchemaInfo


def connect_readonly(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{db_path.as_posix()}?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    return con


def connect_writable(db_path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    return con


def inspect_schema(con: sqlite3.Connection) -> SchemaInfo:
    tables = [row["name"] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    columns: dict[str, list[str]] = {}
    for table in tables:
        rows = con.execute(f"PRAGMA table_info({table})").fetchall()
        columns[table] = [row["name"] for row in rows]
    return SchemaInfo(tables=columns)
