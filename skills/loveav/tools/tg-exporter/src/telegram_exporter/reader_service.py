from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from telethon.errors import RPCError
from telethon.tl import functions, types
from telethon.tl.custom.message import Message
from telethon.utils import get_peer_id

from .bridge_errors import (
    ACCESS_DENIED,
    AMBIGUOUS_CHAT,
    CHAT_NOT_FOUND,
    INVALID_ARGUMENT,
    MEMBERS_UNAVAILABLE,
    MESSAGE_NOT_FOUND,
    TelegramBridgeError,
)
from .cursor_codec import CursorCodec
from .dialog_filters import filter_title, peer_ids
from .models import FolderRef
from .reader_models import (
    AccountProfile,
    ChatDetails,
    DialogInfo,
    MediaMetadata,
    MessageInfoV3,
    Page,
    ParticipantInfo,
    SenderInfo,
)

logger = logging.getLogger("telegram_exporter.reader_service")

DEFAULT_PAGE_LIMIT = 100
MAX_PAGE_LIMIT = 500
ROLE_CACHE_TTL_SECONDS = 60.0
PARTICIPANT_SCAN_CAP = 5000


def _display_name(entity: Any) -> str | None:
    if entity is None:
        return None
    first = getattr(entity, "first_name", None)
    last = getattr(entity, "last_name", None)
    name = " ".join(part for part in (first, last) if part).strip()
    return name or getattr(entity, "title", None) or getattr(entity, "username", None)


def _safe_peer_id(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return int(value)
    try:
        return int(get_peer_id(value))
    except (TypeError, ValueError, AttributeError):
        return None


def _entity_dialog_type(entity: Any, *, own_user_id: int | None = None) -> str:
    cls = type(entity).__name__
    if cls == "User":
        if own_user_id is not None and int(getattr(entity, "id", 0) or 0) == own_user_id:
            return "saved"
        return "bot" if bool(getattr(entity, "bot", False)) else "private"
    if cls == "Channel":
        return "supergroup" if bool(getattr(entity, "megagroup", False)) else "channel"
    if cls == "Chat":
        return "group"
    return "unknown"


def _dialog_is_muted(dialog: Any) -> bool:
    settings = getattr(getattr(dialog, "dialog", None), "notify_settings", None)
    mute_until = getattr(settings, "mute_until", None)
    if not mute_until:
        return False
    if isinstance(mute_until, datetime):
        if mute_until.tzinfo is None:
            mute_until = mute_until.replace(tzinfo=timezone.utc)
        return mute_until > datetime.now(timezone.utc)
    try:
        return float(mute_until) > datetime.now(timezone.utc).timestamp()
    except (TypeError, ValueError):
        return False


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


def _yes_no_all(value: str | None, field: str) -> str:
    normalized = str(value or "all").casefold()
    if normalized not in {"yes", "no", "all"}:
        raise TelegramBridgeError(INVALID_ARGUMENT, f"{field} 只能是 yes/no/all。")
    return normalized


def _dialog_rank(dialog_type: str) -> int:
    return {
        "saved": 0,
        "private": 1,
        "bot": 2,
        "group": 3,
        "supergroup": 4,
        "channel": 5,
        "unknown": 9,
    }.get(dialog_type, 9)


def _folder_matches_dialog(dialog_filter: Any, row: DialogInfo, entity: Any) -> bool:
    excluded = peer_ids(getattr(dialog_filter, "exclude_peers", None))
    if row.chat_id in excluded:
        return False

    included = peer_ids(getattr(dialog_filter, "include_peers", None))
    included.update(peer_ids(getattr(dialog_filter, "pinned_peers", None)))
    if row.chat_id in included:
        return True

    include_by_type = False
    if row.dialog_type in {"group", "supergroup"}:
        include_by_type = bool(getattr(dialog_filter, "groups", False))
    elif row.dialog_type == "channel":
        include_by_type = bool(getattr(dialog_filter, "broadcasts", False))
    elif row.dialog_type == "bot":
        include_by_type = bool(getattr(dialog_filter, "bots", False))
    elif row.dialog_type == "private":
        if bool(getattr(entity, "contact", False)):
            include_by_type = bool(getattr(dialog_filter, "contacts", False))
        else:
            include_by_type = bool(getattr(dialog_filter, "non_contacts", False))
    elif row.dialog_type == "saved":
        # Telegram custom folders do not expose a dedicated "self" flag. Self
        # is only considered a member when Telegram explicitly lists it.
        include_by_type = False

    if not include_by_type:
        return False
    if getattr(dialog_filter, "exclude_muted", False) and row.muted:
        return False
    if getattr(dialog_filter, "exclude_read", False) and not row.is_unread:
        return False
    if getattr(dialog_filter, "exclude_archived", False) and row.archived:
        return False
    return True


def _participant_user_id(participant: Any) -> int | None:
    for attr in ("user_id", "peer"):
        value = getattr(participant, attr, None)
        peer_id = _safe_peer_id(value)
        if peer_id is not None:
            return abs(peer_id) if peer_id > 0 else peer_id
    return None


def _participant_role(participant: Any) -> tuple[str, bool, bool, str | None]:
    name = type(participant).__name__
    creator = "Creator" in name
    admin = creator or "Admin" in name
    role = "owner" if creator else ("admin" if admin else "member")
    title = getattr(participant, "rank", None)
    return role, creator, admin, str(title) if title else None


def _participant_info(user: Any, participant: Any) -> ParticipantInfo:
    role, creator, admin, title = _participant_role(participant)
    return ParticipantInfo(
        user_id=int(getattr(user, "id", 0) or 0),
        display_name=_display_name(user),
        username=getattr(user, "username", None),
        role=role,
        is_creator=creator,
        is_admin=admin,
        admin_title=title,
        bot=bool(getattr(user, "bot", False)),
        deleted_account=bool(getattr(user, "deleted", False)),
    )


def _safe_rights(entity: Any, full_chat: Any = None) -> dict[str, bool | None]:
    rights = getattr(entity, "admin_rights", None)
    result: dict[str, bool | None] = {"creator": bool(getattr(entity, "creator", False))}
    for name in (
        "change_info",
        "post_messages",
        "edit_messages",
        "delete_messages",
        "ban_users",
        "invite_users",
        "pin_messages",
        "add_admins",
        "anonymous",
        "manage_call",
        "manage_topics",
        "post_stories",
        "edit_stories",
        "delete_stories",
    ):
        result[name] = bool(getattr(rights, name, False)) if rights is not None else None
    if full_chat is not None:
        for name in ("can_view_participants", "can_set_username", "can_set_stickers", "can_view_stats"):
            if hasattr(full_chat, name):
                result[name] = bool(getattr(full_chat, name, False))
    return result


def _map_bare_chat_id(result: Any, bare_id: Any) -> int | None:
    if bare_id in {None, 0}:
        return None
    try:
        wanted = int(bare_id)
    except (TypeError, ValueError):
        return None
    for entity in getattr(result, "chats", None) or ():
        if int(getattr(entity, "id", 0) or 0) == wanted:
            return _safe_peer_id(entity)
    return wanted


def _entity_payload(entity: Any) -> dict[str, Any]:
    name = type(entity).__name__
    payload: dict[str, Any] = {
        "type": name.removeprefix("MessageEntity"),
        "offset": int(getattr(entity, "offset", 0) or 0),
        "length": int(getattr(entity, "length", 0) or 0),
    }
    url = getattr(entity, "url", None)
    if isinstance(url, str):
        payload["url"] = url
    user_id = getattr(entity, "user_id", None)
    if isinstance(user_id, int):
        payload["user_id"] = user_id
    language = getattr(entity, "language", None)
    if isinstance(language, str):
        payload["language"] = language
    document_id = getattr(entity, "document_id", None)
    if isinstance(document_id, int):
        payload["custom_emoji_id"] = document_id
    return payload


def _reaction_key(reaction: Any) -> dict[str, Any]:
    if reaction is None:
        return {"type": "unknown"}
    name = type(reaction).__name__
    if hasattr(reaction, "emoticon"):
        return {"type": "emoji", "emoji": getattr(reaction, "emoticon", None)}
    if hasattr(reaction, "document_id"):
        return {"type": "custom_emoji", "custom_emoji_id": int(getattr(reaction, "document_id", 0) or 0)}
    return {"type": name.removeprefix("Reaction").casefold() or "unknown"}


def _reaction_payloads(message: Any) -> tuple[dict[str, Any], ...]:
    reactions = getattr(message, "reactions", None)
    if reactions is None:
        return ()
    recent_by_key: dict[str, list[int]] = {}
    for recent in getattr(reactions, "recent_reactions", None) or ():
        key = str(_reaction_key(getattr(recent, "reaction", None)))
        peer_id = _safe_peer_id(getattr(recent, "peer_id", None))
        if peer_id is not None:
            recent_by_key.setdefault(key, []).append(peer_id)
    rows = []
    for result in getattr(reactions, "results", None) or ():
        reaction = _reaction_key(getattr(result, "reaction", None))
        key = str(reaction)
        rows.append(
            {
                "reaction": reaction,
                "count": int(getattr(result, "count", 0) or 0),
                "chosen": getattr(result, "chosen_order", None) is not None,
                "recent_reactor_ids": recent_by_key.get(key, []),
            }
        )
    return tuple(rows)


def _poll_payload(message: Any) -> dict[str, Any] | None:
    media = getattr(message, "media", None)
    poll = getattr(media, "poll", None)
    if poll is None:
        return None
    question = getattr(poll, "question", None)
    question_text = getattr(question, "text", question)
    answers = []
    for answer in getattr(poll, "answers", None) or ():
        text = getattr(answer, "text", None)
        answers.append(
            {
                "text": getattr(text, "text", text),
                "option_hex": bytes(getattr(answer, "option", b"")).hex(),
            }
        )
    vote_by_option = {}
    results_obj = getattr(media, "results", None)
    for row in getattr(results_obj, "results", None) or ():
        option = bytes(getattr(row, "option", b"")).hex()
        vote_by_option[option] = {
            "voters": int(getattr(row, "voters", 0) or 0),
            "chosen": bool(getattr(row, "chosen", False)),
            "correct": bool(getattr(row, "correct", False)),
        }
    for answer in answers:
        answer.update(vote_by_option.get(answer["option_hex"], {}))
    return {
        "poll_id": int(getattr(poll, "id", 0) or 0),
        "question": question_text,
        "answers": answers,
        "closed": bool(getattr(poll, "closed", False)),
        "quiz": bool(getattr(poll, "quiz", False)),
        "public_voters": bool(getattr(poll, "public_voters", False)),
        "multiple_choice": bool(getattr(poll, "multiple_choice", False)),
        "total_voters": int(getattr(results_obj, "total_voters", 0) or 0),
    }


def _service_action_payload(message: Any) -> dict[str, Any] | None:
    action = getattr(message, "action", None)
    if action is None or type(action).__name__ == "MessageActionEmpty":
        return None
    payload: dict[str, Any] = {"action_type": type(action).__name__.removeprefix("MessageAction")}
    for attr in ("user_id", "channel_id", "chat_id", "message_id", "topic_id"):
        value = getattr(action, attr, None)
        if isinstance(value, int):
            payload[attr] = value
    users = getattr(action, "users", None)
    if users:
        payload["user_ids"] = [int(value) for value in users if isinstance(value, int)]
    return payload


def _forward_payload(message: Any) -> dict[str, Any] | None:
    header = getattr(message, "fwd_from", None)
    if header is None:
        return None
    from_peer = getattr(header, "from_id", None)
    origin_id = _safe_peer_id(from_peer)
    origin_name = getattr(header, "from_name", None)
    if origin_name:
        origin_type = "hidden_user"
    elif from_peer is None:
        origin_type = "unknown"
    else:
        peer_name = type(from_peer).__name__
        origin_type = "user" if peer_name == "PeerUser" else ("channel" if peer_name == "PeerChannel" else "chat")
    return {
        "origin_type": origin_type,
        "origin_id": origin_id,
        "hidden_name": origin_name if isinstance(origin_name, str) else None,
        "date": getattr(header, "date", None),
        "post_author": getattr(header, "post_author", None),
        "source_message_id": getattr(header, "channel_post", None),
        "saved_from_chat_id": _safe_peer_id(getattr(header, "saved_from_peer", None)),
        "saved_from_message_id": getattr(header, "saved_from_msg_id", None),
    }


def _media_metadata(message: Any) -> MediaMetadata | None:
    media = getattr(message, "media", None)
    if media is None or type(media).__name__ == "MessageMediaEmpty":
        return None
    cls = type(media).__name__
    media_type = cls.removeprefix("MessageMedia").casefold() or "unknown"
    if getattr(message, "photo", None) is not None:
        media_type = "photo"
    elif getattr(message, "voice", None) is not None:
        media_type = "voice"
    elif getattr(message, "video", None) is not None:
        media_type = "video"
    elif getattr(message, "audio", None) is not None:
        media_type = "audio"
    elif getattr(message, "sticker", None) is not None:
        media_type = "sticker"
    elif getattr(message, "gif", None) is not None:
        media_type = "gif"
    elif cls == "MessageMediaDocument":
        media_type = "document"
    elif cls == "MessageMediaWebPage":
        media_type = "webpage"
    elif cls == "MessageMediaPoll":
        media_type = "poll"

    file = getattr(message, "file", None)
    document = getattr(media, "document", None)
    photo = getattr(media, "photo", None)
    width = getattr(file, "width", None)
    height = getattr(file, "height", None)
    if (width is None or height is None) and photo is not None:
        sizes = getattr(photo, "sizes", None) or ()
        for size in reversed(sizes):
            if getattr(size, "w", None) and getattr(size, "h", None):
                width, height = int(size.w), int(size.h)
                break
    return MediaMetadata(
        media_type=media_type,
        filename=getattr(file, "name", None),
        mime_type=getattr(file, "mime_type", None) or getattr(document, "mime_type", None),
        size=(int(getattr(file, "size", 0) or 0) or int(getattr(document, "size", 0) or 0) or None),
        width=int(width) if width is not None else None,
        height=int(height) if height is not None else None,
        duration=float(getattr(file, "duration", 0) or 0) or None,
        document_id=(int(getattr(document, "id", 0) or 0) or None),
        photo_id=(int(getattr(photo, "id", 0) or 0) or None),
        spoiler=bool(getattr(media, "spoiler", False)),
    )


class PersonalAccountReader:
    """Read-only account facade over the daemon-owned TelegramService client."""

    def __init__(self, telegram_service: Any, *, cursor_codec: CursorCodec | None = None):
        self.telegram_service = telegram_service
        self.client = telegram_service.client
        self.cursor = cursor_codec or CursorCodec.from_local_identity()
        self._role_cache: dict[int, tuple[float, dict[int, ParticipantInfo], bool]] = {}

    async def account_profile(self) -> AccountProfile:
        me = await self.client.get_me()
        return AccountProfile(
            user_id=int(getattr(me, "id", 0) or 0),
            display_name=_display_name(me),
            username=getattr(me, "username", None),
            premium=bool(getattr(me, "premium", False)),
            bot=bool(getattr(me, "bot", False)),
            language_code=getattr(me, "lang_code", None),
        )

    async def _dialog_catalogue(self) -> tuple[list[DialogInfo], dict[int, Any]]:
        started = time.perf_counter()
        me = await self.client.get_me()
        own_user_id = int(getattr(me, "id", 0) or 0)
        rows: list[DialogInfo] = []
        entities: dict[int, Any] = {}
        migrated_from_by_target: dict[int, int] = {}

        async for dialog in self.client.iter_dialogs(limit=None, ignore_migrated=False):
            entity = dialog.entity
            chat_id = _safe_peer_id(entity)
            if chat_id is None:
                continue
            dialog_type = _entity_dialog_type(entity, own_user_id=own_user_id)
            target_id = _safe_peer_id(getattr(entity, "migrated_to", None))
            if target_id is not None:
                migrated_from_by_target[target_id] = chat_id
            unread_count = int(getattr(dialog, "unread_count", 0) or 0)
            unread_mark = bool(getattr(getattr(dialog, "dialog", None), "unread_mark", False))
            message = getattr(dialog, "message", None)
            row = DialogInfo(
                chat_id=chat_id,
                title=("Saved Messages" if dialog_type == "saved" else (getattr(dialog, "name", None) or _display_name(entity) or str(chat_id))),
                username=getattr(entity, "username", None),
                dialog_type=dialog_type,
                reference="me" if dialog_type == "saved" else None,
                unread_count=unread_count,
                pinned=bool(getattr(dialog, "pinned", False)),
                muted=_dialog_is_muted(dialog),
                archived=bool(getattr(dialog, "archived", False)),
                forum=bool(getattr(entity, "forum", False)),
                is_unread=bool(unread_count > 0 or unread_mark),
                is_contact=bool(getattr(entity, "contact", False)),
                migrated_to_chat_id=target_id,
                last_message_id=int(getattr(message, "id", 0) or 0),
                last_message_date=getattr(message, "date", None),
            )
            rows.append(row)
            entities[chat_id] = entity

        own_chat_id = own_user_id
        saved = next((row for row in rows if row.dialog_type == "saved"), None)
        if saved is None and own_user_id:
            saved = DialogInfo(
                chat_id=own_chat_id,
                title="Saved Messages",
                username=getattr(me, "username", None),
                dialog_type="saved",
                reference="me",
            )
            rows.append(saved)
            entities[own_chat_id] = me

        for row in rows:
            if row.chat_id in migrated_from_by_target:
                row.migrated_from_chat_id = migrated_from_by_target[row.chat_id]

        try:
            response = await self.client(functions.messages.GetDialogFiltersRequest())
            filters = getattr(response, "filters", response) or ()
            for order, dialog_filter in enumerate(filters):
                if type(dialog_filter).__name__ == "DialogFilterDefault":
                    continue
                title = filter_title(dialog_filter)
                folder_id = getattr(dialog_filter, "id", None)
                if not title or folder_id is None:
                    continue
                ref = FolderRef(folder_id=int(folder_id), title=title, order=order)
                for row in rows:
                    entity = entities.get(row.chat_id)
                    if entity is not None and _folder_matches_dialog(dialog_filter, row, entity):
                        row.folders = (*row.folders, ref)
        except Exception:
            logger.warning("Reader chat-folder load failed; returning dialogs without custom folder membership", exc_info=True)

        logger.info("Reader loaded dialog catalogue count=%s duration_ms=%s", len(rows), int((time.perf_counter() - started) * 1000))
        return rows, entities

    async def dialogs_page(
        self,
        *,
        dialog_type: str | None = None,
        folder: str | None = None,
        archived: str = "all",
        search: str | None = None,
        unread: str = "all",
        pinned: str = "all",
        cursor: str | None = None,
        limit: int = DEFAULT_PAGE_LIMIT,
    ) -> Page:
        limit = _validate_limit(limit)
        archived = _yes_no_all(archived, "archived")
        unread = _yes_no_all(unread, "unread")
        pinned = _yes_no_all(pinned, "pinned")
        allowed_types = {"group", "supergroup", "channel", "private", "bot", "saved"}
        if dialog_type and dialog_type not in allowed_types:
            raise TelegramBridgeError(INVALID_ARGUMENT, f"未知 dialog type：{dialog_type}")
        query = {
            "dialog_type": dialog_type,
            "folder": folder,
            "archived": archived,
            "search": search,
            "unread": unread,
            "pinned": pinned,
        }
        position = self.cursor.decode(cursor, "dialogs.list", query) or {}
        last_rank = int(position.get("rank", -1))
        last_id = int(position.get("chat_id", -(2**63)))

        network_started = time.perf_counter()
        rows, _ = await self._dialog_catalogue()
        network_ms = int((time.perf_counter() - network_started) * 1000)
        local_started = time.perf_counter()

        if dialog_type:
            rows = [row for row in rows if row.dialog_type == dialog_type]
        if folder:
            folder_key = str(folder).casefold()
            folder_id = int(folder) if str(folder).lstrip("-").isdigit() else None
            rows = [
                row for row in rows
                if any(
                    (folder_id is not None and ref.folder_id == folder_id)
                    or ref.title.casefold() == folder_key
                    for ref in row.folders
                )
            ]
        if archived != "all":
            wanted = archived == "yes"
            rows = [row for row in rows if row.archived is wanted]
        if unread != "all":
            wanted = unread == "yes"
            rows = [row for row in rows if row.is_unread is wanted]
        if pinned != "all":
            wanted = pinned == "yes"
            rows = [row for row in rows if row.pinned is wanted]
        if search:
            needle = search.casefold()
            rows = [row for row in rows if needle in row.title.casefold() or (row.username and needle in row.username.casefold())]

        rows.sort(key=lambda row: (_dialog_rank(row.dialog_type), row.chat_id))
        rows = [row for row in rows if (_dialog_rank(row.dialog_type), row.chat_id) > (last_rank, last_id)]
        chunk = rows[: limit + 1]
        has_more = len(chunk) > limit
        items = chunk[:limit]
        next_cursor = None
        if has_more and items:
            last = items[-1]
            next_cursor = self.cursor.encode(
                "dialogs.list",
                query,
                {"rank": _dialog_rank(last.dialog_type), "chat_id": last.chat_id},
            )
        local_ms = int((time.perf_counter() - local_started) * 1000)
        return Page(
            items=items,
            next_cursor=next_cursor,
            has_more=has_more,
            timing={"network_ms": network_ms, "local_filter_ms": local_ms, "serialization_ms": 0},
        )

    async def resolve_dialog(self, reference: str | int) -> tuple[DialogInfo, Any]:
        rows, entities = await self._dialog_catalogue()
        raw = str(reference).strip()
        if not raw:
            raise TelegramBridgeError(INVALID_ARGUMENT, "聊天标识不能为空。")
        if raw.casefold() == "me":
            matches = [row for row in rows if row.dialog_type == "saved"]
        elif raw.lstrip("-").isdigit():
            value = int(raw)
            matches = [row for row in rows if row.chat_id == value]
        else:
            username = raw[1:] if raw.startswith("@") else raw
            username_matches = [row for row in rows if row.username and row.username.casefold() == username.casefold()]
            if username_matches:
                matches = username_matches
            else:
                matches = [row for row in rows if row.title.casefold() == raw.casefold()]
        if not matches:
            raise TelegramBridgeError(CHAT_NOT_FOUND, f"找不到会话「{raw}」。")
        if len(matches) > 1:
            raise TelegramBridgeError(
                AMBIGUOUS_CHAT,
                f"会话标识「{raw}」对应多个候选，请改用 chat_id。",
                [
                    {"chat_id": row.chat_id, "title": row.title, "username": row.username, "type": row.dialog_type}
                    for row in matches
                ],
            )
        row = matches[0]
        entity = entities.get(row.chat_id)
        if entity is None:
            try:
                entity = await self.client.get_entity("me" if row.dialog_type == "saved" else row.chat_id)
            except Exception as exc:
                raise CursorCodec.stale("会话存在于目录，但 Telegram entity 已无法恢复。") from exc
        return row, entity

    async def _basic_chat_participants(self, entity: Any) -> tuple[list[ParticipantInfo], Any]:
        result = await self.client(functions.messages.GetFullChatRequest(chat_id=int(getattr(entity, "id", 0) or 0)))
        full_chat = getattr(result, "full_chat", None)
        participants_obj = getattr(full_chat, "participants", None)
        participant_rows = getattr(participants_obj, "participants", None) or ()
        users = {int(getattr(user, "id", 0) or 0): user for user in getattr(result, "users", None) or ()}
        rows: list[ParticipantInfo] = []
        for participant in participant_rows:
            user_id = _participant_user_id(participant)
            user = users.get(int(user_id or 0))
            if user is not None:
                rows.append(_participant_info(user, participant))
        rows.sort(key=lambda item: item.user_id)
        return rows, result

    async def _admin_snapshot(self, row: DialogInfo, entity: Any) -> tuple[dict[int, ParticipantInfo], bool]:
        cached = self._role_cache.get(row.chat_id)
        now = time.monotonic()
        if cached and now - cached[0] < ROLE_CACHE_TTL_SECONDS:
            return cached[1], cached[2]
        snapshot: dict[int, ParticipantInfo] = {}
        available = True
        try:
            if row.dialog_type == "group":
                participants, _ = await self._basic_chat_participants(entity)
                for item in participants:
                    if item.is_admin:
                        snapshot[item.user_id] = item
            elif row.dialog_type in {"supergroup", "channel"}:
                offset = 0
                scanned = 0
                while scanned < MAX_PAGE_LIMIT:
                    result = await self.client(
                        functions.channels.GetParticipantsRequest(
                            channel=entity,
                            filter=types.ChannelParticipantsAdmins(),
                            offset=offset,
                            limit=min(100, MAX_PAGE_LIMIT - scanned),
                            hash=0,
                        )
                    )
                    participants = list(getattr(result, "participants", None) or ())
                    users = {int(getattr(user, "id", 0) or 0): user for user in getattr(result, "users", None) or ()}
                    if not participants:
                        break
                    for participant in participants:
                        user_id = _participant_user_id(participant)
                        user = users.get(int(user_id or 0))
                        if user is not None:
                            item = _participant_info(user, participant)
                            if item.is_admin:
                                snapshot[item.user_id] = item
                    offset += len(participants)
                    scanned += len(participants)
                    if len(participants) < 100:
                        break
            else:
                available = False
        except RPCError:
            available = False
        self._role_cache[row.chat_id] = (now, snapshot, available)
        return snapshot, available

    async def members_page(
        self,
        chat: str | int,
        *,
        role: str | None = None,
        cursor: str | None = None,
        limit: int = DEFAULT_PAGE_LIMIT,
    ) -> Page:
        limit = _validate_limit(limit)
        if role not in {None, "owner", "admin", "member"}:
            raise TelegramBridgeError(INVALID_ARGUMENT, "role 只能是 owner/admin/member。")
        row, entity = await self.resolve_dialog(chat)
        if row.dialog_type not in {"group", "supergroup", "channel"}:
            raise TelegramBridgeError(MEMBERS_UNAVAILABLE, "该会话类型没有可枚举的群成员列表。")
        query = {"chat_id": row.chat_id, "role": role}
        position = self.cursor.decode(cursor, "chats.members", query) or {}
        network_started = time.perf_counter()
        local_started = time.perf_counter()

        try:
            if row.dialog_type == "group":
                all_rows, _ = await self._basic_chat_participants(entity)
                last_user_id = int(position.get("last_user_id", 0))
                filtered = [item for item in all_rows if item.user_id > last_user_id and (role is None or item.role == role)]
                chunk = filtered[: limit + 1]
                has_more = len(chunk) > limit
                items = chunk[:limit]
                next_cursor = None
                if has_more and items:
                    next_cursor = self.cursor.encode(
                        "chats.members", query, {"mode": "basic", "last_user_id": items[-1].user_id}
                    )
            else:
                offset = int(position.get("offset", 0))
                original_offset = offset
                items: list[ParticipantInfo] = []
                scanned = 0
                exhausted = False
                participant_filter = (
                    types.ChannelParticipantsAdmins()
                    if role in {"owner", "admin"}
                    else types.ChannelParticipantsSearch("")
                )
                while len(items) < limit and scanned < PARTICIPANT_SCAN_CAP:
                    batch_limit = min(100, max(1, limit - len(items)))
                    result = await self.client(
                        functions.channels.GetParticipantsRequest(
                            channel=entity,
                            filter=participant_filter,
                            offset=offset,
                            limit=batch_limit,
                            hash=0,
                        )
                    )
                    participants = list(getattr(result, "participants", None) or ())
                    users = {int(getattr(user, "id", 0) or 0): user for user in getattr(result, "users", None) or ()}
                    if not participants:
                        exhausted = True
                        break
                    for participant in participants:
                        info = None
                        user_id = _participant_user_id(participant)
                        user = users.get(int(user_id or 0))
                        if user is not None:
                            info = _participant_info(user, participant)
                        if info is not None and (role is None or info.role == role):
                            items.append(info)
                            if len(items) >= limit:
                                break
                    offset += len(participants)
                    scanned += len(participants)
                    if len(participants) < batch_limit:
                        exhausted = True
                        break

                # Probe bounded future candidates without consuming them in the cursor.
                has_more = False
                next_offset = offset
                if not exhausted:
                    probe_offset = offset
                    probe_scanned = scanned
                    while probe_scanned < PARTICIPANT_SCAN_CAP:
                        result = await self.client(
                            functions.channels.GetParticipantsRequest(
                                channel=entity,
                                filter=participant_filter,
                                offset=probe_offset,
                                limit=100,
                                hash=0,
                            )
                        )
                        participants = list(getattr(result, "participants", None) or ())
                        users = {int(getattr(user, "id", 0) or 0): user for user in getattr(result, "users", None) or ()}
                        if not participants:
                            break
                        if any(
                            (user := users.get(int(_participant_user_id(participant) or 0))) is not None
                            and (role is None or _participant_info(user, participant).role == role)
                            for participant in participants
                        ):
                            has_more = True
                            next_offset = probe_offset
                            break
                        probe_offset += len(participants)
                        probe_scanned += len(participants)
                        if len(participants) < 100:
                            break
                next_cursor = (
                    self.cursor.encode("chats.members", query, {"mode": "channel", "offset": next_offset})
                    if has_more
                    else None
                )
                scanned = max(scanned, offset - original_offset)
        except TelegramBridgeError:
            raise
        except RPCError as exc:
            code = type(exc).__name__
            raise TelegramBridgeError(
                MEMBERS_UNAVAILABLE,
                "Telegram 未向当前账号开放该会话的完整成员枚举。",
                {"telegram_error": code},
            ) from exc

        network_ms = int((time.perf_counter() - network_started) * 1000)
        local_ms = int((time.perf_counter() - local_started) * 1000)
        return Page(
            items=items,
            next_cursor=next_cursor,
            has_more=has_more,
            timing={"network_ms": network_ms, "local_filter_ms": local_ms, "serialization_ms": 0},
            scanned_count=(len(items) if row.dialog_type == "group" else scanned),
            matched_count=len(items),
        )

    async def chat_details(self, chat: str | int) -> ChatDetails:
        row, entity = await self.resolve_dialog(chat)
        description = None
        member_count = None
        linked_chat_id = None
        available_min_id = None
        pinned_message_id = None
        full_chat = None
        owner = None
        owner_visibility = "not_applicable"

        try:
            if row.dialog_type in {"supergroup", "channel"}:
                result = await self.client(functions.channels.GetFullChannelRequest(channel=entity))
                full_chat = getattr(result, "full_chat", None)
                description = getattr(full_chat, "about", None)
                member_count = getattr(full_chat, "participants_count", None)
                linked_chat_id = _map_bare_chat_id(result, getattr(full_chat, "linked_chat_id", None))
                available_min_id = getattr(full_chat, "available_min_id", None)
                pinned_message_id = getattr(full_chat, "pinned_msg_id", None)
            elif row.dialog_type == "group":
                participants, result = await self._basic_chat_participants(entity)
                full_chat = getattr(result, "full_chat", None)
                description = getattr(full_chat, "about", None)
                member_count = len(participants)
                pinned_message_id = getattr(full_chat, "pinned_msg_id", None)
            elif row.dialog_type in {"private", "bot", "saved"}:
                result = await self.client(functions.users.GetFullUserRequest(id=entity))
                full_chat = getattr(result, "full_user", None)
                description = getattr(full_chat, "about", None)
                pinned_message_id = getattr(full_chat, "pinned_msg_id", None)
        except RPCError as exc:
            raise TelegramBridgeError(
                ACCESS_DENIED,
                "Telegram 未向当前账号开放该会话的完整详情。",
                {"telegram_error": type(exc).__name__},
            ) from exc

        if row.dialog_type in {"group", "supergroup", "channel"}:
            snapshot, available = await self._admin_snapshot(row, entity)
            owner = next((item for item in snapshot.values() if item.is_creator), None)
            owner_visibility = "available" if owner is not None else ("not_found" if available else "unavailable")

        if member_count is None:
            raw_count = getattr(entity, "participants_count", None)
            member_count = int(raw_count) if isinstance(raw_count, int) else None
        return ChatDetails(
            chat_id=row.chat_id,
            title=row.title,
            username=row.username,
            chat_type=row.dialog_type,
            description=description if isinstance(description, str) else None,
            member_count=int(member_count) if isinstance(member_count, int) else None,
            owner=owner,
            owner_visibility=owner_visibility,
            current_account_rights=_safe_rights(entity, full_chat),
            forum=row.forum,
            migrated_from_chat_id=row.migrated_from_chat_id,
            migrated_to_chat_id=row.migrated_to_chat_id,
            linked_chat_id=linked_chat_id,
            available_min_id=int(available_min_id) if isinstance(available_min_id, int) else None,
            pinned_message_id=int(pinned_message_id) if isinstance(pinned_message_id, int) else None,
        )

    async def _sender_info(
        self,
        logical_row: DialogInfo,
        message: Any,
        role_snapshot: dict[int, ParticipantInfo],
        role_available: bool,
    ) -> SenderInfo:
        sender = getattr(message, "sender", None)
        if sender is None:
            try:
                sender = await message.get_sender()
            except Exception:
                sender = None
        sender_id = _safe_peer_id(sender)
        if sender_id is None:
            sender_id = _safe_peer_id(getattr(message, "from_id", None))
        sender_cls = type(sender).__name__ if sender is not None else ""
        posted_as = sender_id if sender_cls in {"Chat", "Channel"} else None
        anonymous = bool(
            posted_as is not None
            and logical_row.dialog_type in {"group", "supergroup"}
            and posted_as == logical_row.chat_id
        )
        if anonymous:
            sender_type = "anonymous_admin"
        elif sender_cls == "User" or (sender_id is not None and sender_id > 0):
            sender_type = "user"
        elif sender_cls == "Channel":
            sender_type = "channel"
        elif sender_cls == "Chat":
            sender_type = "chat"
        else:
            sender_type = "unknown"
        role = role_snapshot.get(int(sender_id or 0)) if sender_id is not None and sender_id > 0 else None
        return SenderInfo(
            sender_id=sender_id,
            sender_type=sender_type,
            display_name=_display_name(sender) or (getattr(message, "post_author", None) if anonymous else None),
            username=getattr(sender, "username", None),
            posted_as_chat_id=posted_as,
            is_creator=(role.is_creator if role is not None else (False if role_available and sender_id and sender_id > 0 else None)),
            is_admin=(role.is_admin if role is not None else (False if role_available and sender_id and sender_id > 0 else None)),
            admin_title=role.admin_title if role is not None else None,
            anonymous_admin=anonymous,
            via_bot_id=(int(getattr(message, "via_bot_id", 0) or 0) or None),
            role_basis="current_snapshot" if role_available else "unavailable",
        )

    async def _message_info_v3(
        self,
        logical_row: DialogInfo,
        source_chat_id: int,
        message: Any,
        role_snapshot: dict[int, ParticipantInfo],
        role_available: bool,
    ) -> MessageInfoV3:
        media = _media_metadata(message)
        raw_text = getattr(message, "message", None) or ""
        is_caption = media is not None and media.media_type not in {"webpage"}
        reply = getattr(message, "reply_to", None)
        reply_id = getattr(reply, "reply_to_msg_id", None)
        reply_top_id = getattr(reply, "reply_to_top_id", None)
        forum_topic_id = None
        if bool(getattr(reply, "forum_topic", False)):
            forum_topic_id = reply_top_id or reply_id
        return MessageInfoV3(
            chat_id=logical_row.chat_id,
            source_chat_id=source_chat_id,
            message_id=int(getattr(message, "id", 0) or 0),
            date=getattr(message, "date"),
            edit_date=getattr(message, "edit_date", None),
            sender=await self._sender_info(logical_row, message, role_snapshot, role_available),
            text=None if is_caption else raw_text,
            caption=raw_text if is_caption else None,
            entities=tuple(_entity_payload(entity) for entity in (getattr(message, "entities", None) or ())),
            reply_to_message_id=int(reply_id) if isinstance(reply_id, int) else None,
            reply_to_top_id=int(reply_top_id) if isinstance(reply_top_id, int) else None,
            forum_topic_id=int(forum_topic_id) if isinstance(forum_topic_id, int) else None,
            forward_origin=_forward_payload(message),
            grouped_id=(int(getattr(message, "grouped_id", 0) or 0) or None),
            views=(int(getattr(message, "views", 0)) if getattr(message, "views", None) is not None else None),
            forwards=(int(getattr(message, "forwards", 0)) if getattr(message, "forwards", None) is not None else None),
            reactions=_reaction_payloads(message),
            poll=_poll_payload(message),
            service_action=_service_action_payload(message),
            pinned=bool(getattr(message, "pinned", False)),
            media=media,
            availability="available",
        )

    async def _history_source(
        self,
        logical_row: DialogInfo,
        *,
        source_chat_id: int,
        before_message_id: int,
        limit: int,
        since: datetime | None,
        until: datetime | None,
        topic_id: int | None = None,
    ) -> tuple[list[MessageInfoV3], bool]:
        try:
            entity = await self.client.get_entity("me" if logical_row.dialog_type == "saved" else source_chat_id)
        except Exception as exc:
            raise CursorCodec.stale() from exc
        role_snapshot, role_available = await self._admin_snapshot(logical_row, entity) if logical_row.dialog_type in {"group", "supergroup", "channel"} else ({}, False)
        kwargs: dict[str, Any] = {
            "limit": limit + 1,
            "offset_id": before_message_id or 0,
        }
        if until is not None:
            kwargs["offset_date"] = until
        if topic_id is not None:
            kwargs["reply_to"] = int(topic_id)
        raw_rows = []
        async for message in self.client.iter_messages(entity, **kwargs):
            if not isinstance(message, Message):
                continue
            date = getattr(message, "date", None)
            if date is None:
                continue
            if until is not None and date >= until:
                continue
            if since is not None and date < since:
                break
            raw_rows.append(message)
            if len(raw_rows) >= limit + 1:
                break
        has_more = len(raw_rows) > limit
        raw_rows = raw_rows[:limit]
        rows = [
            await self._message_info_v3(logical_row, source_chat_id, message, role_snapshot, role_available)
            for message in raw_rows
        ]
        return rows, has_more

    async def messages_history_page(
        self,
        chat: str | int,
        *,
        cursor: str | None = None,
        limit: int = DEFAULT_PAGE_LIMIT,
        since: datetime | None = None,
        until: datetime | None = None,
        topic_id: int | None = None,
    ) -> Page:
        limit = _validate_limit(limit)
        if since and until and since >= until:
            raise TelegramBridgeError(INVALID_ARGUMENT, "since 必须早于 until。")
        row, _ = await self.resolve_dialog(chat)
        if row.migrated_to_chat_id is not None:
            # A reference to the legacy row resolves to the current logical chat.
            try:
                row, _ = await self.resolve_dialog(row.migrated_to_chat_id)
            except TelegramBridgeError:
                pass
        query = {
            "chat_id": row.chat_id,
            "since": since.isoformat() if since else None,
            "until": until.isoformat() if until else None,
            "topic_id": topic_id,
        }
        method = "topics.history" if topic_id is not None else "messages.history"
        position = self.cursor.decode(cursor, method, query) or {}
        segment = str(position.get("segment") or "current")
        before_id = int(position.get("before_message_id", 0) or 0)
        legacy_id = row.migrated_from_chat_id
        if segment not in {"current", "legacy"}:
            raise TelegramBridgeError(INVALID_ARGUMENT, "history cursor segment 无效。")
        if segment == "legacy" and legacy_id is None:
            raise CursorCodec.stale("cursor 指向 legacy segment，但迁移关系已不可用。")

        network_started = time.perf_counter()
        items: list[MessageInfoV3] = []
        next_position: dict[str, Any] | None = None
        has_more = False
        current_segment = segment
        current_before = before_id

        while len(items) < limit:
            source_id = row.chat_id if current_segment == "current" else int(legacy_id or 0)
            remaining = limit - len(items)
            rows, source_has_more = await self._history_source(
                row,
                source_chat_id=source_id,
                before_message_id=current_before,
                limit=remaining,
                since=since,
                until=until,
                topic_id=topic_id,
            )
            items.extend(rows)
            if source_has_more:
                has_more = True
                oldest = rows[-1].message_id if rows else current_before
                next_position = {"segment": current_segment, "before_message_id": oldest}
                break
            if current_segment == "current" and legacy_id is not None and topic_id is None:
                current_segment = "legacy"
                current_before = 0
                if len(items) >= limit:
                    has_more = True
                    next_position = {"segment": "legacy", "before_message_id": 0}
                    break
                continue
            break

        next_cursor = self.cursor.encode(method, query, next_position) if has_more and next_position else None
        network_ms = int((time.perf_counter() - network_started) * 1000)
        return Page(
            items=items,
            next_cursor=next_cursor,
            has_more=has_more,
            timing={"network_ms": network_ms, "local_filter_ms": 0, "serialization_ms": 0},
            scanned_count=len(items),
            matched_count=len(items),
        )

    async def messages_get_v3(self, chat: str | int, ids: list[int]) -> list[MessageInfoV3]:
        requested = tuple(dict.fromkeys(int(value) for value in ids))
        if not requested:
            raise TelegramBridgeError(INVALID_ARGUMENT, "至少需要一个 message_id。")
        row, entity = await self.resolve_dialog(chat)
        messages = await self.client.get_messages(entity, ids=list(requested))
        by_id = {int(message.id): message for message in messages if isinstance(message, Message)}
        missing = [message_id for message_id in requested if message_id not in by_id]
        if missing:
            raise TelegramBridgeError(
                MESSAGE_NOT_FOUND,
                "部分消息不存在或当前账号无权访问。",
                {"missing_ids": missing, "reason": "not_found_or_unavailable"},
            )
        role_snapshot, role_available = await self._admin_snapshot(row, entity) if row.dialog_type in {"group", "supergroup", "channel"} else ({}, False)
        return [
            await self._message_info_v3(row, row.chat_id, by_id[message_id], role_snapshot, role_available)
            for message_id in requested
        ]
