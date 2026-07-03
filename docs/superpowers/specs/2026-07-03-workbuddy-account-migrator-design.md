# WorkBuddy Account Migrator Design

Date: 2026-07-03
Status: Draft for user review

## Summary

Build a new WorkBuddy local account data migration tool. The primary goal is to make data from an old WorkBuddy account visible and usable under the currently logged-in account, with dry-run diagnostics, backups, verification, and rollback.

The tool should treat export as a safety net, not as the main product goal. Export helps preserve local conversations before risky changes, but the MVP is account migration for WorkBuddy UI visibility.

## Goals

1. Detect WorkBuddy local storage paths and schema versions.
2. Identify source and target accounts from local data.
3. Generate a dry-run migration plan before any write.
4. Back up all files and database rows that the tool will modify.
5. Migrate UI-visible account ownership for sessions and automations.
6. Merge account-scoped memory and connector data without overwriting target data.
7. Verify the migration with concrete before/after counts.
8. Roll back using a machine-readable manifest.

## Non-Goals

1. Do not promise cloud-side conversation ownership transfer.
2. Do not bypass WorkBuddy or Tencent account authorization.
3. Do not default to copying credentials, tokens, cookies, or secrets.
4. Do not rewrite conversation JSONL files unless a future WorkBuddy version requires it.
5. Do not default to copying large diagnostic stores such as logs, traces, or blobs.
6. Do not ship a GUI in the MVP.

## Current Evidence

The design is based on observed local WorkBuddy storage on this machine:

- `~/.workbuddy/workbuddy.db` contains `sessions`, `workspaces`, `automations`, `automation_runs`, `automation_runtime_state`, `session_usage`, and `migration_meta`.
- `sessions` is account-scoped through `user_id`.
- `automations` is now account-scoped through `owner_user_id`, `owner_status`, and `owner_source`.
- `workspaces` has no account column and should be validated rather than migrated.
- `automation_runs` and `automation_runtime_state` are keyed through automation ids and should be validated rather than rewritten.
- `~/.workbuddy/projects/**/*.jsonl` contains local conversation records keyed by session id.
- Some local JSONL conversation files may not have a matching row in `sessions`, so the tool should report orphan conversation files.
- `~/.workbuddy/memory` and `~/.workbuddy/memery` both exist and should both be considered account-scoped memory stores.
- `~/.workbuddy/connectors/<user_id>` exists and should be merged cautiously.
- `~/Library/Application Support/WorkBuddy/codebuddy-sessions.vscdb` may contain older or Electron-side session metadata and should be inventoried, not used as the primary source of truth for migration.

## Recommended Product Shape

Project name: `workbuddy-migrator`

Command name: `wbm`

Positioning:

> A dry-run-first local WorkBuddy account migration and recovery tool for restoring session and automation visibility after account changes.

The project should openly credit `workbuddy-account-migrate` as prior art while using a new data model and stricter safety model.

## CLI

### `wbm doctor`

Read-only health check.

Checks:

- WorkBuddy paths exist.
- `workbuddy.db` exists and can be opened read-only.
- SQLite WAL state can be inspected.
- WorkBuddy appears to be stopped or the user is warned that writes are unsafe.
- Required tables and columns exist.
- Current user id can be inferred.
- Free disk space is sufficient for backup.

Output:

- Human-readable summary.
- Optional JSON output with `--json`.

### `wbm inventory`

Read-only data inventory.

Reports:

- Distinct accounts from `sessions.user_id`.
- Distinct automation owners from `automations.owner_user_id`.
- Per-account counts for sessions, automations, memory files, memery files, connectors, inspiration directories, and related files.
- Counts for projects JSONL, orphan JSONL, task directories, artifact indexes, media indexes, and blobs.
- Schema warnings for unknown columns or missing expected columns.

### `wbm plan --source <old_uid> --target current`

Read-only migration plan.

The plan must list every intended write:

- Number of `sessions` rows that would change.
- Number of `automations` rows that would change.
- Memory files to merge.
- Memery files to merge.
- Connector files to merge.
- Inspiration files or directories to merge.
- Files that will only be validated.
- Data that will be skipped and why.

The default plan must not include secrets.

### `wbm backup --source <old_uid> --target current`

Create a backup before migration.

Back up:

- `workbuddy.db`, `workbuddy.db-wal`, and `workbuddy.db-shm` if present.
- Target and source memory files that will be read or written.
- Target and source memery files that will be read or written.
- Target connector directory before merge.
- Source connector directory manifest.
- Target inspiration directory before merge.
- The migration plan.

Large stores such as `projects`, `blobs`, `logs`, and `traces` should default to manifest-only backup. Users can request full copies with `--full-archive`.

Backup output:

- A directory under `~/.workbuddy/migrator-backups/<timestamp>-<source>-to-<target>/`.
- `manifest.json` describing every copied file, checksum, size, source path, and restore path.

### `wbm apply --source <old_uid> --target current`

Perform migration.

Preconditions:

- `doctor` passes.
- `plan` was generated.
- A backup exists or `apply` creates one.
- Source and target ids are different.
- User confirms unless `--yes` is passed.

Database writes:

- `UPDATE sessions SET user_id = target WHERE user_id = source`.
- If `automations.owner_user_id` exists, update matching rows to target.
- Preserve `owner_status` unless the source row is `legacy_unassigned`; in that case, set a clear migrated status only if WorkBuddy accepts it. MVP should avoid inventing new statuses.

File writes:

- Merge `memory/<source>_memory.md` into `memory/<target>_memory.md`.
- Merge `memery/<source>_memery.md` into `memery/<target>_memery.md`.
- Merge connector JSON files with target-first semantics.
- Copy non-secret connector state only when the target lacks that entry.
- Merge inspiration directory if files exist.

Secret policy:

- Do not copy credentials, tokens, cookies, or private key material by default.
- Require `--include-secrets` and a second confirmation for secret-bearing files.
- Redact secret values from logs and reports.

SQLite safety:

- Use transactions for DB writes.
- Run WAL checkpoint before reading for inventory and after committing writes.
- If checkpoint fails, stop and report the exact error.

### `wbm verify --source <old_uid> --target current`

Read-only verification after migration.

Checks:

- Source session count is zero unless `--partial` was requested.
- Target session count increased by expected amount.
- Source automation owner count is zero for rows selected by the plan.
- Target automation owner count increased by expected amount.
- Project JSONL coverage for migrated session ids is reported.
- Artifact, media, task, and session_usage links remain resolvable.
- Merged memory and connector files exist.

Verification should produce both console output and `verify.json`.

### `wbm rollback <backup_id>`

Restore from backup.

Behavior:

- Stop if WorkBuddy appears to be running unless `--force` is supplied.
- Restore DB files from backup.
- Restore target memory, memery, connector, and inspiration files.
- Leave large manifest-only stores unchanged.
- Generate `rollback-report.json`.

### `wbm export --source <old_uid>`

P1 safety-net command, not required for MVP apply.

Export local conversations into readable files:

- `index.md`
- `sessions/<date>-<title>/conversation.md`
- `sessions/<date>-<title>/raw.jsonl`
- `sessions/<date>-<title>/metadata.json`
- `sessions/<date>-<title>/tasks.md`
- `sessions/<date>-<title>/artifacts.md`

Export should never modify WorkBuddy data.

## Data Ownership Rules

### Sessions

Source of truth for UI visibility is `workbuddy.db.sessions`.

Migration changes only `user_id`. The session id must remain unchanged so local projects, tasks, artifacts, media indexes, usage, and JSONL files remain linked.

### Automations

If `automations.owner_user_id` exists, it is account-scoped and must be migrated. The tool should not rely on older documentation that says automations are global.

Rows in `automation_runs` and `automation_runtime_state` should not be rewritten because they reference `automation_id`.

### Workspaces

Workspaces are path-based in the observed schema. The tool should validate that referenced `cwd` and workspace paths exist, but it should not rewrite paths in MVP.

### Conversations

Local JSONL files under `~/.workbuddy/projects` should be treated as conversation body evidence. Migration should not rewrite them in MVP because session ids remain stable.

The tool must detect:

- DB sessions with no JSONL.
- JSONL files with no DB session.
- Multiple JSONL files for one session id.

### Memory

Both `memory` and `memery` are account-scoped stores. The merge rule is append-only, line-deduplicated, and target-preserving.

### Connectors

Merge JSON config files with target-first semantics:

- Target values win on key conflicts.
- Source-only keys are copied.
- Secret-bearing files are skipped unless explicitly requested.

### Artifacts, Media, Blobs, Tasks

These are session-linked stores. The migration should verify that links remain valid after session ids are reassigned to the target account. The MVP should not copy or rewrite these stores.

## Architecture

Recommended implementation language: Python 3.11+.

Reasoning:

- Python has built-in SQLite support.
- File hashing, JSON handling, and CLI implementation are straightforward.
- No Node or native dependency setup is required for the first version.

Package layout:

```text
workbuddy_migrator/
  cli.py
  paths.py
  schema.py
  inventory.py
  planner.py
  backup.py
  migrate.py
  verify.py
  rollback.py
  redact.py
  report.py
  # P1 optional:
  export.py
tests/
  fixtures/
  test_inventory.py
  test_planner.py
  test_migrate.py
  test_rollback.py
```

Module boundaries:

- `paths.py`: locate WorkBuddy data on macOS first, with future Windows/Linux support.
- `schema.py`: inspect tables and columns, avoid hard-coded assumptions.
- `inventory.py`: read-only data graph.
- `planner.py`: convert inventory into explicit operations.
- `backup.py`: copy files and write manifest.
- `migrate.py`: execute planned DB and file operations.
- `verify.py`: compare expected and actual results.
- `rollback.py`: restore from manifest.
- `export.py`: P1 module for readable archives. MVP implementation may omit this file unless export is explicitly pulled into scope.
- `redact.py`: redact secrets in reports.

## Safety Model

Default mode is read-only. The first write command must be `backup` or `apply` with automatic backup.

Safety checks:

- Refuse to run `apply` if source equals target.
- Refuse to run `apply` if schema is unknown unless `--unsafe-allow-unknown-schema` is passed.
- Refuse to run `apply` if WorkBuddy appears active unless user confirms.
- Refuse to include secrets without `--include-secrets`.
- Never print full user ids unless `--verbose` is used; show prefixes in default output.
- Never print connector secret values.

## Reports

Every command should produce a machine-readable report:

- `inventory.json`
- `plan.json`
- `backup-manifest.json`
- `apply-report.json`
- `verify.json`
- `rollback-report.json`

Reports make the project useful both as a user tool and as an open source debugging aid.

## MVP Scope

MVP commands:

1. `doctor`
2. `inventory`
3. `plan`
4. `backup`
5. `apply`
6. `verify`
7. `rollback`

P1 commands:

1. `export`
2. `repair-orphans`
3. Windows and Linux path support
4. Optional full archive packaging

## Testing Strategy

Use fixture databases and directories rather than the real user data.

Tests:

- Inventory detects session users and automation owners.
- Planner produces expected operations for source and target accounts.
- Planner refuses source equals target.
- Migrator updates session users and automation owners.
- Migrator merges memory and memery without overwriting target content.
- Migrator skips secret files by default.
- Backup manifest contains every modified path.
- Rollback restores DB and files to exact checksums.
- Verify catches missing JSONL, orphan JSONL, and failed owner migration.

Test fixtures should include:

- Old schema with no `automations.owner_user_id`.
- New schema with `automations.owner_user_id`.
- `memory` only.
- `memery` only.
- Both `memory` and `memery`.
- Orphan JSONL files.

## Open Source Positioning

The project is worth open sourcing because existing projects cover only part of the problem:

- `workbuddy-account-migrate` restores basic session visibility but does not cover newer automation ownership or broader inventory.
- `workbuddy-manager` helps inspect and back up some local metadata but is not an account migration tool.
- Memory sync tools do not migrate WorkBuddy session ownership.

README claims should be conservative:

- "Restores local WorkBuddy account-scoped data visibility where possible."
- "Does not transfer cloud-side ownership."
- "Dry-run first."
- "Back up and verify before applying."

## Success Criteria

The MVP is successful when, on a fixture matching the observed local schema:

1. `inventory` reports the correct old and target account counts.
2. `plan` lists the exact DB rows and files to touch.
3. `apply` migrates sessions and automation owners to target.
4. `verify` confirms no planned source-owned rows remain.
5. `rollback` restores the pre-migration checksums.
6. No command prints secret values.

On the user's real machine, the first safe milestone is:

1. `doctor` passes.
2. `inventory` reports the same account split previously observed.
3. `plan` produces a no-write migration report.
4. No real WorkBuddy data is modified.
