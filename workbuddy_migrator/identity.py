from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any

from .models import AccountIdentity


TOKEN_RE = re.compile(r"Bearer\s+([A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)")


def _decode_jwt_payload(token: str) -> dict[str, Any] | None:
    parts = token.split(".")
    if len(parts) != 3:
        return None
    payload = parts[1]
    payload += "=" * ((4 - len(payload) % 4) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload.encode("ascii"))
        data = json.loads(decoded.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def current_user_id(app_support: Path | None) -> str | None:
    if app_support is None:
        return None
    storage = app_support / "User" / "globalStorage" / "storage.json"
    if not storage.exists():
        return None
    try:
        data = json.loads(storage.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    value = data.get("genie.userId") if isinstance(data, dict) else None
    return value if isinstance(value, str) and value else None


def _identity_from_payload(payload: dict[str, Any]) -> tuple[str, AccountIdentity] | None:
    user_id = payload.get("sub")
    if not isinstance(user_id, str) or not user_id:
        return None
    display_name = payload.get("name")
    nickname = payload.get("nickname")
    preferred_username = payload.get("preferred_username")
    return (
        user_id,
        AccountIdentity(
            display_name=display_name if isinstance(display_name, str) and display_name else None,
            nickname=nickname if isinstance(nickname, str) and nickname else None,
            preferred_username=preferred_username if isinstance(preferred_username, str) and preferred_username else None,
            auth_time=payload.get("auth_time") if isinstance(payload.get("auth_time"), int) else None,
            issued_at=payload.get("iat") if isinstance(payload.get("iat"), int) else None,
            expires_at=payload.get("exp") if isinstance(payload.get("exp"), int) else None,
            source="jwt_log",
        ),
    )


def _identity_rank(identity: AccountIdentity) -> tuple[int, int]:
    return (identity.auth_time or 0, identity.issued_at or 0)


def jwt_log_identities(app_support: Path | None) -> dict[str, AccountIdentity]:
    if app_support is None:
        return {}
    logs = app_support / "logs"
    if not logs.exists():
        return {}

    identities: dict[str, AccountIdentity] = {}
    for file_path in sorted(logs.rglob("*.log*")):
        if not file_path.is_file():
            continue
        try:
            with file_path.open("r", encoding="utf-8", errors="ignore") as handle:
                for line in handle:
                    for match in TOKEN_RE.finditer(line):
                        payload = _decode_jwt_payload(match.group(1))
                        if not payload:
                            continue
                        item = _identity_from_payload(payload)
                        if not item:
                            continue
                        user_id, identity = item
                        existing = identities.get(user_id)
                        if existing is None or _identity_rank(identity) >= _identity_rank(existing):
                            identities[user_id] = identity
        except OSError:
            continue
    return identities
