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

## Quick Start

```bash
python -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m pytest -q
.venv/bin/python -m workbuddy_migrator.cli doctor --json
.venv/bin/python -m workbuddy_migrator.cli inventory --json
.venv/bin/python -m workbuddy_migrator.cli plan --source <old_uid> --target current --report plan.json
```

Run `backup`, `apply`, `verify`, and `rollback` only after reviewing the generated plan and backup manifest.
