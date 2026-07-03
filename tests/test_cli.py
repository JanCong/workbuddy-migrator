from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from conftest import create_db, seed_account_data
from workbuddy_migrator.backup import create_backup
from workbuddy_migrator.cli import main
from workbuddy_migrator.inventory import load_inventory
from workbuddy_migrator.migrate import apply_plan
from workbuddy_migrator.paths import detect_paths
from workbuddy_migrator.planner import build_plan


def test_cli_inventory_json_report(workbuddy_home: Path, capsys) -> None:
    create_db(workbuddy_home)
    seed_account_data(workbuddy_home)
    exit_code = main(["inventory", "--json"])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["accounts"]["old-user"]["session_count"] == 2


def test_cli_plan_writes_report(workbuddy_home: Path, tmp_path: Path) -> None:
    create_db(workbuddy_home)
    seed_account_data(workbuddy_home)
    report_path = tmp_path / "plan.json"
    exit_code = main(["plan", "--source", "old-user", "--target", "new-user", "--report", str(report_path)])
    assert exit_code == 0
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["source_user_id"] == "old-user"
    assert payload["target_user_id"] == "new-user"


def test_cli_rollback_restores_manifest(workbuddy_home: Path, capsys) -> None:
    create_db(workbuddy_home)
    seed_account_data(workbuddy_home)
    paths = detect_paths()
    plan = build_plan(load_inventory(paths), "old-user", "new-user")
    manifest = create_backup(paths, plan, backup_id="cli-rollback")
    apply_plan(paths, plan, manifest)
    exit_code = main(["rollback", "cli-rollback", "--json"])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    con = sqlite3.connect(workbuddy_home / "workbuddy.db")
    try:
        old_sessions = con.execute("SELECT COUNT(*) FROM sessions WHERE user_id = 'old-user'").fetchone()[0]
    finally:
        con.close()
    assert old_sessions == 2
