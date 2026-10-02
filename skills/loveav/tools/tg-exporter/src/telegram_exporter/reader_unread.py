from __future__ import annotations

import time
from typing import Any

from .bridge_errors import INVALID_ARGUMENT, TelegramBridgeError
from .reader_service import MAX_PAGE_LIMIT
from .unread_snapshot import capture_current_unread_snapshot


READ_ACK_CONFIRMATION = "MARK_READ_FROZEN_SNAPSHOT"


def _validate_limit(limit: int) -> int:
    value = int(limit)
    if value <= 0 or value > MAX_PAGE_LIMIT:
        raise TelegramBridgeError(
            INVALID_ARGUMENT,
            f"current-unread 单页数量必须在 1 到 {MAX_PAGE_LIMIT} 之间。",
        )
    return value


async def unread_snapshot_page(
    reader: Any,
    chat: str | int,
    *,
    cursor: str | None = None,
    limit: int = MAX_PAGE_LIMIT,
) -> dict[str, Any]:
    """读取一个固定 current-unread 范围，游标始终复用首次 lower/upper。"""

    limit = _validate_limit(limit)
    row, entity = await reader.resolve_dialog(chat)
    query = {"chat_id": row.chat_id}
    position = reader.cursor.decode(cursor, "messages.unread", query) if cursor else None

    if position is None:
        groups = await reader.telegram_service.list_groups()
        group = await reader.telegram_service.resolve_group(row.chat_id, groups)
        snapshot = await capture_current_unread_snapshot(reader.client, group)
        lower = int(snapshot.read_inbox_max_id or 0)
        upper = int(snapshot.latest_message_id or 0)
        unread_count = int(snapshot.unread_count or 0)
        after_id = lower
    else:
        lower = int(position.get("lower", 0) or 0)
        upper = int(position.get("upper", 0) or 0)
        unread_count = int(position.get("unread_count", 0) or 0)
        after_id = int(position.get("after_message_id", lower) or lower)

    if upper < lower or after_id < lower or after_id > upper:
        raise TelegramBridgeError(INVALID_ARGUMENT, "current-unread cursor 边界无效。")

    started = time.perf_counter()
    raw_rows: list[Any] = []
    if unread_count > 0 and upper > lower:
        async for message in reader.client.iter_messages(
            entity,
            reverse=True,
            min_id=after_id,
            max_id=upper + 1,
            limit=limit + 1,
        ):
            # 未读冻结范围必须保留服务消息和无文字媒体的 ID。
            # LoveAV 会把不能提取关键词的项放入 review，因此不会越过它们确认已读。
            if int(getattr(message, "id", 0) or 0) > 0:
                raw_rows.append(message)
            if len(raw_rows) >= limit + 1:
                break

    has_more = len(raw_rows) > limit
    page_rows = raw_rows[:limit]
    items = [
        await reader._message_info_v3(row, row.chat_id, message, {}, False)
        for message in page_rows
    ]
    next_cursor = None
    if has_more and items:
        next_cursor = reader.cursor.encode(
            "messages.unread",
            query,
            {
                "lower": lower,
                "upper": upper,
                "unread_count": unread_count,
                "after_message_id": items[-1].message_id,
            },
        )

    snapshot_token = reader.cursor.encode(
        "messages.mark_read",
        query,
        {"lower": lower, "upper": upper},
    )
    return {
        "chat_id": row.chat_id,
        "title": row.title,
        "lower": lower,
        "upper": upper,
        "unread_count": unread_count,
        "items": items,
        "count": len(items),
        "next_cursor": next_cursor,
        "has_more": has_more,
        "snapshot_token": snapshot_token,
        "timing": {
            "network_ms": int((time.perf_counter() - started) * 1000),
            "local_filter_ms": 0,
            "serialization_ms": 0,
        },
    }


async def mark_snapshot_read(
    reader: Any,
    chat: str | int,
    *,
    snapshot_token: str,
    max_id: int,
    confirmation: str,
) -> dict[str, Any]:
    """只允许把已读位置推进到已签名冻结范围内的指定水位。"""

    if confirmation != READ_ACK_CONFIRMATION:
        raise TelegramBridgeError(
            INVALID_ARGUMENT,
            f"确认词不正确；必须精确使用 {READ_ACK_CONFIRMATION}。",
        )
    row, entity = await reader.resolve_dialog(chat)
    query = {"chat_id": row.chat_id}
    position = reader.cursor.decode(snapshot_token, "messages.mark_read", query)
    if position is None:
        raise TelegramBridgeError(INVALID_ARGUMENT, "缺少 current-unread snapshot token。")
    lower = int(position.get("lower", 0) or 0)
    upper = int(position.get("upper", 0) or 0)
    requested = int(max_id)
    if not (lower < requested <= upper):
        raise TelegramBridgeError(
            INVALID_ARGUMENT,
            "mark-read max-id 必须位于签名的冻结未读范围内。",
            {"lower": lower, "upper": upper, "requested_max_id": requested},
        )

    await reader.client.send_read_acknowledge(entity, max_id=requested)
    return {
        "chat_id": row.chat_id,
        "frozen_lower": lower,
        "frozen_upper": upper,
        "acknowledged_max_id": requested,
        "confirmed": True,
    }
