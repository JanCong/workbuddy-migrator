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
