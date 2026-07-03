from __future__ import annotations

import os
from pathlib import Path

from .models import WorkBuddyPaths


def detect_paths(home: Path | None = None) -> WorkBuddyPaths:
    root = Path(os.environ["WORKBUDDY_HOME"]).expanduser() if os.environ.get("WORKBUDDY_HOME") else None
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
