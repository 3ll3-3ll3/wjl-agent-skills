from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

DEFAULT_EXPORT_CATEGORY = "未分类"


class ExportMode(StrEnum):
    DATE_RANGE = "date_range"
    UNREAD = "unread"
    SINCE_LAST_EXPORT = "since_last_export"


@dataclass(frozen=True, slots=True)
class FolderRef:
    """A Telegram account chat-folder reference attached to an eligible group."""

    folder_id: int
    title: str
    order: int = 0


@dataclass(slots=True)
class GroupInfo:
    chat_id: int
    title: str
    username: str | None = None
    chat_type: str = "group"
    unread_count: int = 0
    read_inbox_max_id: int = 0
    latest_message_id: int = 0
    migrated_from_chat_id: int | None = None
    has_photo: bool = False
    is_group: bool = False
    is_broadcast: bool = False
    is_muted: bool = False
    is_archived: bool = False
    is_unread: bool = False
    folders: tuple[FolderRef, ...] = ()


@dataclass(frozen=True, slots=True)
class AccountInfo:
    user_id: int
    display_name: str | None
    username: str | None


@dataclass(frozen=True, slots=True)
class TelegramMessageInfo:
    chat_id: int
    chat_title: str
    message_id: int
    date: datetime
    sender: str | None
    text: str


@dataclass(frozen=True, slots=True)
class ForwardResult:
    source_chat_id: int
    destination_chat_id: int | str
    requested_ids: tuple[int, ...]
    successful_ids: tuple[int, ...]
    failed_ids: tuple[int, ...]
    dry_run: bool = False


@dataclass(frozen=True, slots=True)
class SendResult:
    destination_chat_id: int | str
    message_id: int | None
    text_length: int
    dry_run: bool = False


@dataclass(slots=True)
class GroupExportPlan:
    group: GroupInfo
    mode: ExportMode
    category: str = DEFAULT_EXPORT_CATEGORY
    start_at: datetime | None = None
    end_at: datetime | None = None
    last_export_message_id: int = 0

    def validate(self) -> None:
        if not str(self.category).strip():
            raise ValueError(f"群组「{self.group.title}」必须指定导出分类。")
        if self.mode is ExportMode.DATE_RANGE:
            if self.start_at is None or self.end_at is None:
                raise ValueError("时间范围模式必须同时指定开始和结束时间。")
            if self.start_at > self.end_at:
                raise ValueError("开始时间不能晚于结束时间。")
        elif self.mode is ExportMode.SINCE_LAST_EXPORT and self.last_export_message_id <= 0:
            raise ValueError(
                f"群组「{self.group.title}」还没有上次成功导出记录。"
                "请先使用指定时间范围或当前未读模式完成一次导出。"
            )
