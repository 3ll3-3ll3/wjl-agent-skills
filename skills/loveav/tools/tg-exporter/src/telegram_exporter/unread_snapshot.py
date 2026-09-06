from __future__ import annotations

import logging
from dataclasses import replace

from telethon.utils import get_peer_id

from .bridge_errors import CHAT_NOT_FOUND, TelegramBridgeError
from .models import GroupInfo

logger = logging.getLogger("telegram_exporter.unread_snapshot")


async def capture_current_unread_snapshot(client, group: GroupInfo) -> GroupInfo:
    """Freeze the current logical chat's unread bounds for one export execution.

    The caller invokes this immediately before exporting *this* group.  The
    returned GroupInfo is a copy so the catalogue/workspace object remains a
    UI snapshot while export and optional read acknowledgement share one fixed
    lower/upper bound.
    """

    target_chat_id = int(group.chat_id)
    logger.info("Capturing current-unread export-start snapshot (chat_id=%s)", target_chat_id)

    async for dialog in client.iter_dialogs():
        if not (bool(getattr(dialog, "is_group", False)) or bool(getattr(dialog, "is_channel", False))):
            continue

        entity = getattr(dialog, "entity", None)
        if entity is None:
            continue
        try:
            dialog_chat_id = int(get_peer_id(entity))
        except (TypeError, ValueError):
            continue
        if dialog_chat_id != target_chat_id:
            continue

        raw_dialog = getattr(dialog, "dialog", None)
        message = getattr(dialog, "message", None)
        unread_count = int(getattr(dialog, "unread_count", 0) or 0)
        unread_mark = bool(getattr(raw_dialog, "unread_mark", False))
        snapshot = replace(
            group,
            unread_count=unread_count,
            read_inbox_max_id=int(getattr(raw_dialog, "read_inbox_max_id", 0) or 0),
            latest_message_id=int(getattr(message, "id", 0) or 0),
            is_unread=bool(unread_count > 0 or unread_mark),
        )
        logger.info(
            "Captured current-unread export-start snapshot (chat_id=%s, unread=%s, lower=%s, upper=%s)",
            target_chat_id,
            snapshot.unread_count,
            snapshot.read_inbox_max_id,
            snapshot.latest_message_id,
        )
        return snapshot

    raise TelegramBridgeError(
        CHAT_NOT_FOUND,
        f"开始导出时无法刷新 chat_id={target_chat_id} 的当前未读状态。请刷新群组后重试。",
    )
