from __future__ import annotations

import hashlib
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .models import BackupEntry, BackupManifest, MigrationPlan, WorkBuddyPaths
from .report import write_json_report


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _backup_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _copy_entry(source: Path, backup_dir: Path, label: str, reason: str) -> BackupEntry:
    target = backup_dir / label
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return BackupEntry(
        source=str(source),
        restore_path=str(source),
        backup_path=str(target),
        sha256=sha256_file(source),
        size=source.stat().st_size,
        copied=True,
        reason=reason,
    )


def create_backup(paths: WorkBuddyPaths, plan: MigrationPlan, backup_id: str | None = None) -> BackupManifest:
    backup_name = backup_id or f"{_backup_id()}-{plan.source_user_id}-to-{plan.target_user_id}"
    backup_dir = paths.backups / backup_name
    backup_dir.mkdir(parents=True, exist_ok=False)
    entries: list[BackupEntry] = []

    for db_file in [paths.db, paths.db.with_name(paths.db.name + "-wal"), paths.db.with_name(paths.db.name + "-shm")]:
        if db_file.exists():
            entries.append(_copy_entry(db_file, backup_dir, f"database/{db_file.name}", "database restore copy"))

    for operation in plan.operations:
        if operation.kind == "file_merge" and operation.target:
            target_path = paths.root / operation.target
            if target_path.exists():
                entries.append(_copy_entry(target_path, backup_dir, f"files/{operation.target}", "target file before merge"))
        if operation.kind == "dir_merge" and operation.target:
            target_dir = paths.root / operation.target
            if target_dir.exists():
                for file_path in sorted(target_dir.rglob("*")):
                    if file_path.is_file():
                        relative = file_path.relative_to(paths.root)
                        entries.append(_copy_entry(file_path, backup_dir, f"files/{relative}", "target connector file before merge"))

    manifest = BackupManifest(backup_id=backup_name, backup_dir=str(backup_dir), entries=entries, plan=plan)
    write_json_report(backup_dir / "manifest.json", manifest)
    return manifest
