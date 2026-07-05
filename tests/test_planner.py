from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from conftest import create_db, seed_account_data, seed_app_support_identity
from workbuddy_migrator.inventory import load_inventory
from workbuddy_migrator.paths import detect_paths
from workbuddy_migrator.planner import build_plan


def test_plan_lists_session_automation_and_file_operations(workbuddy_home: Path) -> None:
    create_db(workbuddy_home)
    seed_account_data(workbuddy_home)
    inventory = load_inventory(detect_paths())
    plan = build_plan(inventory, source_user_id="old-user", target_user_id="new-user")
    names = [operation.name for operation in plan.operations]
    assert "migrate_sessions_owner" in names
    assert "migrate_automations_owner" in names
    assert "merge_memory" in names
    assert "merge_memery" in names
    assert "merge_connectors" in names
    assert "skip_secret_connector_files" in names


def test_plan_rejects_same_source_and_target(workbuddy_home: Path) -> None:
    create_db(workbuddy_home)
    seed_account_data(workbuddy_home)
    inventory = load_inventory(detect_paths())
    with pytest.raises(ValueError, match="source and target must differ"):
        build_plan(inventory, source_user_id="old-user", target_user_id="old-user")


def test_plan_resolves_current_target(workbuddy_home: Path) -> None:
    create_db(workbuddy_home)
    seed_account_data(workbuddy_home)
    inventory = load_inventory(detect_paths())
    plan = build_plan(inventory, source_user_id="old-user", target_user_id="current")
    assert plan.target_user_id == "new-user"


def test_plan_resolves_current_target_without_existing_target_rows(
    workbuddy_home: Path,
    tmp_path: Path,
    monkeypatch,
) -> None:
    create_db(workbuddy_home)
    con = sqlite3.connect(workbuddy_home / "workbuddy.db")
    try:
        con.executemany(
            "INSERT INTO sessions (id, user_id, title) VALUES (?, ?, ?)",
            [("session-1", "old-user", "Old session one"), ("session-2", "old-user", "Old session two")],
        )
        con.commit()
    finally:
        con.close()
    app_support = tmp_path / "WorkBuddy"
    seed_app_support_identity(app_support, "new-user", "Example User")
    monkeypatch.setenv("WORKBUDDY_APP_SUPPORT", str(app_support))

    inventory = load_inventory(detect_paths())
    plan = build_plan(inventory, source_user_id="old-user", target_user_id="current")

    assert plan.target_user_id == "new-user"
