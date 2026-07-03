from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path
from typing import Any, Literal


TargetRef = str
OperationKind = Literal["db_update", "file_merge", "dir_merge", "validate_only", "skip"]


@dataclass(frozen=True)
class WorkBuddyPaths:
    root: Path
    db: Path
    projects: Path
    memory: Path
    memery: Path
    connectors: Path
    backups: Path
    app_support: Path | None = None


@dataclass(frozen=True)
class SchemaInfo:
    tables: dict[str, list[str]]

    def has_table(self, table: str) -> bool:
        return table in self.tables

    def has_column(self, table: str, column: str) -> bool:
        return column in self.tables.get(table, [])


@dataclass(frozen=True)
class AccountInventory:
    user_id: str
    session_count: int = 0
    automation_count: int = 0
    memory_files: list[str] = field(default_factory=list)
    memery_files: list[str] = field(default_factory=list)
    connector_files: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ConversationCoverage:
    db_sessions_without_jsonl: list[str] = field(default_factory=list)
    jsonl_without_db_session: list[str] = field(default_factory=list)
    duplicate_jsonl_sessions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Inventory:
    root: str
    db_path: str
    schema: SchemaInfo
    accounts: dict[str, AccountInventory]
    session_ids_by_user: dict[str, list[str]]
    automation_ids_by_owner: dict[str, list[str]]
    conversation_coverage: ConversationCoverage
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Operation:
    kind: OperationKind
    name: str
    description: str
    source: str | None = None
    target: str | None = None
    table: str | None = None
    column: str | None = None
    row_ids: list[str] = field(default_factory=list)
    secret: bool = False


@dataclass(frozen=True)
class MigrationPlan:
    source_user_id: str
    target_user_id: str
    operations: list[Operation]
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class BackupEntry:
    source: str
    restore_path: str
    backup_path: str | None
    sha256: str | None
    size: int
    copied: bool
    reason: str


@dataclass(frozen=True)
class BackupManifest:
    backup_id: str
    backup_dir: str
    entries: list[BackupEntry]
    plan: MigrationPlan


def to_jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return {key: to_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    return value
