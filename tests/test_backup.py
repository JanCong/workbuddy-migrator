from __future__ import annotations

from pathlib import Path

from conftest import create_db, seed_account_data
from workbuddy_migrator.backup import create_backup
from workbuddy_migrator.inventory import load_inventory
from workbuddy_migrator.paths import detect_paths
from workbuddy_migrator.planner import build_plan


def test_backup_copies_db_and_target_files(workbuddy_home: Path) -> None:
    create_db(workbuddy_home)
    seed_account_data(workbuddy_home)
    paths = detect_paths()
    plan = build_plan(load_inventory(paths), "old-user", "new-user")
    manifest = create_backup(paths, plan, backup_id="test-backup")
    copied = [entry.restore_path for entry in manifest.entries if entry.copied]
    assert str(workbuddy_home / "workbuddy.db") in copied
    assert str(workbuddy_home / "memory" / "new-user_memory.md") in copied
    assert str(workbuddy_home / "memery" / "new-user_memery.md") in copied
    assert (workbuddy_home / "migrator-backups" / "test-backup" / "manifest.json").exists()
