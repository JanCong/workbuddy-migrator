# WorkBuddy Account Migrator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a dry-run-first Python CLI named `wbm` that inventories, plans, backs up, applies, verifies, and rolls back local WorkBuddy account ownership migration.

**Architecture:** The tool reads WorkBuddy's observed local SQLite database and account-scoped directories, produces explicit machine-readable reports, and only mutates data through a planned operation list plus backup manifest. Session ids remain stable; migration changes account ownership rows and merges small account-scoped files while validating session-linked stores.

**Tech Stack:** Python 3.11+, stdlib `argparse`, `sqlite3`, `json`, `hashlib`, `shutil`, `dataclasses`, `pathlib`; `pytest` for tests.

---

## File Structure

- Create `.gitignore`: ignore local reports, Python caches, and build outputs.
- Create `pyproject.toml`: package metadata, CLI entrypoint, pytest settings.
- Create `README.md`: conservative open-source positioning, quick start, safety notes.
- Create `workbuddy_migrator/__init__.py`: package version.
- Create `workbuddy_migrator/models.py`: dataclasses shared by inventory, planning, backup, verify, rollback.
- Create `workbuddy_migrator/paths.py`: WorkBuddy path detection, env override for tests.
- Create `workbuddy_migrator/schema.py`: SQLite connection and schema inspection helpers.
- Create `workbuddy_migrator/report.py`: stable JSON serialization and report writing.
- Create `workbuddy_migrator/redact.py`: secret key/path detection and log-safe masking.
- Create `workbuddy_migrator/doctor.py`: read-only health checks.
- Create `workbuddy_migrator/inventory.py`: account/session/automation/file inventory.
- Create `workbuddy_migrator/planner.py`: explicit migration operation generation.
- Create `workbuddy_migrator/backup.py`: checksum backup manifest and restore path capture.
- Create `workbuddy_migrator/migrate.py`: transaction-safe DB migration and file merge execution.
- Create `workbuddy_migrator/verify.py`: post-apply invariant checks.
- Create `workbuddy_migrator/rollback.py`: manifest-based restore.
- Create `workbuddy_migrator/cli.py`: command routing and console output.
- Create `tests/conftest.py`: fixture workspace and SQLite data builders.
- Create `tests/test_doctor.py`: health checks.
- Create `tests/test_inventory.py`: inventory behavior.
- Create `tests/test_planner.py`: plan behavior and safety refusal.
- Create `tests/test_backup.py`: backup manifest behavior.
- Create `tests/test_migrate.py`: apply behavior.
- Create `tests/test_verify.py`: post-migration verification.
- Create `tests/test_rollback.py`: restore behavior.
- Create `tests/test_cli.py`: CLI report generation smoke tests.

## Task 1: Project Scaffold And Shared Models

**Files:**
- Create: `.gitignore`
- Create: `pyproject.toml`
- Create: `README.md`
- Create: `workbuddy_migrator/__init__.py`
- Create: `workbuddy_migrator/models.py`
- Create: `workbuddy_migrator/report.py`
- Create: `workbuddy_migrator/redact.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Write scaffold files**

Create `.gitignore`:

```gitignore
__pycache__/
*.py[cod]
.pytest_cache/
.coverage
build/
dist/
*.egg-info/
reports/
```

Create `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=69", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "workbuddy-migrator"
version = "0.1.0"
description = "Dry-run-first local WorkBuddy account migration tool"
readme = "README.md"
requires-python = ">=3.11"
license = { text = "MIT" }
authors = [{ name = "WorkBuddy Migrator Contributors" }]
dependencies = []

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[project.scripts]
wbm = "workbuddy_migrator.cli:main"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

Create `README.md`:

```markdown
# WorkBuddy Migrator

`workbuddy-migrator` is a dry-run-first local migration tool for restoring WorkBuddy account-scoped data visibility after switching accounts.

It is designed for local data owned by the user. It does not transfer cloud-side ownership, bypass WorkBuddy authentication, or copy credentials by default.

## MVP Commands

- `wbm doctor`
- `wbm inventory`
- `wbm plan --source <old_uid> --target current`
- `wbm backup --source <old_uid> --target current`
- `wbm apply --source <old_uid> --target current`
- `wbm verify --source <old_uid> --target current`
- `wbm rollback <backup_id>`

## Safety Model

- Read-only commands come first.
- `apply` creates or requires a backup.
- SQLite writes run inside a transaction.
- Secret-bearing connector data is skipped unless explicitly included.
- Reports are written as JSON for auditability.
```

Create `workbuddy_migrator/__init__.py`:

```python
"""WorkBuddy local account migration toolkit."""

__version__ = "0.1.0"
```

Create `workbuddy_migrator/models.py`:

```python
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
```

Create `workbuddy_migrator/report.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import to_jsonable


def write_json_report(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(to_jsonable(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def print_json(payload: Any) -> None:
    print(json.dumps(to_jsonable(payload), ensure_ascii=False, indent=2))
```

Create `workbuddy_migrator/redact.py`:

```python
from __future__ import annotations

from pathlib import Path

SECRET_MARKERS = (
    "token",
    "secret",
    "cookie",
    "credential",
    "password",
    "private_key",
    "apikey",
    "api_key",
)


def is_secret_name(name: str) -> bool:
    normalized = name.lower().replace("-", "_")
    return any(marker in normalized for marker in SECRET_MARKERS)


def is_secret_path(path: Path | str) -> bool:
    parts = Path(path).parts
    return any(is_secret_name(part) for part in parts)


def mask_user_id(user_id: str, verbose: bool = False) -> str:
    if verbose or len(user_id) <= 8:
        return user_id
    return f"{user_id[:4]}...{user_id[-4:]}"
```

Create `tests/conftest.py`:

```python
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest


@pytest.fixture
def workbuddy_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "workbuddy-home"
    root.mkdir()
    (root / "projects").mkdir()
    (root / "memory").mkdir()
    (root / "memery").mkdir()
    (root / "connectors").mkdir()
    monkeypatch.setenv("WORKBUDDY_HOME", str(root))
    return root


def create_db(root: Path, with_automation_owner: bool = True) -> Path:
    db = root / "workbuddy.db"
    con = sqlite3.connect(db)
    try:
        con.execute("CREATE TABLE sessions (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, title TEXT)")
        if with_automation_owner:
            con.execute(
                "CREATE TABLE automations (id TEXT PRIMARY KEY, owner_user_id TEXT, owner_status TEXT, owner_source TEXT)"
            )
        else:
            con.execute("CREATE TABLE automations (id TEXT PRIMARY KEY, name TEXT)")
        con.execute("CREATE TABLE automation_runs (id TEXT PRIMARY KEY, automation_id TEXT)")
        con.execute("CREATE TABLE automation_runtime_state (automation_id TEXT PRIMARY KEY, state_json TEXT)")
        con.execute("CREATE TABLE session_usage (session_id TEXT PRIMARY KEY, total_tokens INTEGER)")
        con.execute("CREATE TABLE workspaces (id TEXT PRIMARY KEY, cwd TEXT)")
        con.commit()
    finally:
        con.close()
    return db


def seed_account_data(root: Path, source: str = "old-user", target: str = "new-user") -> None:
    con = sqlite3.connect(root / "workbuddy.db")
    try:
        con.executemany(
            "INSERT INTO sessions (id, user_id, title) VALUES (?, ?, ?)",
            [
                ("session-1", source, "Old session one"),
                ("session-2", source, "Old session two"),
                ("session-3", target, "Target session"),
            ],
        )
        con.executemany(
            "INSERT INTO automations (id, owner_user_id, owner_status, owner_source) VALUES (?, ?, ?, ?)",
            [
                ("automation-1", source, "active", "user"),
                ("automation-2", target, "active", "user"),
            ],
        )
        con.commit()
    finally:
        con.close()

    (root / "projects" / "session-1.jsonl").write_text(
        json.dumps({"session_id": "session-1", "role": "user", "content": "hello"}) + "\n",
        encoding="utf-8",
    )
    (root / "projects" / "orphan.jsonl").write_text(
        json.dumps({"session_id": "orphan-session", "role": "user", "content": "orphan"}) + "\n",
        encoding="utf-8",
    )
    (root / "memory" / f"{source}_memory.md").write_text("source memory\nshared line\n", encoding="utf-8")
    (root / "memory" / f"{target}_memory.md").write_text("target memory\nshared line\n", encoding="utf-8")
    (root / "memery" / f"{source}_memery.md").write_text("source memery\n", encoding="utf-8")
    (root / "connectors" / source).mkdir()
    (root / "connectors" / target).mkdir()
    (root / "connectors" / source / "settings.json").write_text('{"a": 1, "shared": "source"}\n', encoding="utf-8")
    (root / "connectors" / target / "settings.json").write_text('{"b": 2, "shared": "target"}\n', encoding="utf-8")
    (root / "connectors" / source / "token.json").write_text('{"token": "secret-value"}\n', encoding="utf-8")
```

- [ ] **Step 2: Verify scaffold imports fail only because CLI is missing**

Run:

```bash
python -m pytest tests -q
```

Expected: pytest starts collecting. At this point no tests exist yet, so `no tests ran` is acceptable.

- [ ] **Step 3: Commit scaffold**

```bash
git add .gitignore pyproject.toml README.md workbuddy_migrator tests
git commit -m "chore: scaffold WorkBuddy migrator package"
```

## Task 2: Path Detection, Schema Inspection, And Doctor

**Files:**
- Create: `workbuddy_migrator/paths.py`
- Create: `workbuddy_migrator/schema.py`
- Create: `workbuddy_migrator/doctor.py`
- Create: `tests/test_doctor.py`

- [ ] **Step 1: Write failing doctor tests**

Create `tests/test_doctor.py`:

```python
from __future__ import annotations

from pathlib import Path

from conftest import create_db
from workbuddy_migrator.doctor import run_doctor
from workbuddy_migrator.paths import detect_paths


def test_detect_paths_uses_workbuddy_home_env(workbuddy_home: Path) -> None:
    paths = detect_paths()
    assert paths.root == workbuddy_home
    assert paths.db == workbuddy_home / "workbuddy.db"
    assert paths.projects == workbuddy_home / "projects"


def test_doctor_reports_missing_db(workbuddy_home: Path) -> None:
    result = run_doctor(detect_paths())
    assert result["ok"] is False
    assert "workbuddy.db is missing" in result["errors"]


def test_doctor_passes_fixture_schema(workbuddy_home: Path) -> None:
    create_db(workbuddy_home)
    result = run_doctor(detect_paths())
    assert result["ok"] is True
    assert result["schema"]["has_sessions"] is True
    assert result["schema"]["has_automation_owner"] is True
```

- [ ] **Step 2: Run doctor tests and confirm failure**

Run:

```bash
python -m pytest tests/test_doctor.py -q
```

Expected: FAIL with `ModuleNotFoundError` for `workbuddy_migrator.doctor` or missing functions.

- [ ] **Step 3: Implement paths, schema, and doctor**

Create `workbuddy_migrator/paths.py`:

```python
from __future__ import annotations

import os
from pathlib import Path

from .models import WorkBuddyPaths


def detect_paths(home: Path | None = None) -> WorkBuddyPaths:
    root = Path(os.environ.get("WORKBUDDY_HOME", "")).expanduser() if os.environ.get("WORKBUDDY_HOME") else None
    if root is None:
        root = home or Path.home() / ".workbuddy"
    app_support = Path.home() / "Library" / "Application Support" / "WorkBuddy"
    return WorkBuddyPaths(
        root=root,
        db=root / "workbuddy.db",
        projects=root / "projects",
        memory=root / "memory",
        memery=root / "memery",
        connectors=root / "connectors",
        backups=root / "migrator-backups",
        app_support=app_support if app_support.exists() else None,
    )
```

Create `workbuddy_migrator/schema.py`:

```python
from __future__ import annotations

import sqlite3
from pathlib import Path

from .models import SchemaInfo


def connect_readonly(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{db_path.as_posix()}?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    return con


def connect_writable(db_path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    return con


def inspect_schema(con: sqlite3.Connection) -> SchemaInfo:
    tables = [row["name"] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    columns: dict[str, list[str]] = {}
    for table in tables:
        rows = con.execute(f"PRAGMA table_info({table})").fetchall()
        columns[table] = [row["name"] for row in rows]
    return SchemaInfo(tables=columns)
```

Create `workbuddy_migrator/doctor.py`:

```python
from __future__ import annotations

from typing import Any

from .models import WorkBuddyPaths
from .schema import connect_readonly, inspect_schema


def run_doctor(paths: WorkBuddyPaths) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    if not paths.root.exists():
        errors.append("WorkBuddy root is missing")
    if not paths.db.exists():
        errors.append("workbuddy.db is missing")
        return {"ok": False, "errors": errors, "warnings": warnings}

    try:
        con = connect_readonly(paths.db)
        try:
            schema = inspect_schema(con)
        finally:
            con.close()
    except Exception as exc:
        errors.append(f"Cannot open workbuddy.db read-only: {exc}")
        return {"ok": False, "errors": errors, "warnings": warnings}

    has_sessions = schema.has_table("sessions") and schema.has_column("sessions", "user_id")
    has_automation_owner = schema.has_table("automations") and schema.has_column("automations", "owner_user_id")
    if not has_sessions:
        errors.append("sessions.user_id is missing")
    if not paths.projects.exists():
        warnings.append("projects directory is missing")
    if not paths.memory.exists():
        warnings.append("memory directory is missing")
    if not paths.memery.exists():
        warnings.append("memery directory is missing")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "schema": {
            "has_sessions": has_sessions,
            "has_automation_owner": has_automation_owner,
            "tables": schema.tables,
        },
    }
```

- [ ] **Step 4: Verify doctor tests pass**

Run:

```bash
python -m pytest tests/test_doctor.py -q
```

Expected: `3 passed`.

- [ ] **Step 5: Commit doctor milestone**

```bash
git add workbuddy_migrator/paths.py workbuddy_migrator/schema.py workbuddy_migrator/doctor.py tests/test_doctor.py
git commit -m "feat: add WorkBuddy doctor checks"
```

## Task 3: Inventory Accounts, Files, And Conversation Coverage

**Files:**
- Create: `workbuddy_migrator/inventory.py`
- Create: `tests/test_inventory.py`

- [ ] **Step 1: Write failing inventory tests**

Create `tests/test_inventory.py`:

```python
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
```

- [ ] **Step 2: Run inventory tests and confirm failure**

Run:

```bash
python -m pytest tests/test_inventory.py -q
```

Expected: FAIL with missing `workbuddy_migrator.inventory`.

- [ ] **Step 3: Implement inventory**

Create `workbuddy_migrator/inventory.py`:

```python
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
```

- [ ] **Step 4: Verify inventory tests pass**

Run:

```bash
python -m pytest tests/test_inventory.py tests/test_doctor.py -q
```

Expected: `6 passed`.

- [ ] **Step 5: Commit inventory milestone**

```bash
git add workbuddy_migrator/inventory.py tests/test_inventory.py
git commit -m "feat: inventory WorkBuddy account data"
```

## Task 4: Migration Planning

**Files:**
- Create: `workbuddy_migrator/planner.py`
- Create: `tests/test_planner.py`

- [ ] **Step 1: Write failing planner tests**

Create `tests/test_planner.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from conftest import create_db, seed_account_data
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
```

- [ ] **Step 2: Run planner tests and confirm failure**

Run:

```bash
python -m pytest tests/test_planner.py -q
```

Expected: FAIL with missing `workbuddy_migrator.planner`.

- [ ] **Step 3: Implement planner**

Create `workbuddy_migrator/planner.py`:

```python
from __future__ import annotations

from .models import Inventory, MigrationPlan, Operation


def _resolve_current_target(inventory: Inventory, source_user_id: str) -> str:
    candidates = [
        user_id
        for user_id, account in inventory.accounts.items()
        if user_id != source_user_id and (account.session_count > 0 or account.automation_count > 0)
    ]
    if len(candidates) != 1:
        raise ValueError("target current requires exactly one non-source account")
    return candidates[0]


def build_plan(
    inventory: Inventory,
    source_user_id: str,
    target_user_id: str,
    include_secrets: bool = False,
) -> MigrationPlan:
    target = _resolve_current_target(inventory, source_user_id) if target_user_id == "current" else target_user_id
    if source_user_id == target:
        raise ValueError("source and target must differ")
    if source_user_id not in inventory.accounts:
        raise ValueError(f"source account not found: {source_user_id}")
    if target not in inventory.accounts:
        raise ValueError(f"target account not found: {target}")

    operations: list[Operation] = []
    source_sessions = inventory.session_ids_by_user.get(source_user_id, [])
    if source_sessions:
        operations.append(
            Operation(
                kind="db_update",
                name="migrate_sessions_owner",
                description="Update sessions.user_id from source to target while preserving session ids",
                table="sessions",
                column="user_id",
                source=source_user_id,
                target=target,
                row_ids=source_sessions,
            )
        )

    source_automations = inventory.automation_ids_by_owner.get(source_user_id, [])
    if source_automations and inventory.schema.has_column("automations", "owner_user_id"):
        operations.append(
            Operation(
                kind="db_update",
                name="migrate_automations_owner",
                description="Update automations.owner_user_id from source to target while preserving automation ids",
                table="automations",
                column="owner_user_id",
                source=source_user_id,
                target=target,
                row_ids=source_automations,
            )
        )

    source_account = inventory.accounts[source_user_id]
    if source_account.memory_files:
        operations.append(
            Operation(
                kind="file_merge",
                name="merge_memory",
                description="Append source memory lines into target memory file with line-level deduplication",
                source=f"memory/{source_user_id}_memory.md",
                target=f"memory/{target}_memory.md",
            )
        )
    if source_account.memery_files:
        operations.append(
            Operation(
                kind="file_merge",
                name="merge_memery",
                description="Append source memery lines into target memery file with line-level deduplication",
                source=f"memery/{source_user_id}_memery.md",
                target=f"memery/{target}_memery.md",
            )
        )
    if source_account.connector_files:
        operations.append(
            Operation(
                kind="dir_merge",
                name="merge_connectors",
                description="Merge non-secret connector JSON files with target-first semantics",
                source=f"connectors/{source_user_id}",
                target=f"connectors/{target}",
            )
        )
        if not include_secrets:
            operations.append(
                Operation(
                    kind="skip",
                    name="skip_secret_connector_files",
                    description="Skip connector files with secret-bearing names unless include-secrets is enabled",
                    source=f"connectors/{source_user_id}",
                    target=f"connectors/{target}",
                    secret=True,
                )
            )

    operations.append(
        Operation(
            kind="validate_only",
            name="validate_conversation_jsonl",
            description="Report DB sessions without JSONL and JSONL files without DB sessions without rewriting conversation files",
        )
    )

    return MigrationPlan(source_user_id=source_user_id, target_user_id=target, operations=operations)
```

- [ ] **Step 4: Verify planner tests pass**

Run:

```bash
python -m pytest tests/test_planner.py tests/test_inventory.py tests/test_doctor.py -q
```

Expected: `9 passed`.

- [ ] **Step 5: Commit planner milestone**

```bash
git add workbuddy_migrator/planner.py tests/test_planner.py
git commit -m "feat: plan WorkBuddy account migration"
```

## Task 5: Backup Manifest

**Files:**
- Create: `workbuddy_migrator/backup.py`
- Create: `tests/test_backup.py`

- [ ] **Step 1: Write failing backup tests**

Create `tests/test_backup.py`:

```python
from __future__ import annotations

from pathlib import Path

from conftest import create_db, seed_account_data
from workbuddy_migrator.backup import create_backup
from workbuddy_migrator.inventory import load_inventory
from workbuddy_migrator.paths import detect_paths
from workbuddy_migrator.planner import build_plan


def test_backup_copies_db_and_target_files(workbuddy_home: Path) -> None:
    create_db(workbuddy_home)
    seed_account_data(workbuddy_home)
    paths = detect_paths()
    plan = build_plan(load_inventory(paths), "old-user", "new-user")
    manifest = create_backup(paths, plan, backup_id="test-backup")
    copied = [entry.restore_path for entry in manifest.entries if entry.copied]
    assert str(workbuddy_home / "workbuddy.db") in copied
    assert str(workbuddy_home / "memory" / "new-user_memory.md") in copied
    assert str(workbuddy_home / "memery" / "new-user_memery.md") in copied
    assert (workbuddy_home / "migrator-backups" / "test-backup" / "manifest.json").exists()
```

- [ ] **Step 2: Run backup tests and confirm failure**

Run:

```bash
python -m pytest tests/test_backup.py -q
```

Expected: FAIL with missing `workbuddy_migrator.backup`.

- [ ] **Step 3: Implement backup**

Create `workbuddy_migrator/backup.py`:

```python
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
```

- [ ] **Step 4: Verify backup tests pass**

Run:

```bash
python -m pytest tests/test_backup.py tests/test_planner.py tests/test_inventory.py tests/test_doctor.py -q
```

Expected: `10 passed`.

- [ ] **Step 5: Commit backup milestone**

```bash
git add workbuddy_migrator/backup.py tests/test_backup.py
git commit -m "feat: back up planned WorkBuddy changes"
```

## Task 6: Apply Migration

**Files:**
- Create: `workbuddy_migrator/migrate.py`
- Create: `tests/test_migrate.py`

- [ ] **Step 1: Write failing migration tests**

Create `tests/test_migrate.py`:

```python
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from conftest import create_db, seed_account_data
from workbuddy_migrator.backup import create_backup
from workbuddy_migrator.inventory import load_inventory
from workbuddy_migrator.migrate import apply_plan
from workbuddy_migrator.paths import detect_paths
from workbuddy_migrator.planner import build_plan


def test_apply_updates_sessions_and_automations(workbuddy_home: Path) -> None:
    create_db(workbuddy_home)
    seed_account_data(workbuddy_home)
    paths = detect_paths()
    plan = build_plan(load_inventory(paths), "old-user", "new-user")
    manifest = create_backup(paths, plan, backup_id="apply-backup")
    report = apply_plan(paths, plan, manifest)
    assert report["db_updates"]["sessions"] == 2
    assert report["db_updates"]["automations"] == 1
    con = sqlite3.connect(workbuddy_home / "workbuddy.db")
    try:
        old_sessions = con.execute("SELECT COUNT(*) FROM sessions WHERE user_id = 'old-user'").fetchone()[0]
        target_sessions = con.execute("SELECT COUNT(*) FROM sessions WHERE user_id = 'new-user'").fetchone()[0]
        old_automations = con.execute("SELECT COUNT(*) FROM automations WHERE owner_user_id = 'old-user'").fetchone()[0]
    finally:
        con.close()
    assert old_sessions == 0
    assert target_sessions == 3
    assert old_automations == 0


def test_apply_merges_memory_and_connector_without_secret(workbuddy_home: Path) -> None:
    create_db(workbuddy_home)
    seed_account_data(workbuddy_home)
    paths = detect_paths()
    plan = build_plan(load_inventory(paths), "old-user", "new-user")
    manifest = create_backup(paths, plan, backup_id="merge-backup")
    apply_plan(paths, plan, manifest)
    memory = (workbuddy_home / "memory" / "new-user_memory.md").read_text(encoding="utf-8")
    assert memory.splitlines() == ["target memory", "shared line", "source memory"]
    settings = json.loads((workbuddy_home / "connectors" / "new-user" / "settings.json").read_text(encoding="utf-8"))
    assert settings == {"b": 2, "shared": "target", "a": 1}
    assert not (workbuddy_home / "connectors" / "new-user" / "token.json").exists()
```

- [ ] **Step 2: Run migration tests and confirm failure**

Run:

```bash
python -m pytest tests/test_migrate.py -q
```

Expected: FAIL with missing `workbuddy_migrator.migrate`.

- [ ] **Step 3: Implement migration apply**

Create `workbuddy_migrator/migrate.py`:

```python
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
```

- [ ] **Step 4: Verify migration tests pass**

Run:

```bash
python -m pytest tests/test_migrate.py tests/test_backup.py tests/test_planner.py tests/test_inventory.py tests/test_doctor.py -q
```

Expected: `12 passed`.

- [ ] **Step 5: Commit migration milestone**

```bash
git add workbuddy_migrator/migrate.py tests/test_migrate.py
git commit -m "feat: apply WorkBuddy account migration"
```

## Task 7: Verification

**Files:**
- Create: `workbuddy_migrator/verify.py`
- Create: `tests/test_verify.py`

- [ ] **Step 1: Write failing verify tests**

Create `tests/test_verify.py`:

```python
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
```

- [ ] **Step 2: Run verify tests and confirm failure**

Run:

```bash
python -m pytest tests/test_verify.py -q
```

Expected: FAIL with missing `workbuddy_migrator.verify`.

- [ ] **Step 3: Implement verify**

Create `workbuddy_migrator/verify.py`:

```python
from __future__ import annotations

from typing import Any

from .models import MigrationPlan, WorkBuddyPaths
from .schema import connect_readonly, inspect_schema


def verify_plan(paths: WorkBuddyPaths, plan: MigrationPlan) -> dict[str, Any]:
    con = connect_readonly(paths.db)
    try:
        schema = inspect_schema(con)
        source_sessions = con.execute(
            "SELECT COUNT(*) FROM sessions WHERE user_id = ?",
            [plan.source_user_id],
        ).fetchone()[0]
        target_sessions = con.execute(
            "SELECT COUNT(*) FROM sessions WHERE user_id = ?",
            [plan.target_user_id],
        ).fetchone()[0]
        source_automations = 0
        target_automations = 0
        if schema.has_column("automations", "owner_user_id"):
            source_automations = con.execute(
                "SELECT COUNT(*) FROM automations WHERE owner_user_id = ?",
                [plan.source_user_id],
            ).fetchone()[0]
            target_automations = con.execute(
                "SELECT COUNT(*) FROM automations WHERE owner_user_id = ?",
                [plan.target_user_id],
            ).fetchone()[0]
    finally:
        con.close()

    memory_exists = (paths.memory / f"{plan.target_user_id}_memory.md").exists()
    memery_exists = (paths.memery / f"{plan.target_user_id}_memery.md").exists()
    checks = {
        "source_sessions_remaining": source_sessions,
        "target_sessions_total": target_sessions,
        "source_automations_remaining": source_automations,
        "target_automations_total": target_automations,
        "target_memory_exists": memory_exists,
        "target_memery_exists": memery_exists,
    }
    return {"ok": source_sessions == 0 and source_automations == 0, "checks": checks}
```

- [ ] **Step 4: Verify tests pass**

Run:

```bash
python -m pytest tests/test_verify.py tests/test_migrate.py tests/test_backup.py tests/test_planner.py tests/test_inventory.py tests/test_doctor.py -q
```

Expected: `14 passed`.

- [ ] **Step 5: Commit verify milestone**

```bash
git add workbuddy_migrator/verify.py tests/test_verify.py
git commit -m "feat: verify WorkBuddy migration results"
```

## Task 8: Rollback

**Files:**
- Create: `workbuddy_migrator/rollback.py`
- Create: `tests/test_rollback.py`

- [ ] **Step 1: Write failing rollback tests**

Create `tests/test_rollback.py`:

```python
from __future__ import annotations

import sqlite3
from pathlib import Path

from conftest import create_db, seed_account_data
from workbuddy_migrator.backup import create_backup
from workbuddy_migrator.inventory import load_inventory
from workbuddy_migrator.migrate import apply_plan
from workbuddy_migrator.paths import detect_paths
from workbuddy_migrator.planner import build_plan
from workbuddy_migrator.rollback import load_backup_manifest, rollback_backup


def test_rollback_restores_database_and_memory(workbuddy_home: Path) -> None:
    create_db(workbuddy_home)
    seed_account_data(workbuddy_home)
    paths = detect_paths()
    plan = build_plan(load_inventory(paths), "old-user", "new-user")
    manifest = create_backup(paths, plan, backup_id="rollback-backup")
    apply_plan(paths, plan, manifest)
    report = rollback_backup(manifest)
    assert report["restored"] >= 3
    con = sqlite3.connect(workbuddy_home / "workbuddy.db")
    try:
        old_sessions = con.execute("SELECT COUNT(*) FROM sessions WHERE user_id = 'old-user'").fetchone()[0]
    finally:
        con.close()
    assert old_sessions == 2
    memory = (workbuddy_home / "memory" / "new-user_memory.md").read_text(encoding="utf-8")
    assert memory.splitlines() == ["target memory", "shared line"]


def test_load_backup_manifest_from_json(workbuddy_home: Path) -> None:
    create_db(workbuddy_home)
    seed_account_data(workbuddy_home)
    paths = detect_paths()
    plan = build_plan(load_inventory(paths), "old-user", "new-user")
    manifest = create_backup(paths, plan, backup_id="json-backup")
    loaded = load_backup_manifest(Path(manifest.backup_dir) / "manifest.json")
    assert loaded.backup_id == "json-backup"
    assert loaded.plan.source_user_id == "old-user"
```

- [ ] **Step 2: Run rollback tests and confirm failure**

Run:

```bash
python -m pytest tests/test_rollback.py -q
```

Expected: FAIL with missing `workbuddy_migrator.rollback`.

- [ ] **Step 3: Implement rollback**

Create `workbuddy_migrator/rollback.py`:

```python
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
```

- [ ] **Step 4: Verify rollback tests pass**

Run:

```bash
python -m pytest tests/test_rollback.py tests/test_verify.py tests/test_migrate.py tests/test_backup.py tests/test_planner.py tests/test_inventory.py tests/test_doctor.py -q
```

Expected: `16 passed`.

- [ ] **Step 5: Commit rollback milestone**

```bash
git add workbuddy_migrator/rollback.py tests/test_rollback.py
git commit -m "feat: restore WorkBuddy data from backup"
```

## Task 9: CLI Commands And JSON Reports

**Files:**
- Create: `workbuddy_migrator/cli.py`
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write failing CLI tests**

Create `tests/test_cli.py`:

```python
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
```

- [ ] **Step 2: Run CLI tests and confirm failure**

Run:

```bash
python -m pytest tests/test_cli.py -q
```

Expected: FAIL with missing `workbuddy_migrator.cli`.

- [ ] **Step 3: Implement CLI**

Create `workbuddy_migrator/cli.py`:

```python
from __future__ import annotations

import argparse
from pathlib import Path

from .backup import create_backup
from .doctor import run_doctor
from .inventory import load_inventory
from .migrate import apply_plan
from .paths import detect_paths
from .planner import build_plan
from .report import print_json, write_json_report
from .rollback import load_backup_manifest, resolve_manifest_path, rollback_backup
from .verify import verify_plan


def _add_source_target(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--source", required=True)
    parser.add_argument("--target", required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wbm")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor")
    doctor.add_argument("--json", action="store_true")
    doctor.add_argument("--report", type=Path)

    inventory = sub.add_parser("inventory")
    inventory.add_argument("--json", action="store_true")
    inventory.add_argument("--report", type=Path)

    plan = sub.add_parser("plan")
    _add_source_target(plan)
    plan.add_argument("--json", action="store_true")
    plan.add_argument("--report", type=Path)

    backup = sub.add_parser("backup")
    _add_source_target(backup)
    backup.add_argument("--json", action="store_true")

    apply = sub.add_parser("apply")
    _add_source_target(apply)
    apply.add_argument("--yes", action="store_true")
    apply.add_argument("--json", action="store_true")

    verify = sub.add_parser("verify")
    _add_source_target(verify)
    verify.add_argument("--json", action="store_true")
    verify.add_argument("--report", type=Path)

    rollback = sub.add_parser("rollback")
    rollback.add_argument("backup_id")
    rollback.add_argument("--json", action="store_true")
    rollback.add_argument("--report", type=Path)

    return parser


def _emit(payload, as_json: bool, report: Path | None = None) -> None:
    if report:
        write_json_report(report, payload)
    if as_json:
        print_json(payload)
    else:
        status = "ok" if getattr(payload, "ok", None) or (isinstance(payload, dict) and payload.get("ok", True)) else "failed"
        print(f"wbm {status}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    paths = detect_paths()

    if args.command == "doctor":
        result = run_doctor(paths)
        _emit(result, args.json, args.report)
        return 0 if result["ok"] else 1

    if args.command == "inventory":
        inventory = load_inventory(paths)
        _emit(inventory, args.json, args.report)
        return 0

    if args.command == "plan":
        inventory = load_inventory(paths)
        plan = build_plan(inventory, args.source, args.target)
        _emit(plan, args.json, args.report)
        return 0

    if args.command == "backup":
        inventory = load_inventory(paths)
        plan = build_plan(inventory, args.source, args.target)
        manifest = create_backup(paths, plan)
        _emit(manifest, args.json)
        return 0

    if args.command == "apply":
        if not args.yes:
            raise SystemExit("apply requires --yes in the MVP CLI")
        inventory = load_inventory(paths)
        plan = build_plan(inventory, args.source, args.target)
        manifest = create_backup(paths, plan)
        result = apply_plan(paths, plan, manifest)
        _emit(result, args.json)
        return 0

    if args.command == "verify":
        inventory = load_inventory(paths)
        plan = build_plan(inventory, args.source, args.target)
        result = verify_plan(paths, plan)
        _emit(result, args.json, args.report)
        return 0 if result["ok"] else 1

    if args.command == "rollback":
        manifest_path = resolve_manifest_path(paths.backups, args.backup_id)
        manifest = load_backup_manifest(manifest_path)
        result = rollback_backup(manifest)
        _emit(result, args.json, args.report)
        return 0 if result["ok"] else 1

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Verify CLI tests pass**

Run:

```bash
python -m pytest tests/test_cli.py tests/test_rollback.py tests/test_verify.py tests/test_migrate.py tests/test_backup.py tests/test_planner.py tests/test_inventory.py tests/test_doctor.py -q
```

Expected: `19 passed`.

- [ ] **Step 5: Commit CLI milestone**

```bash
git add workbuddy_migrator/cli.py tests/test_cli.py
git commit -m "feat: expose WorkBuddy migrator CLI"
```

## Task 10: Final Hardening And Real-Machine Dry Run

**Files:**
- Modify: `README.md`
- Modify: existing tests if final validation reveals a mismatch between documented and implemented behavior.

- [ ] **Step 1: Run full automated tests**

Run:

```bash
python -m pytest -q
```

Expected: `19 passed`.

- [ ] **Step 2: Run local package CLI smoke test**

Run:

```bash
python -m workbuddy_migrator.cli --help
python -m workbuddy_migrator.cli doctor --json
```

Expected: help lists `doctor`, `inventory`, `plan`, `backup`, `apply`, `verify`, and `rollback`. The doctor command exits `0` when the local WorkBuddy fixture env is set, or exits `1` with a JSON error if no real local WorkBuddy database exists in the shell environment.

- [ ] **Step 3: Run read-only real-machine commands only**

Run without `WORKBUDDY_HOME`:

```bash
unset WORKBUDDY_HOME
python -m workbuddy_migrator.cli doctor --json --report reports/doctor.json
python -m workbuddy_migrator.cli inventory --json --report reports/inventory.json
```

Expected: no writes under real WorkBuddy data except report files under the repository `reports/` directory. The `reports/` directory is ignored by git. If `doctor` fails because WorkBuddy is not installed or the observed database path is absent, record that exact error in the final handoff instead of running write commands.

- [ ] **Step 4: Update README with verified commands**

Modify `README.md` so the quick start matches the actual command behavior:

````markdown
## Quick Start

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
python -m workbuddy_migrator.cli doctor --json
python -m workbuddy_migrator.cli inventory --json
python -m workbuddy_migrator.cli plan --source <old_uid> --target current --report plan.json
```

Run `backup`, `apply`, `verify`, and `rollback` only after reviewing the generated plan and backup manifest.
````

- [ ] **Step 5: Verify no secret values are printed in tests**

Run:

```bash
python -m pytest -q
rg -n "secret-value|token-value|password-value" reports workbuddy_migrator || true
```

Expected: pytest passes. The `rg` command prints no generated report or package code containing the literal fixture secret.

- [ ] **Step 6: Commit final hardening**

```bash
git add README.md
git commit -m "docs: document WorkBuddy migrator dry run"
```

## Plan Self-Review Notes

- Spec coverage: MVP commands from the design are covered by Tasks 2 through 9, including the `rollback` CLI path backed by a JSON manifest loader.
- Scope decision: `export`, orphan repair, Windows/Linux paths, full archive packaging, and GUI remain outside this MVP implementation plan.
- Safety decision: the real-machine milestone is read-only only; `apply` is tested against fixtures before any real WorkBuddy data is considered.
- Release boundary: public release should run the read-only real-machine dry run first, then require a separate explicit decision before applying to real WorkBuddy data.
