from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .models import BackupEntry, BackupManifest, MigrationPlan, Operation


def resolve_manifest_path(backups_dir: Path, backup_ref: str) -> Path:
    candidate = Path(backup_ref).expanduser()
    if candidate.is_file():
        return candidate
    return backups_dir / backup_ref / "manifest.json"


def load_backup_manifest(path: Path) -> BackupManifest:
    payload = json.loads(path.read_text(encoding="utf-8"))
    operations = [Operation(**operation) for operation in payload["plan"]["operations"]]
    plan = MigrationPlan(
        source_user_id=payload["plan"]["source_user_id"],
        target_user_id=payload["plan"]["target_user_id"],
        operations=operations,
        warnings=payload["plan"].get("warnings", []),
    )
    entries = [BackupEntry(**entry) for entry in payload["entries"]]
    return BackupManifest(
        backup_id=payload["backup_id"],
        backup_dir=payload["backup_dir"],
        entries=entries,
        plan=plan,
    )


def rollback_backup(manifest: BackupManifest) -> dict[str, Any]:
    restored = 0
    missing: list[str] = []
    for entry in manifest.entries:
        if not entry.copied or not entry.backup_path:
            continue
        backup_path = Path(entry.backup_path)
        restore_path = Path(entry.restore_path)
        if not backup_path.exists():
            missing.append(str(backup_path))
            continue
        restore_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup_path, restore_path)
        restored += 1
    return {"ok": not missing, "restored": restored, "missing": missing}
