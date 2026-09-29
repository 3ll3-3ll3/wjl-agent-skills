from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from telethon import TelegramClient
from telethon.errors import FloodWaitError, SessionPasswordNeededError
from telethon.tl import functions
from telethon.tl.custom.message import Message
from telethon.utils import get_peer_id

from .avatar_cache import read_cached_avatar, write_cached_avatar
from .bridge_errors import (
    AMBIGUOUS_CHAT,
    CHAT_NOT_FOUND,
    CONTENT_PROTECTED,
    FLOOD_WAIT,
    INVALID_ARGUMENT,
    MESSAGE_NOT_FOUND,
    UNKNOWN_OUTCOME,
    UNSUPPORTED_MESSAGE,
    WRITE_FAILED,
    TelegramBridgeError,
)
from .dialog_filters import apply_folder_memberships
from .models import (
    AccountInfo,
    ForwardAlbumInfo,
    ForwardFailure,
    ForwardResult,
    ForwardedMessageRef,
    GroupInfo,
    SendResult,
    TelegramMessageInfo,
)
from .proxy import ProxyConfig, detect_windows_system_proxy
from .session_lock import SessionLease

logger = logging.getLogger("telegram_exporter.telegram_service")

TELEGRAM_ALBUM_MAX_ITEMS = 10
TELEGRAM_FORWARD_RPC_LIMIT = 100
MAX_FORWARD_EXPANDED_ITEMS = 200
ALBUM_INCOMPLETE = "ALBUM_INCOMPLETE"
ALBUM_UNSUPPORTED_MEDIA = "ALBUM_UNSUPPORTED_MEDIA"
SERVICE_MESSAGE = "SERVICE_MESSAGE"


@dataclass(slots=True)
class ApiCredentials:
    api_id: int
    api_hash: str


@dataclass(frozen=True, slots=True)
class _ForwardUnit:
    message_ids: tuple[int, ...]
    grouped_id: int | None
    photo_count: int


def _dialog_is_muted(dialog) -> bool:
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


def _entity_has_photo(entity) -> bool:
    photo = getattr(entity, "photo", None)
    return photo is not None and photo.__class__.__name__ not in {"ChatPhotoEmpty", "UserProfilePhotoEmpty"}


def _migrated_target_peer_id(entity) -> int | None:
    migrated_to = getattr(entity, "migrated_to", None)
    if migrated_to is None:
        return None
    try:
        return int(get_peer_id(migrated_to))
    except (TypeError, ValueError):
        return None


def _chat_type(entity, dialog) -> str:
    if entity.__class__.__name__ == "Channel":
        return "supergroup" if bool(getattr(entity, "megagroup", False) or dialog.is_group) else "channel"
    return "group" if dialog.is_group else "channel"


def _sender_label(sender) -> str | None:
    if sender is None:
        return None
    name = " ".join(
        part for part in [getattr(sender, "first_name", None), getattr(sender, "last_name", None)] if part
    ).strip()
    return name or getattr(sender, "title", None) or getattr(sender, "username", None)


def _chat_candidate(group: GroupInfo) -> dict:
    return {
        "chat_id": group.chat_id,
        "title": group.title,
        "username": group.username,
        "type": group.chat_type,
    }


def _grouped_id(message: Message) -> int | None:
    value = getattr(message, "grouped_id", None)
    return int(value) if value is not None else None


def _is_photo(message: Message) -> bool:
    media = getattr(message, "media", None)
    if media is not None and media.__class__.__name__ == "MessageMediaPhoto":
        return True
    return getattr(message, "photo", None) is not None


def _forwardable_kind(message: Message, *, source_protected: bool = False) -> tuple[str | None, str | None]:
    """只基于 Telegram 原始消息类型决定是否可做原生服务端转发。"""
    if getattr(message, "action", None) is not None:
        return None, SERVICE_MESSAGE
    if source_protected or bool(getattr(message, "noforwards", False)):
        return None, CONTENT_PROTECTED
    if _is_photo(message):
        return "photo", None
    media = getattr(message, "media", None)
    if (message.message or "") and (
        media is None or media.__class__.__name__ in {"MessageMediaEmpty", "MessageMediaWebPage"}
    ):
        return "text", None
    return None, UNSUPPORTED_MESSAGE


def _as_messages(value) -> list[Message]:
    if isinstance(value, Message):
        return [value]
    if value is None:
        return []
    try:
        return [item for item in value if isinstance(item, Message)]
    except TypeError:
        return []


def _chunk_forward_units(units: list[_ForwardUnit]) -> list[tuple[int, ...]]:
    chunks: list[tuple[int, ...]] = []
    current: list[int] = []
    for unit in units:
        if len(unit.message_ids) > TELEGRAM_FORWARD_RPC_LIMIT:
            raise TelegramBridgeError(
                INVALID_ARGUMENT,
                "单个相册超过 Telegram 原生 forward 批次上限。",
                {"grouped_id": unit.grouped_id, "count": len(unit.message_ids)},
            )
        if current and len(current) + len(unit.message_ids) > TELEGRAM_FORWARD_RPC_LIMIT:
            chunks.append(tuple(current))
            current = []
        current.extend(unit.message_ids)
    if current:
        chunks.append(tuple(current))
    return chunks


class TelegramService:
    def __init__(self, credentials: ApiCredentials, session_file: Path):
        self.proxy: ProxyConfig | None = detect_windows_system_proxy()
        self._session_lease = SessionLease(session_file)
        self._session_lease.acquire()
        proxy_payload = self.proxy.as_telethon_dict() if self.proxy else None
        try:
            self.client = TelegramClient(
                str(session_file),
                credentials.api_id,
                credentials.api_hash,
                proxy=proxy_payload,
            )
        except Exception:
            self._session_lease.release()
            raise
        # api_id/api_hash are credentials for this product's threat model and
        # must not enter ordinary logs. A safe session basename and proxy label
        # are enough for diagnostics.
        logger.info(
            "Telegram client initialized (session=%s, proxy=%s)",
            session_file.name,
            self.proxy.safe_label if self.proxy else "direct",
        )

    async def connect(self) -> bool:
        logger.info(
            "Connecting to Telegram transport via %s",
            self.proxy.safe_label if self.proxy else "direct connection",
        )
        try:
            await self.client.connect()
            authorized = await self.client.is_user_authorized()
            logger.info("Telegram transport connected; authorized=%s", authorized)
            return authorized
        except Exception:
            logger.exception("Telegram transport connection failed")
            raise

    async def send_code(self, phone: str) -> None:
        logger.info("Requesting Telegram login code")
        try:
            await self.client.send_code_request(phone)
            logger.info("Telegram login code request accepted")
        except Exception:
            logger.exception("Telegram login code request failed")
            raise

    async def sign_in_code(self, phone: str, code: str) -> bool:
        logger.info("Submitting Telegram login code")
        try:
            await self.client.sign_in(phone=phone, code=code)
        except SessionPasswordNeededError:
            logger.info("Telegram account requires 2FA password")
            return False
        except Exception:
            logger.exception("Telegram login code verification failed")
            raise
        logger.info("Telegram login code verified")
        return True

    async def sign_in_password(self, password: str) -> None:
        logger.info("Submitting Telegram 2FA password")
        try:
            await self.client.sign_in(password=password)
            logger.info("Telegram 2FA verification succeeded")
        except Exception:
            logger.exception("Telegram 2FA verification failed")
            raise

    async def account_info(self) -> AccountInfo:
        me = await self.client.get_me()
        display_name = _sender_label(me)
        return AccountInfo(
            user_id=int(getattr(me, "id", 0) or 0),
            display_name=display_name,
            username=getattr(me, "username", None),
        )

    async def list_groups(self) -> list[GroupInfo]:
        logger.info("Loading Telegram dialogs")
        groups: list[GroupInfo] = []
        eligible_dialogs = []
        try:
            async for dialog in self.client.iter_dialogs():
                if dialog.is_group or dialog.is_channel:
                    eligible_dialogs.append(dialog)
        except Exception:
            logger.exception("Loading Telegram dialogs failed")
            raise

        migrated_from_by_target: dict[int, int] = {}
        for dialog in eligible_dialogs:
            entity = dialog.entity
            target_id = _migrated_target_peer_id(entity)
            if target_id is not None:
                migrated_from_by_target[target_id] = int(get_peer_id(entity))
                continue

            unread_count = int(dialog.unread_count or 0)
            unread_mark = bool(getattr(dialog.dialog, "unread_mark", False))
            groups.append(
                GroupInfo(
                    chat_id=int(get_peer_id(entity)),
                    title=dialog.name or str(get_peer_id(entity)),
                    username=getattr(entity, "username", None),
                    chat_type=_chat_type(entity, dialog),
                    unread_count=unread_count,
                    read_inbox_max_id=int(getattr(dialog.dialog, "read_inbox_max_id", 0) or 0),
                    latest_message_id=int(getattr(dialog.message, "id", 0) or 0),
                    has_photo=_entity_has_photo(entity),
                    is_group=bool(dialog.is_group),
                    is_broadcast=bool(dialog.is_channel and not dialog.is_group),
                    is_muted=_dialog_is_muted(dialog),
                    is_archived=bool(getattr(dialog, "archived", False)),
                    is_unread=bool(unread_count > 0 or unread_mark),
                )
            )

        collapsed = 0
        for group in groups:
            old_id = migrated_from_by_target.get(group.chat_id)
            if old_id is not None:
                group.migrated_from_chat_id = old_id
                collapsed += 1
        if migrated_from_by_target:
            logger.info(
                "Collapsed %s migrated legacy basic-group rows; %s matched current supergroups",
                len(migrated_from_by_target),
                collapsed,
            )

        try:
            response = await self.client(functions.messages.GetDialogFiltersRequest())
            filters = getattr(response, "filters", response)
            folder_count = apply_folder_memberships(groups, filters or ())
            logger.info("Loaded %s Telegram chat folders containing eligible groups/channels", folder_count)
        except Exception:
            logger.warning("Loading Telegram chat folders failed; continuing with full catalogue", exc_info=True)

        groups.sort(key=lambda x: x.title.casefold())
        logger.info("Loaded %s groups/channels", len(groups))
        return groups

    async def resolve_group(self, reference: str | int, groups: list[GroupInfo] | None = None) -> GroupInfo:
        catalogue = groups if groups is not None else await self.list_groups()
        raw = str(reference).strip()
        if not raw:
            raise TelegramBridgeError(INVALID_ARGUMENT, "聊天标识不能为空。")

        numeric = raw.lstrip("-").isdigit()
        if numeric:
            chat_id = int(raw)
            for group in catalogue:
                if group.chat_id == chat_id:
                    return group
            raise TelegramBridgeError(CHAT_NOT_FOUND, f"找不到 chat_id={chat_id} 的群组/频道。")

        username = raw[1:] if raw.startswith("@") else raw
        username_matches = [g for g in catalogue if g.username and g.username.casefold() == username.casefold()]
        if len(username_matches) == 1:
            return username_matches[0]
        if len(username_matches) > 1:
            raise TelegramBridgeError(
                AMBIGUOUS_CHAT,
                f"聊天标识「{raw}」对应多个候选。请改用 chat_id。",
                [_chat_candidate(g) for g in username_matches],
            )

        title_matches = [g for g in catalogue if g.title.casefold() == raw.casefold()]
        if len(title_matches) == 1:
            return title_matches[0]
        if len(title_matches) > 1:
            raise TelegramBridgeError(
                AMBIGUOUS_CHAT,
                f"群名「{raw}」对应多个聊天。请改用 chat_id。",
                [_chat_candidate(g) for g in title_matches],
            )
        raise TelegramBridgeError(CHAT_NOT_FOUND, f"找不到群组/频道「{raw}」。")

    async def _message_info(self, group: GroupInfo, message: Message) -> TelegramMessageInfo:
        sender = await message.get_sender()
        return TelegramMessageInfo(
            chat_id=group.chat_id,
            chat_title=group.title,
            message_id=int(message.id),
            date=message.date,
            sender=_sender_label(sender),
            text=message.message or "",
        )

    async def search_messages(
        self,
        chat: str | int,
        *,
        contains: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 100,
        case_sensitive: bool = False,
    ) -> list[TelegramMessageInfo]:
        if limit <= 0:
            raise TelegramBridgeError(INVALID_ARGUMENT, "limit 必须大于 0。")
        if since and until and since >= until:
            raise TelegramBridgeError(INVALID_ARGUMENT, "since 必须早于 until。")

        groups = await self.list_groups()
        group = await self.resolve_group(chat, groups)
        entity = await self.client.get_entity(group.chat_id)
        kwargs: dict = {}
        if contains:
            kwargs["search"] = contains
        if until:
            kwargs["offset_date"] = until

        needle = contains if case_sensitive else (contains.casefold() if contains else None)
        results: list[TelegramMessageInfo] = []
        async for message in self.client.iter_messages(entity, limit=None, **kwargs):
            if not isinstance(message, Message):
                continue
            date = message.date
            if until and date >= until:
                continue
            if since and date < since:
                break
            text = message.message or ""
            if not text:
                continue
            if needle:
                haystack = text if case_sensitive else text.casefold()
                if needle not in haystack:
                    continue
            results.append(await self._message_info(group, message))
            if len(results) >= limit:
                break
        results.sort(key=lambda item: (item.date, item.message_id))
        return results

    async def get_messages(self, chat: str | int, ids: Iterable[int]) -> list[TelegramMessageInfo]:
        requested = tuple(dict.fromkeys(int(value) for value in ids))
        if not requested:
            raise TelegramBridgeError(INVALID_ARGUMENT, "至少需要一个 message_id。")
        groups = await self.list_groups()
        group = await self.resolve_group(chat, groups)
        entity = await self.client.get_entity(group.chat_id)
        messages = await self.client.get_messages(entity, ids=list(requested))
        by_id = {
            int(message.id): message
            for message in messages
            if isinstance(message, Message)
        }
        missing = [message_id for message_id in requested if message_id not in by_id]
        if missing:
            raise TelegramBridgeError(
                MESSAGE_NOT_FOUND,
                "部分消息不存在或当前账号无权访问。",
                {"missing_ids": missing},
            )
        return [await self._message_info(group, by_id[message_id]) for message_id in requested]

    async def _album_members(self, source_entity, seed: Message) -> list[Message]:
        grouped_id = _grouped_id(seed)
        if grouped_id is None:
            return [seed]
        seed_id = int(seed.id)
        low = max(1, seed_id - TELEGRAM_ALBUM_MAX_ITEMS)
        high = seed_id + TELEGRAM_ALBUM_MAX_ITEMS
        nearby = await self.client.get_messages(source_entity, ids=list(range(low, high + 1)))
        members = {
            int(message.id): message
            for message in _as_messages(nearby)
            if _grouped_id(message) == grouped_id
        }
        members[seed_id] = seed
        return [members[message_id] for message_id in sorted(members)]

    async def _latest_message_id(self, destination_entity) -> int | None:
        try:
            latest = await self.client.get_messages(destination_entity, limit=1)
        except Exception:
            return None
        rows = _as_messages(latest)
        ids = [int(getattr(message, "id", 0) or 0) for message in rows]
        ids = [message_id for message_id in ids if message_id > 0]
        return max(ids) if ids else None

    async def forward_messages(
        self,
        source_chat: str | int,
        destination_chat: str | int,
        ids: Iterable[int],
        *,
        dry_run: bool = False,
    ) -> ForwardResult:
        requested = tuple(dict.fromkeys(int(value) for value in ids))
        if not requested:
            raise TelegramBridgeError(INVALID_ARGUMENT, "至少需要一个 message_id。")
        groups = await self.list_groups()
        source = await self.resolve_group(source_chat, groups)
        source_entity = await self.client.get_entity(source.chat_id)

        destination_raw = str(destination_chat).strip()
        if destination_raw.casefold() == "me":
            destination_entity = "me"
            destination_id: int | str = "me"
        else:
            destination = await self.resolve_group(destination_raw, groups)
            destination_entity = await self.client.get_entity(destination.chat_id)
            destination_id = destination.chat_id

        messages = await self.client.get_messages(source_entity, ids=list(requested))
        by_id = {int(message.id): message for message in _as_messages(messages)}
        source_protected = bool(getattr(source_entity, "noforwards", False))
        processed_groups: set[int] = set()
        units: list[_ForwardUnit] = []
        albums: list[ForwardAlbumInfo] = []
        excluded_by_id: dict[int, ForwardFailure] = {}
        excluded_order: list[int] = []

        def exclude(message_id: int, reason: str, grouped_id: int | None = None) -> None:
            if message_id in excluded_by_id:
                return
            excluded_by_id[message_id] = ForwardFailure(
                message_id=message_id,
                reason=reason,
                grouped_id=grouped_id,
            )
            excluded_order.append(message_id)

        for message_id in requested:
            message = by_id.get(message_id)
            if message is None:
                exclude(message_id, MESSAGE_NOT_FOUND)
                continue

            grouped_id = _grouped_id(message)
            if grouped_id is None:
                kind, reason = _forwardable_kind(message, source_protected=source_protected)
                if reason is not None:
                    exclude(message_id, reason)
                    continue
                units.append(
                    _ForwardUnit(
                        message_ids=(message_id,),
                        grouped_id=None,
                        photo_count=1 if kind == "photo" else 0,
                    )
                )
                continue

            if grouped_id in processed_groups:
                continue
            processed_groups.add(grouped_id)
            members = await self._album_members(source_entity, message)
            member_ids = tuple(int(item.id) for item in members)
            expected_ids = tuple(range(member_ids[0], member_ids[-1] + 1)) if member_ids else ()
            if (
                len(member_ids) < 2
                or len(member_ids) > TELEGRAM_ALBUM_MAX_ITEMS
                or member_ids != expected_ids
            ):
                for member_id in member_ids or (message_id,):
                    exclude(member_id, ALBUM_INCOMPLETE, grouped_id)
                continue

            classifications = [
                _forwardable_kind(item, source_protected=source_protected)
                for item in members
            ]
            reasons = [reason for _, reason in classifications if reason is not None]
            kinds = [kind for kind, reason in classifications if reason is None]
            if CONTENT_PROTECTED in reasons:
                album_reason = CONTENT_PROTECTED
            elif reasons or any(kind != "photo" for kind in kinds):
                album_reason = ALBUM_UNSUPPORTED_MEDIA
            else:
                album_reason = None

            if album_reason is not None:
                for member_id in member_ids:
                    exclude(member_id, album_reason, grouped_id)
                continue

            units.append(
                _ForwardUnit(
                    message_ids=member_ids,
                    grouped_id=grouped_id,
                    photo_count=len(member_ids),
                )
            )
            albums.append(ForwardAlbumInfo(grouped_id=grouped_id, message_ids=member_ids))

        planned_ids = tuple(message_id for unit in units for message_id in unit.message_ids)
        if len(planned_ids) > MAX_FORWARD_EXPANDED_ITEMS:
            raise TelegramBridgeError(
                INVALID_ARGUMENT,
                "相册补全后的原生 forward 消息数量超过 200 条安全上限。",
                {
                    "requested_count": len(requested),
                    "expanded_count": len(planned_ids),
                    "limit": MAX_FORWARD_EXPANDED_ITEMS,
                },
            )
        planned_set = set(planned_ids)
        failed_ids = tuple(message_id for message_id in requested if message_id not in planned_set)
        excluded = tuple(excluded_by_id[message_id] for message_id in excluded_order)
        photo_count = sum(unit.photo_count for unit in units)

        if dry_run:
            logger.info(
                "Telegram write dry-run: forward requested=%s forwardable=%s photos=%s albums=%s excluded=%s",
                len(requested),
                len(planned_ids),
                photo_count,
                len(albums),
                len(excluded),
            )
            return ForwardResult(
                source_chat_id=source.chat_id,
                destination_chat_id=destination_id,
                requested_ids=requested,
                successful_ids=planned_ids,
                failed_ids=failed_ids,
                dry_run=True,
                planned_ids=planned_ids,
                requested_count=len(requested),
                forwardable_count=len(planned_ids),
                photo_count=photo_count,
                album_count=len(albums),
                albums=tuple(albums),
                excluded=excluded,
            )

        if not planned_ids:
            return ForwardResult(
                source_chat_id=source.chat_id,
                destination_chat_id=destination_id,
                requested_ids=requested,
                successful_ids=(),
                failed_ids=failed_ids,
                dry_run=False,
                planned_ids=(),
                requested_count=len(requested),
                forwardable_count=0,
                photo_count=0,
                album_count=0,
                albums=(),
                excluded=excluded,
            )

        before_id = await self._latest_message_id(destination_entity)
        grouped_by_source = {
            message_id: unit.grouped_id
            for unit in units
            for message_id in unit.message_ids
        }
        confirmed_source_ids: list[int] = []
        destination_message_ids: list[int] = []
        forwarded_messages: list[ForwardedMessageRef] = []
        chunks = _chunk_forward_units(units)
        logger.info(
            "Telegram write: native forward requested=%s planned=%s photos=%s albums=%s rpc_batches=%s",
            len(requested),
            len(planned_ids),
            photo_count,
            len(albums),
            len(chunks),
        )

        for index, chunk in enumerate(chunks):
            try:
                result = await self.client.forward_messages(
                    destination_entity,
                    list(chunk),
                    from_peer=source_entity,
                )
            except FloodWaitError as exc:
                seconds = int(getattr(exc, "seconds", 0) or 0)
                raise TelegramBridgeError(
                    FLOOD_WAIT,
                    f"Telegram 要求等待 {seconds} 秒后再试。" if seconds else "Telegram 触发 Flood Wait。",
                    {
                        "retry_after_seconds": seconds,
                        "confirmed_source_ids": confirmed_source_ids,
                        "not_attempted_source_ids": [
                            message_id
                            for later in chunks[index:]
                            for message_id in later
                        ],
                    },
                ) from exc
            except Exception as exc:
                if type(exc).__name__ == "ChatForwardsRestrictedError":
                    protected_ids = [
                        message_id
                        for later in chunks[index:]
                        for message_id in later
                    ]
                    merged_excluded = list(excluded)
                    known = {item.message_id for item in merged_excluded}
                    for protected_id in protected_ids:
                        if protected_id not in known:
                            merged_excluded.append(
                                ForwardFailure(
                                    message_id=protected_id,
                                    reason=CONTENT_PROTECTED,
                                    grouped_id=grouped_by_source.get(protected_id),
                                )
                            )
                    requested_failed = tuple(
                        message_id
                        for message_id in requested
                        if message_id not in set(confirmed_source_ids)
                    )
                    after_id = await self._latest_message_id(destination_entity)
                    return ForwardResult(
                        source_chat_id=source.chat_id,
                        destination_chat_id=destination_id,
                        requested_ids=requested,
                        successful_ids=tuple(confirmed_source_ids),
                        failed_ids=requested_failed,
                        dry_run=False,
                        planned_ids=planned_ids,
                        requested_count=len(requested),
                        forwardable_count=len(planned_ids),
                        photo_count=photo_count,
                        album_count=len(albums),
                        albums=tuple(albums),
                        excluded=tuple(merged_excluded),
                        destination_message_ids=tuple(destination_message_ids),
                        forwarded_messages=tuple(forwarded_messages),
                        destination_before_message_id=before_id,
                        destination_after_message_id=after_id,
                    )
                if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
                    uncertain = list(chunk)
                    not_attempted = [
                        message_id
                        for later in chunks[index + 1 :]
                        for message_id in later
                    ]
                    raise TelegramBridgeError(
                        UNKNOWN_OUTCOME,
                        "Telegram 原生转发请求已发出，但写入结果无法确认；请先检查目标聊天，勿自动重试。",
                        {
                            "confirmed_source_ids": confirmed_source_ids,
                            "confirmed_destination_ids": destination_message_ids,
                            "uncertain_source_ids": uncertain,
                            "not_attempted_source_ids": not_attempted,
                        },
                    ) from exc
                raise TelegramBridgeError(
                    WRITE_FAILED,
                    f"Telegram 转发失败：{type(exc).__name__}",
                    {
                        "confirmed_source_ids": confirmed_source_ids,
                        "confirmed_destination_ids": destination_message_ids,
                    },
                ) from exc

            returned = _as_messages(result)
            returned_ids = [int(getattr(message, "id", 0) or 0) for message in returned]
            if len(returned_ids) != len(chunk) or any(message_id <= 0 for message_id in returned_ids):
                raise TelegramBridgeError(
                    UNKNOWN_OUTCOME,
                    "Telegram 已返回原生转发结果，但目标消息 ID 不完整；请先检查目标聊天，勿自动重试。",
                    {
                        "confirmed_source_ids": confirmed_source_ids,
                        "confirmed_destination_ids": destination_message_ids,
                        "uncertain_source_ids": list(chunk),
                        "returned_destination_ids": [message_id for message_id in returned_ids if message_id > 0],
                        "not_attempted_source_ids": [
                            message_id
                            for later in chunks[index + 1 :]
                            for message_id in later
                        ],
                    },
                )

            confirmed_source_ids.extend(chunk)
            destination_message_ids.extend(returned_ids)
            forwarded_messages.extend(
                ForwardedMessageRef(
                    source_message_id=source_id,
                    destination_message_id=destination_message_id,
                    grouped_id=grouped_by_source.get(source_id),
                )
                for source_id, destination_message_id in zip(chunk, returned_ids, strict=True)
            )

        after_id = await self._latest_message_id(destination_entity)
        logger.info(
            "Telegram write succeeded: native forward forwarded=%s photos=%s albums=%s",
            len(confirmed_source_ids),
            photo_count,
            len(albums),
        )
        return ForwardResult(
            source_chat_id=source.chat_id,
            destination_chat_id=destination_id,
            requested_ids=requested,
            successful_ids=tuple(confirmed_source_ids),
            failed_ids=failed_ids,
            dry_run=False,
            planned_ids=planned_ids,
            requested_count=len(requested),
            forwardable_count=len(planned_ids),
            photo_count=photo_count,
            album_count=len(albums),
            albums=tuple(albums),
            excluded=excluded,
            destination_message_ids=tuple(destination_message_ids),
            forwarded_messages=tuple(forwarded_messages),
            destination_before_message_id=before_id,
            destination_after_message_id=after_id,
        )

    async def send_text_message(self, destination_chat: str | int, text: str, *, dry_run: bool = False) -> SendResult:
        if not text:
            raise TelegramBridgeError(INVALID_ARGUMENT, "发送文本不能为空。")
        groups = await self.list_groups()
        destination_raw = str(destination_chat).strip()
        if destination_raw.casefold() == "me":
            destination_entity = "me"
            destination_id: int | str = "me"
        else:
            destination = await self.resolve_group(destination_raw, groups)
            destination_entity = await self.client.get_entity(destination.chat_id)
            destination_id = destination.chat_id

        if dry_run:
            logger.info(
                "Telegram write dry-run: send destination_chat_id=%s text_length=%s",
                destination_id,
                len(text),
            )
            return SendResult(destination_chat_id=destination_id, message_id=None, text_length=len(text), dry_run=True)

        logger.info("Telegram write: send destination_chat_id=%s text_length=%s", destination_id, len(text))
        message = await self.client.send_message(destination_entity, text, parse_mode=None, link_preview=False)
        message_id = int(getattr(message, "id", 0) or 0)
        logger.info("Telegram write succeeded: send destination_chat_id=%s message_id=%s", destination_id, message_id)
        return SendResult(
            destination_chat_id=destination_id,
            message_id=message_id or None,
            text_length=len(text),
            dry_run=False,
        )

    async def group_avatar_bytes(self, group: GroupInfo) -> bytes | None:
        cached = read_cached_avatar(group.chat_id)
        if cached is not None:
            return cached
        if not group.has_photo:
            return None

        try:
            entity = await self.client.get_entity(group.chat_id)
            data = await self.client.download_profile_photo(entity, file=bytes, download_big=False)
            if isinstance(data, bytes) and data:
                write_cached_avatar(group.chat_id, data)
                return data
        except Exception:
            logger.warning("Loading selector avatar failed for chat_id=%s", group.chat_id, exc_info=True)
        return None

    async def close(self) -> None:
        lease = getattr(self, "_session_lease", None)
        try:
            client = getattr(self, "client", None)
            if client is None or not client.is_connected():
                return
            logger.info("Disconnecting Telegram client")
            result = client.disconnect()
            if inspect.isawaitable(result):
                await result
            logger.info("Telegram client disconnected")
        finally:
            if lease is not None:
                lease.release()
