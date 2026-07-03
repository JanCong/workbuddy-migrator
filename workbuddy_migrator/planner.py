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
