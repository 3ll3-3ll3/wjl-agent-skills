from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from telethon import TelegramClient
from telethon.tl.custom.message import Message

from .desktop_json import ExportMessage, build_chat_export
from .export_categories import export_timestamp_name, next_available_json_path, validate_category_name
from .models import ExportMode, GroupExportPlan

ProgressCallback = Callable[[int, int | None], None]


@dataclass(slots=True)
class ExportResult:
    chat_id: int
    title: str
    message_count: int
    latest_message_id: int
    result_path: Path


def safe_folder_name(value: str) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip().rstrip(".")
    return value[:120] or "Telegram Chat"


async def _sender_fields(message: Message) -> tuple[str | None, str | None]:
    sender = await message.get_sender()
    if sender is None:
        return None, None
    name = " ".join(
        p for p in [getattr(sender, "first_name", None), getattr(sender, "last_name", None)] if p
    ).strip()
    if not name:
        name = getattr(sender, "title", None) or getattr(sender, "username", None)
    sender_id = getattr(sender, "id", None)
    kind = "user" if getattr(sender, "first_name", None) is not None else "channel"
    return name or None, f"{kind}{sender_id}" if sender_id is not None else None


def _message_text(message: Message) -> str:
    # Telethon .message includes normal text and media caption text.
    return (message.message or "").strip()


def _iter_kwargs(plan: GroupExportPlan) -> dict:
    kwargs: dict = {"reverse": True}
    if plan.mode is ExportMode.DATE_RANGE:
        kwargs["offset_date"] = plan.start_at
    elif plan.mode is ExportMode.UNREAD:
        kwargs["min_id"] = plan.group.read_inbox_max_id
        # The caller supplies one frozen snapshot for this group's execution.
        # Telethon's max_id is exclusive, hence upper + 1 here.
        if plan.group.latest_message_id > 0:
            kwargs["max_id"] = plan.group.latest_message_id + 1
    elif plan.mode is ExportMode.SINCE_LAST_EXPORT:
        kwargs["min_id"] = plan.last_export_message_id
    return kwargs


async def _collect_messages(
    client: TelegramClient,
    entity,
    plan: GroupExportPlan,
    *,
    track_checkpoint: bool,
    exported: list[ExportMessage],
    progress: ProgressCallback | None,
) -> int:
    latest_id = 0
    async for message in client.iter_messages(entity, **_iter_kwargs(plan)):
        if not isinstance(message, Message):
            continue

        # DATE_RANGE uses inclusive application-level boundary checks.
        if plan.mode is ExportMode.DATE_RANGE:
            if plan.start_at and message.date < plan.start_at:
                continue
            if plan.end_at and message.date > plan.end_at:
                break

        if track_checkpoint:
            latest_id = max(latest_id, int(message.id))

        text = _message_text(message)
        if not text:
            continue

        from_name, from_id = await _sender_fields(message)
        reply_to = None
        if message.reply_to is not None:
            reply_to = getattr(message.reply_to, "reply_to_msg_id", None)

        exported.append(
            ExportMessage(
                id=int(message.id),
                date=message.date,
                from_name=from_name,
                from_id=from_id,
                text=text,
                reply_to_message_id=reply_to,
                edited=message.edit_date,
            )
        )
        if progress and len(exported) % 100 == 0:
            progress(len(exported), None)
    return latest_id


def _write_export_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
        f.write("\n")
    tmp.replace(path)


async def export_group(
    client: TelegramClient,
    plan: GroupExportPlan,
    output_root: Path,
    progress: ProgressCallback | None = None,
    export_moment: datetime | None = None,
) -> ExportResult:
    plan.validate()
    category = validate_category_name(plan.category)
    current_entity = await client.get_entity(plan.group.chat_id)

    exported: list[ExportMessage] = []
    latest_id = 0

    # For upgraded basic-group -> supergroup chats, only historical date-range
    # exports need to query the legacy Chat. Current unread and since-last always
    # belong to the active supergroup.
    if plan.mode is ExportMode.DATE_RANGE and plan.group.migrated_from_chat_id is not None:
        legacy_entity = await client.get_entity(plan.group.migrated_from_chat_id)
        await _collect_messages(
            client,
            legacy_entity,
            plan,
            track_checkpoint=False,
            exported=exported,
            progress=progress,
        )

    # A dialog with zero unread messages should produce a valid empty export,
    # not accidentally fall back to min_id=0 and walk the whole chat history.
    should_fetch_current = not (plan.mode is ExportMode.UNREAD and plan.group.unread_count <= 0)
    if should_fetch_current:
        latest_id = await _collect_messages(
            client,
            current_entity,
            plan,
            track_checkpoint=True,
            exported=exported,
            progress=progress,
        )

    if len(exported) > 1:
        exported.sort(key=lambda item: (item.date, item.id))

    group_folder = Path(output_root) / category / safe_folder_name(plan.group.title)
    moment = export_moment or datetime.now().astimezone()
    result_path = next_available_json_path(group_folder, export_timestamp_name(moment))
    payload = build_chat_export(
        name=plan.group.title,
        chat_id=plan.group.chat_id,
        chat_type="private_supergroup",
        messages=exported,
    )
    _write_export_json_atomic(result_path, payload)

    if progress:
        progress(len(exported), len(exported))
    return ExportResult(
        chat_id=plan.group.chat_id,
        title=plan.group.title,
        message_count=len(exported),
        latest_message_id=latest_id,
        result_path=result_path,
    )
