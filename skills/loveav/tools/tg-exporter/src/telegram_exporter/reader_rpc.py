from __future__ import annotations

from datetime import datetime
from typing import Any

from .bridge_errors import INVALID_ARGUMENT, TelegramBridgeError
from .reader_media import media_download
from .reader_runtime import PersonalAccountReaderV3
from .reader_search import search_messages_page
from .reader_topics import topic_history_page, topics_page

READER_METHODS = {
    "account.get",
    "dialogs.list",
    "chats.get",
    "chats.members",
    "messages.history",
    "topics.list",
    "topics.history",
    "media.download",
}


def _parse_iso(value: Any) -> datetime | None:
    if value in {None, ""}:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError as exc:
        raise TelegramBridgeError(INVALID_ARGUMENT, f"无法解析时间：{value}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.now().astimezone().tzinfo)
    return parsed


async def _reader(server: Any) -> PersonalAccountReaderV3:
    service = await server._authorized_service()
    current = getattr(server, "_v3_reader", None)
    if current is None or current.telegram_service is not service:
        current = PersonalAccountReaderV3(service)
        server._v3_reader = current
    return current


async def dispatch_reader(server: Any, method: str, params: dict[str, Any]) -> Any:
    async def operation():
        reader = await _reader(server)
        if method == "account.get":
            return await reader.account_profile()
        if method == "dialogs.list":
            return await reader.dialogs_page(
                dialog_type=params.get("dialog_type"),
                folder=params.get("folder"),
                archived=str(params.get("archived") or "all"),
                search=params.get("search"),
                unread=str(params.get("unread") or "all"),
                pinned=str(params.get("pinned") or "all"),
                cursor=params.get("cursor"),
                limit=int(params.get("limit", 100)),
            )
        if method == "chats.get":
            return await reader.chat_details(params.get("chat", ""))
        if method == "chats.members":
            return await reader.members_page(
                params.get("chat", ""),
                role=params.get("role"),
                cursor=params.get("cursor"),
                limit=int(params.get("limit", 100)),
            )
        if method == "messages.history":
            return await reader.messages_history_page(
                params.get("chat", ""),
                cursor=params.get("cursor"),
                limit=int(params.get("limit", 100)),
                since=_parse_iso(params.get("since")),
                until=_parse_iso(params.get("until")),
            )
        if method == "messages.search" and params.get("schema") == "v3":
            sender_id = params.get("sender_id")
            topic_id = params.get("topic_id")
            sender_role = params.get("sender_role")
            # This scope is the only place the sender-role patch enables
            # current-admin snapshot work and request-local sender recovery.
            # Ordinary history, GUI export and non-role searches do not opt in.
            with reader.sender_role_filter_scope(sender_role):
                return await search_messages_page(
                    reader,
                    chat=params.get("chat"),
                    contains=params.get("contains"),
                    regex=params.get("regex"),
                    sender_id=int(sender_id) if sender_id is not None else None,
                    sender_role=sender_role,
                    since=_parse_iso(params.get("since")),
                    until=_parse_iso(params.get("until")),
                    message_type=params.get("message_type"),
                    topic_id=int(topic_id) if topic_id is not None else None,
                    has_link=str(params.get("has_link") or "all"),
                    url_domain=params.get("url_domain"),
                    cursor=params.get("cursor"),
                    limit=int(params.get("limit", 100)),
                    case_sensitive=bool(params.get("case_sensitive", False)),
                )
        if method == "messages.get" and params.get("schema") == "v3":
            return await reader.messages_get_v3(
                params.get("chat", ""),
                [int(value) for value in params.get("ids", [])],
            )
        if method == "topics.list":
            return await topics_page(
                reader,
                params.get("chat", ""),
                cursor=params.get("cursor"),
                limit=int(params.get("limit", 100)),
            )
        if method == "topics.history":
            return await topic_history_page(
                reader,
                params.get("chat", ""),
                int(params.get("topic_id", 0)),
                cursor=params.get("cursor"),
                limit=int(params.get("limit", 100)),
                since=_parse_iso(params.get("since")),
                until=_parse_iso(params.get("until")),
            )
        if method == "media.download":
            return await media_download(
                reader,
                params.get("chat", ""),
                [int(value) for value in (params.get("ids") or [])],
                str(params.get("output") or ""),
                confirm=params.get("confirm"),
                allow_large_download=bool(params.get("allow_large_download", False)),
            )
        raise TelegramBridgeError(INVALID_ARGUMENT, f"未知 reader method：{method}")

    return await server.operations.run_read(operation)
