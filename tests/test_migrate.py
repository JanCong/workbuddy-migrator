from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from conftest import create_db, seed_account_data
from workbuddy_migrator.backup import create_backup
from workbuddy_migrator.inventory import load_inventory
from workbuddy_migrator.migrate import apply_plan
from workbuddy_migrator.paths import detect_paths
from workbuddy_migrator.planner import build_plan


def test_apply_updates_sessions_and_automations(workbuddy_home: Path) -> None:
    create_db(workbuddy_home)
    seed_account_data(workbuddy_home)
    paths = detect_paths()
    plan = build_plan(load_inventory(paths), "old-user", "new-user")
    manifest = create_backup(paths, plan, backup_id="apply-backup")
    report = apply_plan(paths, plan, manifest)
    assert report["db_updates"]["sessions"] == 2
    assert report["db_updates"]["automations"] == 1
    con = sqlite3.connect(workbuddy_home / "workbuddy.db")
    try:
        old_sessions = con.execute("SELECT COUNT(*) FROM sessions WHERE user_id = 'old-user'").fetchone()[0]
        target_sessions = con.execute("SELECT COUNT(*) FROM sessions WHERE user_id = 'new-user'").fetchone()[0]
        old_automations = con.execute("SELECT COUNT(*) FROM automations WHERE owner_user_id = 'old-user'").fetchone()[0]
    finally:
        con.close()
    assert old_sessions == 0
    assert target_sessions == 3
    assert old_automations == 0


def test_apply_merges_memory_and_connector_without_secret(workbuddy_home: Path) -> None:
    create_db(workbuddy_home)
    seed_account_data(workbuddy_home)
    paths = detect_paths()
    plan = build_plan(load_inventory(paths), "old-user", "new-user")
    manifest = create_backup(paths, plan, backup_id="merge-backup")
    apply_plan(paths, plan, manifest)
    memory = (workbuddy_home / "memory" / "new-user_memory.md").read_text(encoding="utf-8")
    assert memory.splitlines() == ["target memory", "shared line", "source memory"]
    settings = json.loads((workbuddy_home / "connectors" / "new-user" / "settings.json").read_text(encoding="utf-8"))
    assert settings == {"b": 2, "shared": "target", "a": 1}
    assert not (workbuddy_home / "connectors" / "new-user" / "token.json").exists()
