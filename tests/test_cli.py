from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from conftest import create_db, seed_account_data, seed_app_support_identity
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


def test_cli_inventory_report_human_status_is_ok(workbuddy_home: Path, tmp_path: Path, capsys) -> None:
    create_db(workbuddy_home)
    seed_account_data(workbuddy_home)
    report_path = tmp_path / "inventory.json"
    exit_code = main(["inventory", "--report", str(report_path)])
    assert exit_code == 0
    assert capsys.readouterr().out == "wbm ok\n"
    assert report_path.exists()


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


def test_cli_migrate_interactive_uses_numbered_accounts(
    workbuddy_home: Path,
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    create_db(workbuddy_home)
    seed_account_data(workbuddy_home)
    app_support = tmp_path / "WorkBuddy"
    seed_app_support_identity(app_support, "new-user", "Example User")
    monkeypatch.setenv("WORKBUDDY_APP_SUPPORT", str(app_support))
    replies = iter(["2", "1", "y"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(replies))

    exit_code = main(["migrate"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "[1] new-...user  Example User" in output
    assert "[2] old-...user  未找到姓名" in output
    assert "确认迁移" in output
    con = sqlite3.connect(workbuddy_home / "workbuddy.db")
    try:
        old_sessions = con.execute("SELECT COUNT(*) FROM sessions WHERE user_id = 'old-user'").fetchone()[0]
        new_sessions = con.execute("SELECT COUNT(*) FROM sessions WHERE user_id = 'new-user'").fetchone()[0]
    finally:
        con.close()
    assert old_sessions == 0
    assert new_sessions == 3
