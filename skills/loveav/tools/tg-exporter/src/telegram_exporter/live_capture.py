from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from telethon import events
from telethon.tl.custom.message import Message
from telethon.utils import get_peer_id

from .bridge_errors import INVALID_ARGUMENT, TelegramBridgeError
from .reader_search import _extract_urls, _normalize_domain, _url_hostname, domain_matches


logger = logging.getLogger("telegram_exporter.live_capture")
MAX_CAPTURE_MESSAGES = 50
MAX_TEXT_LENGTH = 4096
MAX_FIRST_REPLY_TIMEOUT_SECONDS = 30.0
MAX_SETTLE_SECONDS = 5.0


def _event_chat_id(event: Any, message: Any) -> int | None:
    value = getattr(event, "chat_id", None)
    if isinstance(value, int):
        return value
    for candidate in (getattr(message, "peer_id", None), getattr(event, "chat", None)):
        try:
            return int(get_peer_id(candidate))
        except (TypeError, ValueError, AttributeError):
            continue
    return None


async def send_and_capture(
    reader: Any,
    destination_chat: str | int,
    text: str,
    *,
    first_reply_timeout_seconds: float = 8.0,
    settle_seconds: float = 2.0,
    max_messages: int = 20,
    url_domain: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """订阅目标会话后发送文本，并在同一 daemon 请求中捕获短时回复。"""

    body = str(text or "")
    if not body or len(body) > MAX_TEXT_LENGTH:
        raise TelegramBridgeError(
            INVALID_ARGUMENT,
            f"发送文本长度必须在 1 到 {MAX_TEXT_LENGTH} 之间。",
        )
    timeout = float(first_reply_timeout_seconds)
    settle = float(settle_seconds)
    requested_max = int(max_messages)
    if not (0.1 <= timeout <= MAX_FIRST_REPLY_TIMEOUT_SECONDS):
        raise TelegramBridgeError(INVALID_ARGUMENT, "first-reply-timeout 必须在 0.1 到 30 秒之间。")
    if not (0.1 <= settle <= MAX_SETTLE_SECONDS):
        raise TelegramBridgeError(INVALID_ARGUMENT, "settle-seconds 必须在 0.1 到 5 秒之间。")
    if not (1 <= requested_max <= MAX_CAPTURE_MESSAGES):
        raise TelegramBridgeError(INVALID_ARGUMENT, f"max-messages 必须在 1 到 {MAX_CAPTURE_MESSAGES} 之间。")

    wanted_domain = _normalize_domain(url_domain) if url_domain else None
    row, entity = await reader.resolve_dialog(destination_chat)
    if dry_run:
        return {
            "destination_chat_id": row.chat_id,
            "text_length": len(body),
            "dry_run": True,
            "first_reply_timeout_seconds": timeout,
            "settle_seconds": settle,
            "max_messages": requested_max,
            "url_domain": wanted_domain,
            "sent_message_id": None,
            "captured": [],
            "captured_count": 0,
            "timed_out": False,
        }

    queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=requested_max)
    sent_message_id: int | None = None

    async def on_new_message(event: Any) -> None:
        message = getattr(event, "message", None)
        if not isinstance(message, Message):
            return
        if _event_chat_id(event, message) not in {None, row.chat_id}:
            return
        message_id = int(getattr(message, "id", 0) or 0)
        if sent_message_id is not None and message_id == sent_message_id:
            return
        if bool(getattr(message, "out", False)):
            return
        if wanted_domain is not None:
            urls = _extract_urls(message)
            if not any(domain_matches(_url_hostname(url), wanted_domain) for url in urls):
                return
        if not queue.full():
            queue.put_nowait(message)

    builder = events.NewMessage(chats=entity)
    reader.client.add_event_handler(on_new_message, builder)
    try:
        logger.info(
            "Telegram write: send-and-capture destination_chat_id=%s text_length=%s timeout=%s settle=%s max=%s",
            row.chat_id,
            len(body),
            timeout,
            settle,
            requested_max,
        )
        sent = await reader.client.send_message(entity, body, parse_mode=None, link_preview=False)
        sent_message_id = int(getattr(sent, "id", 0) or 0) or None

        captured_raw: list[Any] = []
        first = None
        deadline = time.monotonic() + timeout
        while first is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                candidate = await asyncio.wait_for(queue.get(), timeout=remaining)
            except TimeoutError:
                break
            candidate_id = int(getattr(candidate, "id", 0) or 0)
            # handler 在 send 之前安装，所以可能短暂收到早于本次发送的消息。
            # Telegram 群组消息 ID 单调递增；只有严格晚于本次发送 ID 的回复才可入列。
            if sent_message_id is not None and candidate_id <= sent_message_id:
                continue
            first = candidate
            captured_raw.append(candidate)

        if first is not None:
            while len(captured_raw) < requested_max:
                try:
                    candidate = await asyncio.wait_for(queue.get(), timeout=settle)
                    candidate_id = int(getattr(candidate, "id", 0) or 0)
                    if sent_message_id is None or candidate_id > sent_message_id:
                        captured_raw.append(candidate)
                except TimeoutError:
                    break

        captured = [
            await reader._message_info_v3(row, row.chat_id, message, {}, False)
            for message in captured_raw
        ]
        logger.info(
            "Telegram write succeeded: send-and-capture destination_chat_id=%s sent_message_id=%s captured=%s",
            row.chat_id,
            sent_message_id,
            len(captured),
        )
        return {
            "destination_chat_id": row.chat_id,
            "text_length": len(body),
            "dry_run": False,
            "first_reply_timeout_seconds": timeout,
            "settle_seconds": settle,
            "max_messages": requested_max,
            "url_domain": wanted_domain,
            "sent_message_id": sent_message_id,
            "captured": captured,
            "captured_count": len(captured),
            "timed_out": not captured,
        }
    finally:
        reader.client.remove_event_handler(on_new_message, builder)
