from __future__ import annotations

import sqlite3
from pathlib import Path

from conftest import create_db, seed_account_data
from workbuddy_migrator.backup import create_backup
from workbuddy_migrator.inventory import load_inventory
from workbuddy_migrator.migrate import apply_plan
from workbuddy_migrator.paths import detect_paths
from workbuddy_migrator.planner import build_plan
from workbuddy_migrator.rollback import load_backup_manifest, rollback_backup


def test_rollback_restores_database_and_memory(workbuddy_home: Path) -> None:
    create_db(workbuddy_home)
    seed_account_data(workbuddy_home)
    paths = detect_paths()
    plan = build_plan(load_inventory(paths), "old-user", "new-user")
    manifest = create_backup(paths, plan, backup_id="rollback-backup")
    apply_plan(paths, plan, manifest)
    report = rollback_backup(manifest)
    assert report["restored"] >= 3
    con = sqlite3.connect(workbuddy_home / "workbuddy.db")
    try:
        old_sessions = con.execute("SELECT COUNT(*) FROM sessions WHERE user_id = 'old-user'").fetchone()[0]
    finally:
        con.close()
    assert old_sessions == 2
    memory = (workbuddy_home / "memory" / "new-user_memory.md").read_text(encoding="utf-8")
    assert memory.splitlines() == ["target memory", "shared line"]


def test_load_backup_manifest_from_json(workbuddy_home: Path) -> None:
    create_db(workbuddy_home)
    seed_account_data(workbuddy_home)
    paths = detect_paths()
    plan = build_plan(load_inventory(paths), "old-user", "new-user")
    manifest = create_backup(paths, plan, backup_id="json-backup")
    loaded = load_backup_manifest(Path(manifest.backup_dir) / "manifest.json")
    assert loaded.backup_id == "json-backup"
    assert loaded.plan.source_user_id == "old-user"
