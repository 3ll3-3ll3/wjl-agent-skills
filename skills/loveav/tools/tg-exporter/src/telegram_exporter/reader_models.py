from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .models import FolderRef


@dataclass(frozen=True, slots=True)
class AccountProfile:
    user_id: int
    display_name: str | None
    username: str | None
    premium: bool
    bot: bool
    language_code: str | None


@dataclass(slots=True)
class DialogInfo:
    chat_id: int
    title: str
    username: str | None
    dialog_type: str
    reference: str | None = None
    unread_count: int = 0
    pinned: bool = False
    muted: bool = False
    archived: bool = False
    forum: bool = False
    is_unread: bool = False
    is_contact: bool = False
    migrated_from_chat_id: int | None = None
    migrated_to_chat_id: int | None = None
    last_message_id: int = 0
    last_message_date: datetime | None = None
    folders: tuple[FolderRef, ...] = ()


@dataclass(frozen=True, slots=True)
class ParticipantInfo:
    user_id: int
    display_name: str | None
    username: str | None
    role: str
    is_creator: bool
    is_admin: bool
    admin_title: str | None
    bot: bool
    deleted_account: bool


@dataclass(frozen=True, slots=True)
class ChatDetails:
    chat_id: int
    title: str
    username: str | None
    chat_type: str
    description: str | None
    member_count: int | None
    owner: ParticipantInfo | None
    owner_visibility: str
    current_account_rights: dict[str, bool | None]
    forum: bool
    migrated_from_chat_id: int | None
    migrated_to_chat_id: int | None
    linked_chat_id: int | None
    available_min_id: int | None
    pinned_message_id: int | None


@dataclass(frozen=True, slots=True)
class SenderInfo:
    sender_id: int | None
    sender_type: str
    display_name: str | None
    username: str | None
    posted_as_chat_id: int | None
    is_creator: bool | None
    is_admin: bool | None
    admin_title: str | None
    anonymous_admin: bool
    via_bot_id: int | None
    role_basis: str
    unknown_reason: str | None = None


@dataclass(frozen=True, slots=True)
class MediaMetadata:
    media_type: str
    filename: str | None = None
    mime_type: str | None = None
    size: int | None = None
    width: int | None = None
    height: int | None = None
    duration: float | None = None
    document_id: int | None = None
    photo_id: int | None = None
    spoiler: bool = False


@dataclass(frozen=True, slots=True)
class MessageInfoV3:
    chat_id: int
    source_chat_id: int
    message_id: int
    date: datetime
    edit_date: datetime | None
    sender: SenderInfo
    text: str | None
    caption: str | None
    entities: tuple[dict[str, Any], ...]
    reply_to_message_id: int | None
    reply_to_top_id: int | None
    forum_topic_id: int | None
    forward_origin: dict[str, Any] | None
    grouped_id: int | None
    views: int | None
    forwards: int | None
    reactions: tuple[dict[str, Any], ...]
    poll: dict[str, Any] | None
    service_action: dict[str, Any] | None
    pinned: bool
    media: MediaMetadata | None
    availability: str = "available"


@dataclass(frozen=True, slots=True)
class ForumTopicInfo:
    topic_id: int
    title: str
    icon_color: int | None
    icon_custom_emoji_id: int | None
    top_message_id: int | None
    unread_count: int
    pinned: bool
    closed: bool
    hidden: bool
    date: datetime | None = None


@dataclass(slots=True)
class Page:
    items: list[Any] = field(default_factory=list)
    next_cursor: str | None = None
    has_more: bool = False
    count: int = 0
    timing: dict[str, int] = field(
        default_factory=lambda: {"network_ms": 0, "local_filter_ms": 0, "serialization_ms": 0}
    )
    scanned_count: int | None = None
    matched_count: int | None = None

    def __post_init__(self) -> None:
        if not self.count:
            self.count = len(self.items)
