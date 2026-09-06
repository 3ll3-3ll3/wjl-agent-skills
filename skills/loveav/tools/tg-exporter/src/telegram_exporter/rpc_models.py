from __future__ import annotations

from datetime import datetime
from typing import Any

from .models import (
    AccountInfo,
    ExportMode,
    FolderRef,
    ForwardResult,
    GroupExportPlan,
    GroupInfo,
    SendResult,
    TelegramMessageInfo,
)


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def folder_to_dict(folder: FolderRef) -> dict[str, Any]:
    return {"folder_id": folder.folder_id, "title": folder.title, "order": folder.order}


def folder_from_dict(payload: dict[str, Any]) -> FolderRef:
    return FolderRef(
        folder_id=int(payload["folder_id"]),
        title=str(payload["title"]),
        order=int(payload.get("order", 0)),
    )


def group_to_dict(group: GroupInfo) -> dict[str, Any]:
    return {
        "chat_id": group.chat_id,
        "title": group.title,
        "username": group.username,
        "chat_type": group.chat_type,
        "unread_count": group.unread_count,
        "read_inbox_max_id": group.read_inbox_max_id,
        "latest_message_id": group.latest_message_id,
        "migrated_from_chat_id": group.migrated_from_chat_id,
        "has_photo": group.has_photo,
        "is_group": group.is_group,
        "is_broadcast": group.is_broadcast,
        "is_muted": group.is_muted,
        "is_archived": group.is_archived,
        "is_unread": group.is_unread,
        "folders": [folder_to_dict(folder) for folder in group.folders],
    }


def group_from_dict(payload: dict[str, Any]) -> GroupInfo:
    return GroupInfo(
        chat_id=int(payload["chat_id"]),
        title=str(payload["title"]),
        username=payload.get("username"),
        chat_type=str(payload.get("chat_type", "group")),
        unread_count=int(payload.get("unread_count", 0)),
        read_inbox_max_id=int(payload.get("read_inbox_max_id", 0)),
        latest_message_id=int(payload.get("latest_message_id", 0)),
        migrated_from_chat_id=(
            int(payload["migrated_from_chat_id"])
            if payload.get("migrated_from_chat_id") is not None
            else None
        ),
        has_photo=bool(payload.get("has_photo", False)),
        is_group=bool(payload.get("is_group", False)),
        is_broadcast=bool(payload.get("is_broadcast", False)),
        is_muted=bool(payload.get("is_muted", False)),
        is_archived=bool(payload.get("is_archived", False)),
        is_unread=bool(payload.get("is_unread", False)),
        folders=tuple(folder_from_dict(item) for item in payload.get("folders", [])),
    )


def account_from_dict(payload: dict[str, Any]) -> AccountInfo:
    return AccountInfo(
        user_id=int(payload.get("user_id", 0)),
        display_name=payload.get("display_name"),
        username=payload.get("username"),
    )


def message_from_dict(payload: dict[str, Any]) -> TelegramMessageInfo:
    return TelegramMessageInfo(
        chat_id=int(payload["chat_id"]),
        chat_title=str(payload["chat_title"]),
        message_id=int(payload["message_id"]),
        date=datetime.fromisoformat(str(payload["date"])),
        sender=payload.get("sender"),
        text=str(payload.get("text", "")),
    )


def forward_from_dict(payload: dict[str, Any]) -> ForwardResult:
    return ForwardResult(
        source_chat_id=int(payload["source_chat_id"]),
        destination_chat_id=payload["destination_chat_id"],
        requested_ids=tuple(int(value) for value in payload.get("requested_ids", [])),
        successful_ids=tuple(int(value) for value in payload.get("successful_ids", [])),
        failed_ids=tuple(int(value) for value in payload.get("failed_ids", [])),
        dry_run=bool(payload.get("dry_run", False)),
    )


def send_from_dict(payload: dict[str, Any]) -> SendResult:
    message_id = payload.get("message_id")
    return SendResult(
        destination_chat_id=payload["destination_chat_id"],
        message_id=int(message_id) if message_id is not None else None,
        text_length=int(payload.get("text_length", 0)),
        dry_run=bool(payload.get("dry_run", False)),
    )


def plan_to_dict(plan: GroupExportPlan, *, mark_read_after_export: bool) -> dict[str, Any]:
    return {
        "group": group_to_dict(plan.group),
        "mode": plan.mode.value,
        "category": plan.category,
        "start_at": plan.start_at.isoformat() if plan.start_at else None,
        "end_at": plan.end_at.isoformat() if plan.end_at else None,
        "last_export_message_id": plan.last_export_message_id,
        "mark_read_after_export": bool(mark_read_after_export),
    }


def plan_from_dict(payload: dict[str, Any]) -> tuple[GroupExportPlan, bool]:
    plan = GroupExportPlan(
        group=group_from_dict(dict(payload["group"])),
        mode=ExportMode(str(payload["mode"])),
        category=str(payload.get("category") or "未分类"),
        start_at=_dt(payload.get("start_at")),
        end_at=_dt(payload.get("end_at")),
        last_export_message_id=int(payload.get("last_export_message_id", 0)),
    )
    plan.validate()
    return plan, bool(payload.get("mark_read_after_export", False))
