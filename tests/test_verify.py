from __future__ import annotations

from pathlib import Path

from conftest import create_db, seed_account_data
from workbuddy_migrator.backup import create_backup
from workbuddy_migrator.inventory import load_inventory
from workbuddy_migrator.migrate import apply_plan
from workbuddy_migrator.paths import detect_paths
from workbuddy_migrator.planner import build_plan
from workbuddy_migrator.verify import verify_plan


def test_verify_passes_after_apply(workbuddy_home: Path) -> None:
    create_db(workbuddy_home)
    seed_account_data(workbuddy_home)
    paths = detect_paths()
    plan = build_plan(load_inventory(paths), "old-user", "new-user")
    manifest = create_backup(paths, plan, backup_id="verify-backup")
    apply_plan(paths, plan, manifest)
    result = verify_plan(paths, plan)
    assert result["ok"] is True
    assert result["checks"]["source_sessions_remaining"] == 0
    assert result["checks"]["source_automations_remaining"] == 0


def test_verify_fails_before_apply(workbuddy_home: Path) -> None:
    create_db(workbuddy_home)
    seed_account_data(workbuddy_home)
    paths = detect_paths()
    plan = build_plan(load_inventory(paths), "old-user", "new-user")
    result = verify_plan(paths, plan)
    assert result["ok"] is False
    assert result["checks"]["source_sessions_remaining"] == 2
