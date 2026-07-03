from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .models import BackupManifest, MigrationPlan, WorkBuddyPaths
from .redact import is_secret_path
from .schema import connect_writable


def _merge_lines(source: Path, target: Path) -> int:
    source_lines = source.read_text(encoding="utf-8").splitlines()
    target_lines = target.read_text(encoding="utf-8").splitlines() if target.exists() else []
    seen = set(target_lines)
    merged = list(target_lines)
    added = 0
    for line in source_lines:
        if line not in seen:
            merged.append(line)
            seen.add(line)
            added += 1
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(merged) + "\n", encoding="utf-8")
    return added


def _merge_json(source: Path, target: Path) -> None:
    source_data = json.loads(source.read_text(encoding="utf-8"))
    target_data = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}
    if not isinstance(source_data, dict) or not isinstance(target_data, dict):
        if not target.exists():
            shutil.copy2(source, target)
        return
    merged = dict(source_data)
    merged.update(target_data)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _merge_directory(source_dir: Path, target_dir: Path) -> dict[str, int]:
    copied = 0
    skipped_secret = 0
    for source in sorted(source_dir.rglob("*")):
        if not source.is_file():
            continue
        relative = source.relative_to(source_dir)
        if is_secret_path(relative):
            skipped_secret += 1
            continue
        target = target_dir / relative
        if source.suffix == ".json":
            _merge_json(source, target)
        elif not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        copied += 1
    return {"copied_or_merged": copied, "skipped_secret": skipped_secret}


def apply_plan(paths: WorkBuddyPaths, plan: MigrationPlan, manifest: BackupManifest) -> dict[str, Any]:
    if not manifest.entries:
        raise ValueError("backup manifest has no entries")

    db_updates = {"sessions": 0, "automations": 0}
    con = connect_writable(paths.db)
    try:
        con.execute("BEGIN")
        for operation in plan.operations:
            if operation.kind != "db_update":
                continue
            placeholders = ",".join("?" for _ in operation.row_ids)
            if operation.name == "migrate_sessions_owner":
                result = con.execute(
                    f"UPDATE sessions SET user_id = ? WHERE user_id = ? AND id IN ({placeholders})",
                    [plan.target_user_id, plan.source_user_id, *operation.row_ids],
                )
                db_updates["sessions"] = result.rowcount
            if operation.name == "migrate_automations_owner":
                result = con.execute(
                    f"UPDATE automations SET owner_user_id = ? WHERE owner_user_id = ? AND id IN ({placeholders})",
                    [plan.target_user_id, plan.source_user_id, *operation.row_ids],
                )
                db_updates["automations"] = result.rowcount
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

    file_merges: dict[str, Any] = {}
    for operation in plan.operations:
        if operation.kind == "file_merge" and operation.source and operation.target:
            added = _merge_lines(paths.root / operation.source, paths.root / operation.target)
            file_merges[operation.name] = {"added_lines": added}
        if operation.kind == "dir_merge" and operation.source and operation.target:
            file_merges[operation.name] = _merge_directory(paths.root / operation.source, paths.root / operation.target)

    return {"db_updates": db_updates, "file_merges": file_merges, "backup_id": manifest.backup_id}
