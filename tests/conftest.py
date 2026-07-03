from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest


@pytest.fixture
def workbuddy_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "workbuddy-home"
    root.mkdir()
    (root / "projects").mkdir()
    (root / "memory").mkdir()
    (root / "memery").mkdir()
    (root / "connectors").mkdir()
    monkeypatch.setenv("WORKBUDDY_HOME", str(root))
    return root


def create_db(root: Path, with_automation_owner: bool = True) -> Path:
    db = root / "workbuddy.db"
    con = sqlite3.connect(db)
    try:
        con.execute("CREATE TABLE sessions (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, title TEXT)")
        if with_automation_owner:
            con.execute(
                "CREATE TABLE automations (id TEXT PRIMARY KEY, owner_user_id TEXT, owner_status TEXT, owner_source TEXT)"
            )
        else:
            con.execute("CREATE TABLE automations (id TEXT PRIMARY KEY, name TEXT)")
        con.execute("CREATE TABLE automation_runs (id TEXT PRIMARY KEY, automation_id TEXT)")
        con.execute("CREATE TABLE automation_runtime_state (automation_id TEXT PRIMARY KEY, state_json TEXT)")
        con.execute("CREATE TABLE session_usage (session_id TEXT PRIMARY KEY, total_tokens INTEGER)")
        con.execute("CREATE TABLE workspaces (id TEXT PRIMARY KEY, cwd TEXT)")
        con.commit()
    finally:
        con.close()
    return db


def seed_account_data(root: Path, source: str = "old-user", target: str = "new-user") -> None:
    con = sqlite3.connect(root / "workbuddy.db")
    try:
        con.executemany(
            "INSERT INTO sessions (id, user_id, title) VALUES (?, ?, ?)",
            [
                ("session-1", source, "Old session one"),
                ("session-2", source, "Old session two"),
                ("session-3", target, "Target session"),
            ],
        )
        con.executemany(
            "INSERT INTO automations (id, owner_user_id, owner_status, owner_source) VALUES (?, ?, ?, ?)",
            [
                ("automation-1", source, "active", "user"),
                ("automation-2", target, "active", "user"),
            ],
        )
        con.commit()
    finally:
        con.close()

    (root / "projects" / "session-1.jsonl").write_text(
        json.dumps({"session_id": "session-1", "role": "user", "content": "hello"}) + "\n",
        encoding="utf-8",
    )
    (root / "projects" / "orphan.jsonl").write_text(
        json.dumps({"session_id": "orphan-session", "role": "user", "content": "orphan"}) + "\n",
        encoding="utf-8",
    )
    (root / "memory" / f"{source}_memory.md").write_text("source memory\nshared line\n", encoding="utf-8")
    (root / "memory" / f"{target}_memory.md").write_text("target memory\nshared line\n", encoding="utf-8")
    (root / "memery" / f"{source}_memery.md").write_text("source memery\n", encoding="utf-8")
    (root / "memery" / f"{target}_memery.md").write_text("target memery\n", encoding="utf-8")
    (root / "connectors" / source).mkdir()
    (root / "connectors" / target).mkdir()
    (root / "connectors" / source / "settings.json").write_text('{"a": 1, "shared": "source"}\n', encoding="utf-8")
    (root / "connectors" / target / "settings.json").write_text('{"b": 2, "shared": "target"}\n', encoding="utf-8")
    (root / "connectors" / source / "token.json").write_text('{"token": "secret-value"}\n', encoding="utf-8")
