from __future__ import annotations

import logging

from telethon import TelegramClient

from .models import GroupInfo

logger = logging.getLogger("telegram_exporter.read_state")


async def mark_unread_snapshot_read(client: TelegramClient, group: GroupInfo) -> int | None:
    """Mark the frozen export-start unread snapshot as read, never newer messages.

    Telegram read state advances by message id. The acknowledgement therefore
    covers every incoming item up to the snapshot's latest message id, including
    media/service items that are not written into the text-only JSON export.
    """

    max_id = int(group.latest_message_id or 0)
    current = int(group.read_inbox_max_id or 0)
    if group.unread_count <= 0 or max_id <= current:
        logger.info(
            "No unread snapshot acknowledgement needed for '%s' (unread=%s, current=%s, latest=%s)",
            group.title,
            group.unread_count,
            current,
            max_id,
        )
        return None

    entity = await client.get_entity(group.chat_id)
    logger.info("Marking unread snapshot as read for '%s' (max_id=%s)", group.title, max_id)
    await client.send_read_acknowledge(entity, max_id=max_id)
    logger.info("Unread snapshot marked as read for '%s' (max_id=%s)", group.title, max_id)
    return max_id
