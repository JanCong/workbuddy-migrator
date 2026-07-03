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
