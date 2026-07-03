from __future__ import annotations

from pathlib import Path

from conftest import create_db, seed_account_data
from workbuddy_migrator.inventory import load_inventory
from workbuddy_migrator.paths import detect_paths


def test_inventory_counts_accounts_sessions_and_automations(workbuddy_home: Path) -> None:
    create_db(workbuddy_home)
    seed_account_data(workbuddy_home)
    inventory = load_inventory(detect_paths())
    assert inventory.accounts["old-user"].session_count == 2
    assert inventory.accounts["new-user"].session_count == 1
    assert inventory.accounts["old-user"].automation_count == 1
    assert inventory.accounts["new-user"].automation_count == 1


def test_inventory_finds_memory_memery_and_connectors(workbuddy_home: Path) -> None:
    create_db(workbuddy_home)
    seed_account_data(workbuddy_home)
    inventory = load_inventory(detect_paths())
    assert "old-user_memory.md" in inventory.accounts["old-user"].memory_files
    assert "old-user_memery.md" in inventory.accounts["old-user"].memery_files
    assert "settings.json" in inventory.accounts["old-user"].connector_files


def test_inventory_reports_jsonl_coverage(workbuddy_home: Path) -> None:
    create_db(workbuddy_home)
    seed_account_data(workbuddy_home)
    inventory = load_inventory(detect_paths())
    assert inventory.conversation_coverage.db_sessions_without_jsonl == ["session-2", "session-3"]
    assert inventory.conversation_coverage.jsonl_without_db_session == ["orphan-session"]
