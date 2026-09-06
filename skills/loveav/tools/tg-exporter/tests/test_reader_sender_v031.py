from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from telethon.tl import types
from telethon.utils import get_peer_id

from telegram_exporter.cursor_codec import CursorCodec
from telegram_exporter.reader_models import DialogInfo, ParticipantInfo
from telegram_exporter.reader_runtime import PersonalAccountReaderV3, _owner_rpc_visibility
from telegram_exporter.reader_service import _forward_payload


def marked_channel_id(bare_id: int) -> int:
    return int(get_peer_id(types.PeerChannel(channel_id=bare_id)))


class FakeClient:
    def __init__(self):
        self.entity_by_key: dict[object, object] = {}
        self.participant_pages: list[object] = []

    async def get_entity(self, key):
        if key in self.entity_by_key:
            return self.entity_by_key[key]
        raise LookupError("synthetic entity unavailable")

    async def __call__(self, _request):
        if self.participant_pages:
            return self.participant_pages.pop(0)
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
        via_bot_id=None,
        fwd_from=None,
        action=None,
    ):
        self.sender = sender
        self.from_id = from_id
        self.peer_id = peer_id
        self.sender_id = sender_id
        self.sender_chat = sender_chat
        self.post_author = post_author
        self.via_bot_id = via_bot_id
        self.fwd_from = fwd_from
        self.action = action
        self.id = 1
        self.date = datetime(2026, 8, 30, tzinfo=timezone.utc)
        self.edit_date = None
        self.message = "synthetic fixture"
        self.entities = []
        self.media = None
        self.reply_to = None
        self.grouped_id = None
        self.views = None
        self.forwards = None
        self.reactions = None
        self.pinned = False

    async def get_sender(self):
        return self.sender


def make_reader(client: FakeClient | None = None) -> PersonalAccountReaderV3:
    client = client or FakeClient()
    return PersonalAccountReaderV3(
        SimpleNamespace(client=client),
        cursor_codec=CursorCodec(b"s" * 32),
    )


def test_broadcast_channel_post_uses_peer_id_even_when_sender_id_is_negative() -> None:
    bare_id = 4101
    chat_id = marked_channel_id(bare_id)
    row = DialogInfo(chat_id=chat_id, title="Synthetic Channel", username=None, dialog_type="channel")
    message = FakeMessage(
        from_id=None,
        peer_id=types.PeerChannel(channel_id=bare_id),
        sender_id=chat_id,
    )
    sender = asyncio.run(make_reader()._sender_info(row, message, {}, False))
    assert sender.sender_type == "channel"
    assert sender.sender_id == chat_id
    assert sender.posted_as_chat_id == chat_id
    assert sender.display_name == "Synthetic Channel"
    assert sender.unknown_reason is None
    assert sender.role_basis == "telegram_sender_peer"


def test_anonymous_admin_send_as_group_is_not_deanonymized() -> None:
    bare_id = 4102
    chat_id = marked_channel_id(bare_id)
    row = DialogInfo(chat_id=chat_id, title="Synthetic Group", username=None, dialog_type="supergroup")
    message = FakeMessage(
        from_id=types.PeerChannel(channel_id=bare_id),
        peer_id=types.PeerChannel(channel_id=bare_id),
        post_author="Synthetic Admin Title",
    )
    sender = asyncio.run(make_reader()._sender_info(row, message, {}, True))
    assert sender.sender_type == "anonymous_admin"
    assert sender.sender_id == chat_id
    assert sender.posted_as_chat_id == chat_id
    assert sender.anonymous_admin is True
    assert sender.is_admin is True
    assert sender.admin_title == "Synthetic Admin Title"
    assert sender.role_basis == "telegram_anonymous_admin"
    assert sender.unknown_reason is None


def test_external_send_as_channel_is_classified_as_channel_not_user() -> None:
    logical_id = marked_channel_id(4103)
    external_id = marked_channel_id(4104)
    row = DialogInfo(chat_id=logical_id, title="Synthetic Group", username=None, dialog_type="supergroup")
    message = FakeMessage(from_id=types.PeerChannel(channel_id=4104))
    sender = asyncio.run(make_reader()._sender_info(row, message, {}, True))
    assert sender.sender_type == "channel"
    assert sender.sender_id == external_id
    assert sender.posted_as_chat_id == external_id
    assert sender.anonymous_admin is False
    assert sender.role_basis == "telegram_sender_peer"


def test_user_sender_uses_current_role_snapshot() -> None:
    row = DialogInfo(chat_id=marked_channel_id(4105), title="Synthetic Group", username=None, dialog_type="supergroup")
    role = ParticipantInfo(
        user_id=5101,
        display_name="Synthetic User",
        username=None,
        role="admin",
        is_creator=False,
        is_admin=True,
        admin_title="Moderator",
        bot=False,
        deleted_account=False,
    )
    message = FakeMessage(from_id=types.PeerUser(user_id=5101), sender_id=5101, via_bot_id=6101)
    sender = asyncio.run(make_reader()._sender_info(row, message, {5101: role}, True))
    assert sender.sender_type == "user"
    assert sender.sender_id == 5101
    assert sender.is_admin is True
    assert sender.admin_title == "Moderator"
    assert sender.via_bot_id == 6101
    assert sender.role_basis == "current_snapshot"
    assert sender.unknown_reason is None


def test_deleted_user_entity_remains_user_when_telegram_provides_peer() -> None:
    DeletedUser = type("User", (), {})
    entity = DeletedUser()
    entity.id = 5102
    entity.first_name = "Deleted"
    entity.last_name = None
    entity.title = None
    entity.username = None
    entity.deleted = True
    row = DialogInfo(chat_id=marked_channel_id(4106), title="Synthetic Group", username=None, dialog_type="supergroup")
    message = FakeMessage(sender=entity, from_id=types.PeerUser(user_id=5102), sender_id=5102)
    sender = asyncio.run(make_reader()._sender_info(row, message, {}, False))
    assert sender.sender_type == "user"
    assert sender.sender_id == 5102
    assert sender.unknown_reason is None


def test_forward_origin_never_becomes_actual_sender() -> None:
    row = DialogInfo(chat_id=marked_channel_id(4107), title="Synthetic Group", username=None, dialog_type="supergroup")
    fwd = SimpleNamespace(
        from_id=types.PeerUser(user_id=7101),
        from_name=None,
        date=datetime(2026, 8, 29, tzinfo=timezone.utc),
        post_author=None,
        channel_post=None,
        saved_from_peer=None,
        saved_from_msg_id=None,
    )
    message = FakeMessage(fwd_from=fwd)
    sender = asyncio.run(make_reader()._sender_info(row, message, {}, False))
    origin = _forward_payload(message)
    assert sender.sender_type == "unknown"
    assert sender.sender_id is None
    assert sender.unknown_reason == "forwarded_message_without_actual_sender"
    assert origin is not None
    assert origin["origin_type"] == "user"
    assert origin["origin_id"] == 7101


def test_unknown_reasons_are_explicit_for_service_post_author_and_absence() -> None:
    row = DialogInfo(chat_id=marked_channel_id(4108), title="Synthetic Group", username=None, dialog_type="supergroup")

    ServiceAction = type("MessageActionSynthetic", (), {})
    service_sender = asyncio.run(make_reader()._sender_info(row, FakeMessage(action=ServiceAction()), {}, False))
    assert service_sender.sender_type == "unknown"
    assert service_sender.unknown_reason == "service_message_without_sender"

    post_sender = asyncio.run(make_reader()._sender_info(row, FakeMessage(post_author="Visible Label Only"), {}, False))
    assert post_sender.sender_type == "unknown"
    assert post_sender.display_name is None
    assert post_sender.unknown_reason == "post_author_without_sender_peer"

    absent_sender = asyncio.run(make_reader()._sender_info(row, FakeMessage(), {}, False))
    assert absent_sender.sender_type == "unknown"
    assert absent_sender.unknown_reason == "telegram_sender_not_provided"


def test_owner_rpc_visibility_is_specific() -> None:
    assert _owner_rpc_visibility("ChatAdminRequiredError") == "insufficient_permissions"
    assert _owner_rpc_visibility("AdminRightsRequiredError") == "insufficient_permissions"
    assert _owner_rpc_visibility("ChannelPrivateError") == "participants_unavailable"
    assert _owner_rpc_visibility("UserNotParticipantError") == "participants_unavailable"
    assert _owner_rpc_visibility("SomeOtherRpcError") == "telegram_not_returned"


def test_basic_group_without_creator_is_explicit_not_found() -> None:
    reader = make_reader()
    row = DialogInfo(chat_id=-4201, title="Synthetic Basic Group", username=None, dialog_type="group")
    admin = ParticipantInfo(
        user_id=5201,
        display_name="Synthetic Admin",
        username=None,
        role="admin",
        is_creator=False,
        is_admin=True,
        admin_title=None,
        bot=False,
        deleted_account=False,
    )

    async def fake_participants(_entity):
        return [admin], SimpleNamespace()

    reader._basic_chat_participants = fake_participants  # type: ignore[method-assign]
    snapshot, available = asyncio.run(reader._admin_snapshot(row, SimpleNamespace()))
    assert available is True
    assert 5201 in snapshot
    assert reader._owner_visibility_hint[row.chat_id] == "not_found"


def test_channel_complete_admin_response_without_creator_is_telegram_not_returned() -> None:
    client = FakeClient()
    reader = make_reader(client)
    row = DialogInfo(chat_id=marked_channel_id(4202), title="Synthetic Channel", username=None, dialog_type="channel")
    client.participant_pages = [SimpleNamespace(participants=[], users=[])]
    snapshot, available = asyncio.run(reader._admin_snapshot(row, types.PeerChannel(channel_id=4202)))
    assert snapshot == {}
    assert available is True
    assert reader._owner_visibility_hint[row.chat_id] == "telegram_not_returned"
