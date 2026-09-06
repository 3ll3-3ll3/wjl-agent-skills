from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import replace
from typing import Any, Iterator

from telethon.errors import RPCError
from telethon.tl import functions, types
from telethon.tl.custom.message import Message

from .bridge_errors import INVALID_ARGUMENT, MESSAGE_NOT_FOUND, TelegramBridgeError
from .reader_models import ChatDetails, DialogInfo, MessageInfoV3, ParticipantInfo, SenderInfo
from .reader_service import (
    MAX_PAGE_LIMIT,
    PersonalAccountReader,
    _display_name,
    _participant_info,
    _participant_user_id,
    _safe_peer_id,
)


def _peer_kind(value: Any) -> str | None:
    name = type(value).__name__ if value is not None else ""
    if name in {"User", "PeerUser"}:
        return "user"
    if name in {"Channel", "PeerChannel"}:
        return "channel"
    if name in {"Chat", "PeerChat"}:
        return "chat"
    return None


def _raw_peer_id(value: Any) -> int | None:
    """Return a marked peer id for Telegram-provided sender peer fields.

    ``_safe_peer_id`` remains the normal entity path. This helper only adds
    deterministic fallbacks for raw Peer* constructors that may not be fully
    hydrated in a Telethon Message.
    """

    peer_id = _safe_peer_id(value)
    if peer_id is not None:
        return peer_id
    name = type(value).__name__ if value is not None else ""
    if name == "PeerUser":
        raw = getattr(value, "user_id", None)
        return int(raw) if isinstance(raw, int) and raw else None
    if name == "PeerChat":
        raw = getattr(value, "chat_id", None)
        return -int(raw) if isinstance(raw, int) and raw else None
    if name == "PeerChannel":
        raw = getattr(value, "channel_id", None)
        return -(1_000_000_000_000 + int(raw)) if isinstance(raw, int) and raw else None
    return None


def _owner_rpc_visibility(error_name: str) -> str:
    if error_name in {
        "ChatAdminRequiredError",
        "AdminRightsRequiredError",
        "UserAdminInvalidError",
    }:
        return "insufficient_permissions"
    if error_name in {
        "ChannelPrivateError",
        "ChatForbiddenError",
        "UserNotParticipantError",
    }:
        return "participants_unavailable"
    return "telegram_not_returned"


class PersonalAccountReaderV3(PersonalAccountReader):
    """Production reader with v0.3.x logical identity and sender fixes."""

    def __init__(self, telegram_service: Any, **kwargs: Any):
        super().__init__(telegram_service, **kwargs)
        self._owner_visibility_hint: dict[int, str] = {}
        self._sender_role_search: ContextVar[dict[str, Any] | None] = ContextVar(
            f"tg_exporter_sender_role_search_{id(self)}",
            default=None,
        )

    @contextmanager
    def sender_role_filter_scope(self, sender_role: str | None) -> Iterator[None]:
        """Bound extra sender work to one advanced-search request.

        The scope is entered for v3 messages.search. A non-empty sender role
        enables the current-admin snapshot and a request-local sender entity
        cache. Ordinary searches keep both disabled, while history/get/chat
        operations remain on their existing code paths.
        """

        token = self._sender_role_search.set(
            {
                "active": True,
                "sender_role": sender_role,
                "sender_cache": {},
            }
        )
        try:
            yield
        finally:
            self._sender_role_search.reset(token)

    async def _admin_snapshot(
        self,
        row: DialogInfo,
        entity: Any,
    ) -> tuple[dict[int, ParticipantInfo], bool]:
        search_context = self._sender_role_search.get()
        if search_context is not None and search_context.get("active") and not search_context.get("sender_role"):
            # Advanced search only needs participant/admin network work when a
            # sender-role filter was explicitly requested. Other reader calls
            # do not enter this scope and therefore retain existing behavior.
            return {}, False

        # Historical messages may come from a legacy Basic Group while the
        # logical chat is the current Supergroup. Current owner/admin role must
        # always be evaluated on the current logical entity, then delegate to
        # the established base snapshot contract.
        if row.dialog_type in {"group", "supergroup", "channel"}:
            source_id = _safe_peer_id(entity)
            if source_id is not None and source_id != row.chat_id:
                try:
                    entity = await self.client.get_entity(row.chat_id)
                except Exception:
                    self._owner_visibility_hint[row.chat_id] = "participants_unavailable"
                    return {}, False

        snapshot, available = await super()._admin_snapshot(row, entity)
        if any(item.is_creator for item in snapshot.values()):
            self._owner_visibility_hint[row.chat_id] = "available"
        elif not available:
            self._owner_visibility_hint[row.chat_id] = "participants_unavailable"
        elif row.dialog_type == "group":
            # Basic-group GetFullChat returns the complete visible participant
            # structure in one response, so a complete list with no creator is
            # a meaningful not-found result rather than a pagination ambiguity.
            self._owner_visibility_hint[row.chat_id] = "not_found"
        else:
            self._owner_visibility_hint[row.chat_id] = "telegram_not_returned"
        return snapshot, available

    async def _diagnose_owner_visibility(self, row: DialogInfo, entity: Any) -> str:
        """Explain an absent owner without guessing from names or message text.

        This probe is only used by ``chats get`` when the normal current admin
        snapshot contains no creator. It is bounded and read-only, so message
        history/search do not pay for a duplicate participant scan.
        """

        try:
            if row.dialog_type == "group":
                participants, _ = await self._basic_chat_participants(entity)
                return "available" if any(item.is_creator for item in participants) else "not_found"
            if row.dialog_type not in {"supergroup", "channel"}:
                return "not_applicable"

            offset = 0
            scanned = 0
            complete = False
            while scanned < MAX_PAGE_LIMIT:
                request_limit = min(100, MAX_PAGE_LIMIT - scanned)
                result = await self.client(
                    functions.channels.GetParticipantsRequest(
                        channel=entity,
                        filter=types.ChannelParticipantsAdmins(),
                        offset=offset,
                        limit=request_limit,
                        hash=0,
                    )
                )
                participants = list(getattr(result, "participants", None) or ())
                users = {
                    int(getattr(user, "id", 0) or 0): user
                    for user in getattr(result, "users", None) or ()
                }
                if not participants:
                    complete = True
                    break
                for participant in participants:
                    user_id = _participant_user_id(participant)
                    user = users.get(int(user_id or 0))
                    if user is not None and _participant_info(user, participant).is_creator:
                        return "available"
                offset += len(participants)
                scanned += len(participants)
                if len(participants) < request_limit:
                    complete = True
                    break
            if not complete and scanned >= MAX_PAGE_LIMIT:
                return "creator_not_in_returned_page"
            return "telegram_not_returned"
        except RPCError as exc:
            return _owner_rpc_visibility(type(exc).__name__)

    async def chat_details(self, chat: str | int) -> ChatDetails:
        details = await super().chat_details(chat)
        if details.owner is not None or details.chat_type not in {"group", "supergroup", "channel"}:
            return details
        try:
            row, entity = await self.resolve_dialog(details.chat_id)
            visibility = await self._diagnose_owner_visibility(row, entity)
        except TelegramBridgeError:
            visibility = self._owner_visibility_hint.get(details.chat_id, "telegram_not_returned")
        self._owner_visibility_hint[details.chat_id] = visibility
        return replace(details, owner_visibility=visibility)

    async def _sender_info(
        self,
        logical_row: DialogInfo,
        message: Any,
        role_snapshot: dict[int, ParticipantInfo],
        role_available: bool,
    ) -> SenderInfo:
        search_context = self._sender_role_search.get()
        role_filter_active = bool(search_context and search_context.get("sender_role"))
        sender_cache: dict[int, Any] | None = (
            search_context.get("sender_cache") if role_filter_active and search_context is not None else None
        )

        sender = getattr(message, "sender", None)
        raw_from = getattr(message, "from_id", None)
        sender_chat = getattr(message, "sender_chat", None)
        raw_sender_peer = sender_chat or raw_from
        sender_id_property = getattr(message, "sender_id", None)
        post_author = getattr(message, "post_author", None)

        if sender is None and sender_chat is not None:
            sender = sender_chat

        async def resolve_sender_once(peer: Any) -> Any:
            if sender_cache is None or peer is None:
                return None
            peer_id = _raw_peer_id(peer)
            if peer_id is None and isinstance(peer, int) and peer:
                peer_id = int(peer)
            if peer_id is None:
                return None
            if peer_id not in sender_cache:
                try:
                    sender_cache[peer_id] = await self.client.get_entity(peer)
                except Exception:
                    # Failure is cached too, so the same unresolved peer cannot
                    # generate one Telegram request per message.
                    sender_cache[peer_id] = None
            return sender_cache[peer_id]

        if role_filter_active:
            # Do not call Message.get_sender() here: it may independently fetch
            # the same entity per message. Use one request-local cache instead.
            sender_is_hydrated = sender is not None and not type(sender).__name__.startswith("Peer")
            resolution_peer = raw_sender_peer
            if resolution_peer is None and isinstance(sender_id_property, int) and sender_id_property:
                resolution_peer = int(sender_id_property)
            current_raw_id = _raw_peer_id(raw_sender_peer)
            is_current_chat_peer = (
                current_raw_id is not None
                and current_raw_id == logical_row.chat_id
                and logical_row.dialog_type in {"group", "supergroup"}
            )
            if not sender_is_hydrated and resolution_peer is not None and not is_current_chat_peer:
                resolved = await resolve_sender_once(resolution_peer)
                if resolved is not None:
                    sender = resolved
        else:
            # Preserve the established non-role reader behavior. The patch adds
            # no new sender-resolution work to ordinary history/search paths.
            if sender is None:
                try:
                    sender = await message.get_sender()
                except Exception:
                    sender = None

            raw_kind_for_resolution = _peer_kind(raw_sender_peer)
            if sender is None and raw_sender_peer is not None and raw_kind_for_resolution in {"chat", "channel"}:
                try:
                    sender = await self.client.get_entity(raw_sender_peer)
                except Exception:
                    sender = None

        raw_kind = _peer_kind(raw_sender_peer)
        sender_kind = _peer_kind(sender) or raw_kind
        sender_id = _safe_peer_id(sender)
        if sender_id is None:
            sender_id = _raw_peer_id(raw_sender_peer)
        if sender_id is None and isinstance(sender_id_property, int) and sender_id_property:
            sender_id = int(sender_id_property)

        # A positive sender id is unambiguously a user. A negative id without
        # a peer type is only classified when it is the current group itself;
        # external negative ids remain unknown unless the bounded resolver
        # hydrated an entity above.
        if sender_kind is None and sender_id is not None:
            if sender_id > 0:
                sender_kind = "user"
            elif sender_id == logical_row.chat_id and logical_row.dialog_type in {"group", "supergroup"}:
                sender_kind = "chat" if logical_row.dialog_type == "group" else "channel"

        # Broadcast channel posts commonly omit from_id. Telethon may still
        # expose a negative sender_id property, so the peer_id check must run
        # even when sender_id is already populated. The raw peer establishes
        # that the actual poster is the channel rather than an unknown user.
        if raw_from is None and logical_row.dialog_type == "channel":
            peer_id = _raw_peer_id(getattr(message, "peer_id", None))
            if peer_id == logical_row.chat_id and (sender_id is None or sender_id == peer_id):
                sender_id = peer_id
                sender_kind = "channel"

        posted_as = sender_id if sender_kind in {"chat", "channel"} else None
        current_chat_sender = bool(
            posted_as is not None
            and logical_row.dialog_type in {"group", "supergroup"}
            and posted_as == logical_row.chat_id
        )
        explicit_anonymous_flag = any(
            getattr(message, name, False) is True
            for name in ("anonymous_admin", "is_anonymous_admin")
        )
        # Telethon's real-world anonymous-admin representation commonly uses
        # from_id=current supergroup plus post_author, without a sender_chat.
        # post_author alone is never sufficient; the current-group peer is the
        # identity evidence.
        anonymous = bool(
            current_chat_sender
            and (
                explicit_anonymous_flag
                or (
                    sender_chat is None
                    and raw_from is not None
                    and isinstance(post_author, str)
                    and bool(post_author)
                )
            )
        )

        if anonymous:
            sender_type = "anonymous_admin"
        elif sender_kind == "user":
            sender_type = "user"
        elif sender_kind == "channel":
            sender_type = "channel"
        elif sender_kind == "chat":
            sender_type = "chat"
        else:
            sender_type = "unknown"

        role = role_snapshot.get(int(sender_id or 0)) if sender_type == "user" and sender_id is not None else None
        display_name = _display_name(sender)
        if display_name is None and posted_as == logical_row.chat_id:
            display_name = logical_row.title

        unknown_reason = None
        if sender_type == "unknown":
            action = getattr(message, "action", None)
            if action is not None and type(action).__name__ != "MessageActionEmpty":
                unknown_reason = "service_message_without_sender"
            elif getattr(message, "fwd_from", None) is not None:
                unknown_reason = "forwarded_message_without_actual_sender"
            elif isinstance(post_author, str) and post_author:
                unknown_reason = "post_author_without_sender_peer"
            elif raw_sender_peer is not None or (isinstance(sender_id_property, int) and sender_id_property):
                unknown_reason = "unsupported_or_unavailable_sender_peer"
            else:
                unknown_reason = "telegram_sender_not_provided"

        if sender_type == "user":
            role_basis = "current_snapshot" if role_available else "unavailable"
            is_creator = role.is_creator if role is not None else (False if role_available else None)
            is_admin = role.is_admin if role is not None else (False if role_available else None)
            admin_title = role.admin_title if role is not None else None
        elif anonymous:
            # During sender-role filtering, expose the admin truth in the same
            # role basis understood by the existing matcher. Outside that
            # bounded search scope, preserve the richer Telegram-specific basis.
            role_basis = "current_snapshot" if role_filter_active else "telegram_anonymous_admin"
            is_creator = None
            is_admin = True
            admin_title = str(post_author) if isinstance(post_author, str) and post_author else None
        elif current_chat_sender:
            role_basis = "current_snapshot" if role_filter_active else "telegram_current_chat_sender"
            is_creator = None
            is_admin = True
            admin_title = None
        elif sender_type in {"chat", "channel"}:
            role_basis = "telegram_sender_peer"
            is_creator = None
            is_admin = None
            admin_title = None
        else:
            role_basis = "telegram_message_fields"
            is_creator = None
            is_admin = None
            admin_title = None

        return SenderInfo(
            sender_id=sender_id,
            sender_type=sender_type,
            display_name=display_name,
            username=getattr(sender, "username", None),
            posted_as_chat_id=posted_as,
            is_creator=is_creator,
            is_admin=is_admin,
            admin_title=admin_title,
            anonymous_admin=anonymous,
            via_bot_id=(int(getattr(message, "via_bot_id", 0) or 0) or None),
            role_basis=role_basis,
            unknown_reason=unknown_reason,
        )

    async def messages_get_v3(self, chat: str | int, ids: list[int]) -> list[MessageInfoV3]:
        """Fetch exact messages while preserving logical/current migration identity."""

        requested = tuple(dict.fromkeys(int(value) for value in ids))
        if not requested:
            raise TelegramBridgeError(INVALID_ARGUMENT, "至少需要一个 message_id。")

        source_row, source_entity = await self.resolve_dialog(chat)
        logical_row = source_row
        source_chat_id = source_row.chat_id
        if source_row.migrated_to_chat_id is not None:
            try:
                logical_row, _ = await self.resolve_dialog(source_row.migrated_to_chat_id)
            except TelegramBridgeError:
                logical_row = source_row

        messages = await self.client.get_messages(source_entity, ids=list(requested))
        by_id = {
            int(message.id): message
            for message in (messages or ())
            if isinstance(message, Message)
        }
        missing = [message_id for message_id in requested if message_id not in by_id]
        if missing:
            raise TelegramBridgeError(
                MESSAGE_NOT_FOUND,
                "部分消息不存在或当前账号无权访问。",
                {"missing_ids": missing, "reason": "not_found_or_unavailable"},
            )

        role_snapshot, role_available = (
            await self._admin_snapshot(logical_row, source_entity)
            if logical_row.dialog_type in {"group", "supergroup", "channel"}
            else ({}, False)
        )
        return [
            await self._message_info_v3(
                logical_row,
                source_chat_id,
                by_id[message_id],
                role_snapshot,
                role_available,
            )
            for message_id in requested
        ]
