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
