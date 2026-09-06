from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from telethon.errors import RPCError
from telethon.tl import functions

from .bridge_errors import ACCESS_DENIED, INVALID_ARGUMENT, NOT_A_FORUM, TelegramBridgeError
from .reader_models import ForumTopicInfo, Page
from .reader_service import MAX_PAGE_LIMIT, PersonalAccountReader


def _validate_limit(limit: int) -> int:
    value = int(limit)
    if value <= 0:
        raise TelegramBridgeError(INVALID_ARGUMENT, "limit 必须大于 0。")
    if value > MAX_PAGE_LIMIT:
        raise TelegramBridgeError(
            INVALID_ARGUMENT,
            f"reader 单页最多 {MAX_PAGE_LIMIT} 条。",
            {"requested_limit": value, "max_limit": MAX_PAGE_LIMIT},
        )
    return value


def _topic_payload(topic: Any) -> ForumTopicInfo | None:
    if type(topic).__name__ != "ForumTopic":
        return None
    date = getattr(topic, "date", None)
    return ForumTopicInfo(
        topic_id=int(getattr(topic, "id", 0) or 0),
        title=str(getattr(topic, "title", "") or ""),
        icon_color=(int(getattr(topic, "icon_color", 0) or 0) or None),
        icon_custom_emoji_id=(int(getattr(topic, "icon_emoji_id", 0) or 0) or None),
        top_message_id=(int(getattr(topic, "top_message", 0) or 0) or None),
        unread_count=int(getattr(topic, "unread_count", 0) or 0),
        pinned=bool(getattr(topic, "pinned", False)),
        closed=bool(getattr(topic, "closed", False)),
        hidden=bool(getattr(topic, "hidden", False)),
        date=date if isinstance(date, datetime) else None,
    )


async def topics_page(
    reader: PersonalAccountReader,
    chat: str | int,
    *,
    cursor: str | None = None,
    limit: int = 100,
) -> Page:
    limit = _validate_limit(limit)
    row, entity = await reader.resolve_dialog(chat)
    if row.dialog_type != "supergroup" or not row.forum:
        raise TelegramBridgeError(NOT_A_FORUM, "该会话不是 Telegram Forum Supergroup。")

    query = {"chat_id": row.chat_id}
    position = reader.cursor.decode(cursor, "topics.list", query) or {}
    offset_date = None
    if position.get("offset_date"):
        try:
            offset_date = datetime.fromisoformat(str(position["offset_date"]))
        except ValueError as exc:
            raise TelegramBridgeError(INVALID_ARGUMENT, "topic cursor date 无效。") from exc
    offset_id = int(position.get("offset_id", 0) or 0)
    offset_topic = int(position.get("offset_topic", 0) or 0)

    network_started = time.perf_counter()
    try:
        result = await reader.client(
            functions.messages.GetForumTopicsRequest(
                peer=entity,
                q=None,
                offset_date=offset_date,
                offset_id=offset_id,
                offset_topic=offset_topic,
                limit=min(limit + 1, MAX_PAGE_LIMIT + 1),
            )
        )
    except RPCError as exc:
        raise TelegramBridgeError(
            ACCESS_DENIED,
            "Telegram 未向当前账号开放该 Forum Topic 列表。",
            {"telegram_error": type(exc).__name__},
        ) from exc
    network_ms = int((time.perf_counter() - network_started) * 1000)

    raw = [item for item in (getattr(result, "topics", None) or ()) if type(item).__name__ == "ForumTopic"]
    rows = [mapped for item in raw if (mapped := _topic_payload(item)) is not None]
    count_hint = int(getattr(result, "count", len(rows)) or len(rows))
    has_more = len(rows) > limit or (len(rows) >= limit and count_hint > limit)
    items = rows[:limit]
    next_cursor = None
    if has_more and items:
        last = items[-1]
        next_cursor = reader.cursor.encode(
            "topics.list",
            query,
            {
                "offset_date": last.date.isoformat() if last.date else None,
                "offset_id": last.top_message_id or 0,
                "offset_topic": last.topic_id,
            },
        )
    return Page(
        items=items,
        next_cursor=next_cursor,
        has_more=has_more,
        timing={"network_ms": network_ms, "local_filter_ms": 0, "serialization_ms": 0},
    )


async def topic_history_page(
    reader: PersonalAccountReader,
    chat: str | int,
    topic_id: int,
    *,
    cursor: str | None = None,
    limit: int = 100,
    since: datetime | None = None,
    until: datetime | None = None,
) -> Page:
    row, _ = await reader.resolve_dialog(chat)
    if row.dialog_type != "supergroup" or not row.forum:
        raise TelegramBridgeError(NOT_A_FORUM, "该会话不是 Telegram Forum Supergroup。")
    if int(topic_id) <= 0:
        raise TelegramBridgeError(INVALID_ARGUMENT, "topic id 必须大于 0。")
    return await reader.messages_history_page(
        row.chat_id,
        cursor=cursor,
        limit=limit,
        since=since,
        until=until,
        topic_id=int(topic_id),
    )
