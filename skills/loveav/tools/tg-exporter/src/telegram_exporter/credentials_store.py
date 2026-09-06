from __future__ import annotations

import logging

from .paths import credentials_path
from .storage import read_json, write_json_atomic
from .telegram_service import ApiCredentials

logger = logging.getLogger("telegram_exporter.credentials_store")


def load_saved_credentials() -> ApiCredentials | None:
    payload = read_json(credentials_path(), None)
    if not payload:
        return None
    try:
        api_id = int(payload["api_id"])
        api_hash = str(payload["api_hash"])
    except (KeyError, TypeError, ValueError):
        logger.warning("Stored Telegram API credentials are invalid")
        return None
    if api_id <= 0 or not api_hash:
        return None
    return ApiCredentials(api_id=api_id, api_hash=api_hash)


def save_credentials(credentials: ApiCredentials) -> None:
    if credentials.api_id <= 0 or not credentials.api_hash:
        raise ValueError("API ID 和 API Hash 不能为空。")
    write_json_atomic(
        credentials_path(),
        {"api_id": int(credentials.api_id), "api_hash": str(credentials.api_hash)},
    )
    logger.info("Telegram API credentials saved locally (api_id=%s; api_hash not logged)", credentials.api_id)
