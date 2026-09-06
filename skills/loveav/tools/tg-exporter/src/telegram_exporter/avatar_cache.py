from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from .paths import avatar_cache_dir

CACHE_MAX_AGE = timedelta(days=7)


def avatar_cache_path(chat_id: int) -> Path:
    token = f"m{abs(chat_id)}" if chat_id < 0 else str(chat_id)
    return avatar_cache_dir() / f"{token}.img"


def read_cached_avatar(chat_id: int, *, max_age: timedelta = CACHE_MAX_AGE) -> bytes | None:
    path = avatar_cache_path(chat_id)
    try:
        stat = path.stat()
    except OSError:
        return None

    modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
    if datetime.now(timezone.utc) - modified > max_age:
        return None

    try:
        data = path.read_bytes()
    except OSError:
        return None
    return data or None


def write_cached_avatar(chat_id: int, data: bytes) -> Path:
    path = avatar_cache_path(chat_id)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)
    return path
