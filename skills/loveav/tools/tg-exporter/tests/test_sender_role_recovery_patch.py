from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from telethon.tl import types
from telethon.utils import get_peer_id

from telegram_exporter.cursor_codec import CursorCodec
from telegram_exporter.reader_models import DialogInfo, ParticipantInfo
from telegram_exporter.reader_runtime import PersonalAccountReaderV3, _raw_peer_id
from telegram_exporter.reader_search import _role_matches
from telegram_exporter.reader_service import _forward_payload


def marked_channel_id(bare_id: int) -> int:
    return int(get_peer_id(types.PeerChannel(channel_id=bare_id)))


class FakeClient:
    def __init__(self) -> None:
        self.entities: dict[int, object] = {}
        self.get_entity_calls: list[int] = []
        self.participant_rpc_calls = 0

    async def get_entity(self, key):
        marked = _raw_peer_id(key)
        if marked is None and isinstance(key, int):
            marked = int(key)
        self.get_entity_calls.append(int(marked or 0))
        if marked in self.entities:
            return self.entities[marked]
        raise LookupError("synthetic entity unavailable")

    async def __call__(self, _request):
        self.participant_rpc_calls += 1
        return SimpleNamespace(participants=[], users=[])


class FakeMessage:
    def __init__(
        self,
        *,
        sender=None,
        from_id=None,
        peer_id=None,
        sender_id=None,
        sender_chat=None,
        post_author=None,
        fwd_from=None,
        anonymous_admin=False,
    ) -> None:
        self.sender = sender
        self.from_id = from_id
        self.peer_id = peer_id
        self.sender_id = sender_id
        self.sender_chat = sender_chat
        self.post_author = post_author
        self.fwd_from = fwd_from
        self.anonymous_admin = anonymous_admin
        self.is_anonymous_admin = False
        self.via_bot_id = None
        self.action = None
        self.id = 1
        self.date = datetime(2026, 8, 31, tzinfo=timezone.utc)
        self.edit_date = None
        self.message = "synthetic fixture only"
        self.entities = []
        self.media = None
        self.reply_to = None
        self.grouped_id = None
        self.views = None
        self.forwards = None
        self.reactions = None
        self.pinned = False
        self.get_sender_calls = 0

    async def get_sender(self):
        self.get_sender_calls += 1
        return self.sender


def make_user(user_id: int, name: str = "Synthetic User"):
    User = type("User", (), {})
    user = User()
    user.id = user_id
    user.first_name = name
    user.last_name = None
    user.title = None
    user.username = None
    user.deleted = False
    return user


def make_reader(client: FakeClient | None = None) -> PersonalAccountReaderV3:
    client = client or FakeClient()
    return PersonalAccountReaderV3(
        SimpleNamespace(client=client),
        cursor_codec=CursorCodec(b"r" * 32),
    )


def admin_role(user_id: int, *, creator: bool = False) -> ParticipantInfo:
    return ParticipantInfo(
        user_id=user_id,
        display_name="Synthetic Admin",
        username=None,
        role="owner" if creator else "admin",
        is_creator=creator,
        is_admin=True,
        admin_title=None,
        bot=False,
        deleted_account=False,
    )


def member_role(user_id: int) -> ParticipantInfo:
    return ParticipantInfo(
        user_id=user_id,
        display_name="Synthetic Member",
        username=None,
        role="member",
        is_creator=False,
        is_admin=False,
        admin_title=None,
        bot=False,
        deleted_account=False,
    )


async def sender_in_scope(
    reader: PersonalAccountReaderV3,
    row: DialogInfo,
    message: FakeMessage,
    snapshot: dict[int, ParticipantInfo],
    available: bool,
    *,
    role: str | None = "admin",
):
    with reader.sender_role_filter_scope(role):
        return await reader._sender_info(row, message, snapshot, available)


def test_unloaded_sender_peer_is_resolved_once_per_role_search_request() -> None:
    client = FakeClient()
    reader = make_reader(client)
    row = DialogInfo(
        chat_id=marked_channel_id(8101),
        title="Synthetic Supergroup",
        username=None,
        dialog_type="supergroup",
    )
    user_id = 9101
    client.entities[user_id] = make_user(user_id, "Recovered Sender")
    role = admin_role(user_id)
    first = FakeMessage(from_id=types.PeerUser(user_id=user_id), sender_id=user_id)
    second = FakeMessage(from_id=types.PeerUser(user_id=user_id), sender_id=user_id)

    async def scenario():
        with reader.sender_role_filter_scope("admin"):
            sender1 = await reader._sender_info(row, first, {user_id: role}, True)
            sender2 = await reader._sender_info(row, second, {user_id: role}, True)
            return sender1, sender2

    sender1, sender2 = asyncio.run(scenario())

    assert client.get_entity_calls == [user_id]
    assert first.get_sender_calls == 0
    assert second.get_sender_calls == 0
    assert sender1.sender_type == "user"
    assert sender1.sender_id == user_id
    assert sender1.display_name == "Recovered Sender"
    assert sender1.is_admin is True
    assert sender2.sender_id == user_id


def test_anonymous_admin_matches_admin_role_without_guessing_user() -> None:
    bare_chat_id = 8102
    chat_id = marked_channel_id(bare_chat_id)
    reader = make_reader()
    row = DialogInfo(chat_id=chat_id, title="Synthetic Supergroup", username=None, dialog_type="supergroup")
    message = FakeMessage(
        from_id=types.PeerChannel(channel_id=bare_chat_id),
        peer_id=types.PeerChannel(channel_id=bare_chat_id),
        post_author="Visible Telegram admin label",
        anonymous_admin=True,
    )

    sender = asyncio.run(sender_in_scope(reader, row, message, {}, False))

    assert sender.sender_type == "anonymous_admin"
    assert sender.anonymous_admin is True
    assert sender.posted_as_chat_id == chat_id
    assert sender.is_admin is True
    assert sender.is_creator is None
    assert _role_matches(SimpleNamespace(sender=sender), "admin") is True
    assert _role_matches(SimpleNamespace(sender=sender), "owner") is False


def test_current_chat_send_as_matches_admin_role_but_not_specific_owner() -> None:
    bare_chat_id = 8103
    chat_id = marked_channel_id(bare_chat_id)
    reader = make_reader()
    row = DialogInfo(chat_id=chat_id, title="Synthetic Supergroup", username=None, dialog_type="supergroup")
    message = FakeMessage(
        sender_chat=types.PeerChannel(channel_id=bare_chat_id),
        peer_id=types.PeerChannel(channel_id=bare_chat_id),
        sender_id=chat_id,
    )

    sender = asyncio.run(sender_in_scope(reader, row, message, {}, False))

    assert sender.sender_type == "channel"
    assert sender.posted_as_chat_id == chat_id
    assert sender.anonymous_admin is False
    assert sender.is_admin is True
    assert sender.is_creator is None
    assert _role_matches(SimpleNamespace(sender=sender), "admin") is True
    assert _role_matches(SimpleNamespace(sender=sender), "owner") is False


def test_normal_member_does_not_match_admin_role() -> None:
    client = FakeClient()
    reader = make_reader(client)
    row = DialogInfo(
        chat_id=marked_channel_id(8104),
        title="Synthetic Supergroup",
        username=None,
        dialog_type="supergroup",
    )
    user_id = 9104
    client.entities[user_id] = make_user(user_id)
    role = member_role(user_id)
    message = FakeMessage(from_id=types.PeerUser(user_id=user_id), sender_id=user_id)

    sender = asyncio.run(sender_in_scope(reader, row, message, {user_id: role}, True))

    assert sender.sender_type == "user"
    assert sender.is_admin is False
    assert _role_matches(SimpleNamespace(sender=sender), "admin") is False


def test_forward_origin_admin_is_not_treated_as_actual_admin_sender() -> None:
    row = DialogInfo(
        chat_id=marked_channel_id(8105),
        title="Synthetic Supergroup",
        username=None,
        dialog_type="supergroup",
    )
    admin_user_id = 9105
    fwd = SimpleNamespace(
        from_id=types.PeerUser(user_id=admin_user_id),
        from_name=None,
        date=datetime(2026, 8, 30, tzinfo=timezone.utc),
        post_author=None,
        channel_post=None,
        saved_from_peer=None,
        saved_from_msg_id=None,
    )
    reader = make_reader()
    message = FakeMessage(fwd_from=fwd)

    sender = asyncio.run(
        sender_in_scope(reader, row, message, {admin_user_id: admin_role(admin_user_id)}, True)
    )

    origin = _forward_payload(message)
    assert sender.sender_type == "unknown"
    assert sender.sender_id is None
    assert sender.unknown_reason == "forwarded_message_without_actual_sender"
    assert _role_matches(SimpleNamespace(sender=sender), "admin") is False
    assert origin is not None
    assert origin["origin_type"] == "user"


def test_completely_missing_sender_stays_unknown() -> None:
    row = DialogInfo(
        chat_id=marked_channel_id(8106),
        title="Synthetic Supergroup",
        username=None,
        dialog_type="supergroup",
    )
    reader = make_reader()
    message = FakeMessage()

    sender = asyncio.run(sender_in_scope(reader, row, message, {}, True))

    assert sender.sender_type == "unknown"
    assert sender.sender_id is None
    assert sender.unknown_reason == "telegram_sender_not_provided"
    assert _role_matches(SimpleNamespace(sender=sender), "admin") is False


def test_non_role_search_scope_adds_no_admin_snapshot_or_cached_sender_resolution() -> None:
    client = FakeClient()
    reader = make_reader(client)
    bare_chat_id = 8107
    chat_id = marked_channel_id(bare_chat_id)
    row = DialogInfo(chat_id=chat_id, title="Synthetic Supergroup", username=None, dialog_type="supergroup")
    message = FakeMessage(from_id=types.PeerUser(user_id=9107), sender_id=9107)

    async def scenario():
        with reader.sender_role_filter_scope(None):
            snapshot, available = await reader._admin_snapshot(row, types.PeerChannel(channel_id=bare_chat_id))
            sender = await reader._sender_info(row, message, {}, False)
            return snapshot, available, sender

    snapshot, available, sender = asyncio.run(scenario())

    assert snapshot == {}
    assert available is False
    assert client.participant_rpc_calls == 0
    assert client.get_entity_calls == []
    # Existing Message.get_sender behavior is preserved; the patch itself adds
    # no client-side entity recovery to ordinary search/history/GUI paths.
    assert message.get_sender_calls == 1
    assert sender.sender_type == "user"
