from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable


@dataclass(slots=True)
class ExportMessage:
    id: int
    date: datetime
    from_name: str | None
    from_id: str | None
    text: str
    reply_to_message_id: int | None = None
    edited: datetime | None = None


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone().isoformat(timespec="seconds")


def _unix_str(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return str(int(dt.timestamp()))


def _text_entities(text: str) -> list[dict[str, str]]:
    # V0.1: pure text compatibility. Rich entity mapping can be extended later.
    return [{"type": "plain", "text": text}] if text else []


def serialize_message(message: ExportMessage) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": message.id,
        "type": "message",
        "date": _iso(message.date),
        "date_unixtime": _unix_str(message.date),
    }
    if message.from_name:
        data["from"] = message.from_name
    if message.from_id:
        data["from_id"] = message.from_id
    if message.reply_to_message_id:
        data["reply_to_message_id"] = message.reply_to_message_id
    if message.edited:
        data["edited"] = _iso(message.edited)
        data["edited_unixtime"] = _unix_str(message.edited)
    data["text"] = message.text
    data["text_entities"] = _text_entities(message.text)
    return data


def build_chat_export(
    *,
    name: str,
    chat_id: int,
    chat_type: str,
    messages: Iterable[ExportMessage],
) -> dict[str, Any]:
    return {
        "name": name,
        "type": chat_type,
        "id": abs(int(chat_id)),
        "messages": [serialize_message(m) for m in messages],
    }
