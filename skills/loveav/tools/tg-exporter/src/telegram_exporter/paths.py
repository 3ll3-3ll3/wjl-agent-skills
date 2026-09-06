from __future__ import annotations

import os
from pathlib import Path

APP_DIR_NAME = "TelegramMultiChatExporter"


def app_data_dir() -> Path:
    base = os.environ.get("APPDATA")
    if base:
        path = Path(base) / APP_DIR_NAME
    else:
        path = Path.home() / ".telegram-multi-chat-exporter"
    path.mkdir(parents=True, exist_ok=True)
    return path


def credentials_path() -> Path:
    return app_data_dir() / "api_credentials.json"


def session_path() -> Path:
    return app_data_dir() / "telegram"


def session_files() -> tuple[Path, ...]:
    base = session_path()
    return (
        base.with_suffix(".session"),
        base.with_suffix(".session-journal"),
    )


def state_path() -> Path:
    return app_data_dir() / "local_state.json"


def settings_path() -> Path:
    return app_data_dir() / "settings.json"


def ipc_identity_path() -> Path:
    return app_data_dir() / "ipc_identity.json"


def ipc_identity_lock_path() -> Path:
    return app_data_dir() / "ipc_identity.lock"


def daemon_lock_path() -> Path:
    return app_data_dir() / "tg-daemon.lock"


def daemon_job_state_path() -> Path:
    return app_data_dir() / "daemon_jobs.json"


def logs_dir() -> Path:
    path = app_data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def avatar_cache_dir() -> Path:
    """Local-only cache for small Telegram chat avatars used by the selector UI."""

    path = app_data_dir() / "cache" / "avatars"
    path.mkdir(parents=True, exist_ok=True)
    return path
