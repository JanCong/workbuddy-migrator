from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from .models import AccountInventory, ConversationCoverage, Inventory, WorkBuddyPaths
from .schema import connect_readonly, inspect_schema


def _list_names(path: Path, pattern: str) -> list[str]:
    if not path.exists():
        return []
    return sorted(item.name for item in path.glob(pattern) if item.is_file())


def _connector_files(path: Path) -> list[str]:
    if not path.exists():
        return []
    return sorted(str(item.relative_to(path)) for item in path.rglob("*") if item.is_file())


def _jsonl_session_ids(projects: Path) -> list[str]:
    ids: list[str] = []
    if not projects.exists():
        return ids
    for file_path in sorted(projects.rglob("*.jsonl")):
        with file_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                value = record.get("session_id") or record.get("sessionId") or record.get("conversationId")
                if isinstance(value, str) and value:
                    ids.append(value)
                    break
    return ids


def load_inventory(paths: WorkBuddyPaths) -> Inventory:
    con = connect_readonly(paths.db)
    try:
        schema = inspect_schema(con)
        session_rows = con.execute("SELECT id, user_id FROM sessions ORDER BY id").fetchall()
        sessions_by_user: dict[str, list[str]] = defaultdict(list)
        for row in session_rows:
            sessions_by_user[row["user_id"]].append(row["id"])

        automations_by_owner: dict[str, list[str]] = defaultdict(list)
        if schema.has_column("automations", "owner_user_id"):
            rows = con.execute("SELECT id, owner_user_id FROM automations WHERE owner_user_id IS NOT NULL ORDER BY id").fetchall()
            for row in rows:
                automations_by_owner[row["owner_user_id"]].append(row["id"])
    finally:
        con.close()

    user_ids = sorted(set(sessions_by_user) | set(automations_by_owner))
    accounts: dict[str, AccountInventory] = {}
    for user_id in user_ids:
        accounts[user_id] = AccountInventory(
            user_id=user_id,
            session_count=len(sessions_by_user.get(user_id, [])),
            automation_count=len(automations_by_owner.get(user_id, [])),
            memory_files=_list_names(paths.memory, f"{user_id}_memory.md"),
            memery_files=_list_names(paths.memery, f"{user_id}_memery.md"),
            connector_files=_connector_files(paths.connectors / user_id),
        )

    db_session_ids = sorted(row_id for ids in sessions_by_user.values() for row_id in ids)
    jsonl_ids = _jsonl_session_ids(paths.projects)
    jsonl_counter = Counter(jsonl_ids)
    coverage = ConversationCoverage(
        db_sessions_without_jsonl=sorted(set(db_session_ids) - set(jsonl_ids)),
        jsonl_without_db_session=sorted(set(jsonl_ids) - set(db_session_ids)),
        duplicate_jsonl_sessions=sorted(session_id for session_id, count in jsonl_counter.items() if count > 1),
    )

    return Inventory(
        root=str(paths.root),
        db_path=str(paths.db),
        schema=schema,
        accounts=accounts,
        session_ids_by_user={key: sorted(value) for key, value in sessions_by_user.items()},
        automation_ids_by_owner={key: sorted(value) for key, value in automations_by_owner.items()},
        conversation_coverage=coverage,
    )
