from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from telegram_exporter import reader_service as reader_module
from telegram_exporter import tgctl
from telegram_exporter.bridge_errors import INVALID_CURSOR, TelegramBridgeError
from telegram_exporter.cursor_codec import CursorCodec
from telegram_exporter.reader_service import PersonalAccountReader

CHANNEL_ID = -(10**12 + 10)


class User:
    def __init__(self, user_id: int, name: str, *, username: str | None = None, bot: bool = False, contact: bool = False):
        self.id = user_id
        self.first_name = name
        self.last_name = None
        self.username = username
        self.bot = bot
        self.contact = contact
        self.premium = False
        self.lang_code = None
        self.deleted = False


class Channel:
    def __init__(self, channel_id: int, title: str, *, username: str | None = None, megagroup: bool = True, forum: bool = False):
        self.id = channel_id
        self.title = title
        self.username = username
        self.megagroup = megagroup
        self.forum = forum
        self.creator = False
        self.admin_rights = None
        self.migrated_to = None


class FakeDialog:
    def __init__(self, entity, name: str, *, unread: int = 0, pinned: bool = False, archived: bool = False, message_id: int = 1):
        self.entity = entity
        self.name = name
        self.unread_count = unread
        self.pinned = pinned
        self.archived = archived
        self.dialog = SimpleNamespace(unread_mark=False, notify_settings=None)
        self.message = SimpleNamespace(id=message_id, date=datetime(2026, 8, 30, tzinfo=timezone.utc))


class FakeClient:
    def __init__(self):
        self.me = User(100, "Me", username="me")
        self.entities = {
            1: User(1, "Alice", username="alice", contact=True),
            2: User(2, "Helper", username="helperbot", bot=True),
            CHANNEL_ID: Channel(10, "Svip", username="svip", megagroup=True),
        }
        self.dialogs = [
            FakeDialog(self.entities[1], "Alice", unread=2),
            FakeDialog(self.entities[2], "Helper", pinned=True),
            FakeDialog(self.entities[CHANNEL_ID], "Svip", archived=True, message_id=20),
        ]
        self.messages = []

    async def get_me(self):
        return self.me

    def iter_dialogs(self, **_kwargs):
        async def iterator():
            for dialog in self.dialogs:
                yield dialog
        return iterator()

    async def __call__(self, request):
        if type(request).__name__ == "GetDialogFiltersRequest":
            return SimpleNamespace(filters=[])
        if type(request).__name__ == "GetParticipantsRequest":
            return SimpleNamespace(participants=[], users=[])
        raise AssertionError(type(request).__name__)

    async def get_entity(self, value):
        if value == "me" or value == 100:
            return self.me
        return self.entities[value]

    def iter_messages(self, _entity, **kwargs):
        offset_id = int(kwargs.get("offset_id", 0) or 0)
        limit = int(kwargs.get("limit", 100))
        rows = [row for row in self.messages if not offset_id or row.id < offset_id]

        async def iterator():
            for row in rows[:limit]:
                yield row
        return iterator()

    async def get_messages(self, _entity, ids):
        by_id = {row.id: row for row in self.messages}
        return [by_id.get(int(value)) for value in ids]


class FakeMessage:
    def __init__(self, message_id: int, text: str, sender: User, *, media=None, reply_to=None):
        self.id = message_id
        self.message = text
        self.sender = sender
        self.from_id = None
        self.date = datetime(2026, 8, 30, 1, message_id % 60, tzinfo=timezone.utc)
        self.edit_date = None
        self.entities = []
        self.media = media
        self.reply_to = reply_to
        self.fwd_from = None
        self.grouped_id = None
        self.views = None
        self.forwards = None
        self.reactions = None
        self.action = None
        self.pinned = False
        self.via_bot_id = None
        self.post_author = None
        self.photo = None
        self.voice = None
        self.video = None
        self.audio = None
        self.sticker = None
        self.gif = None
        self.file = None

    async def get_sender(self):
        return self.sender


class MessageMediaDocument:
    def __init__(self):
        self.document = SimpleNamespace(id=77, mime_type="application/pdf", size=1234)
        self.spoiler = False


def _fake_get_peer_id(value):
    if isinstance(value, int):
        return value
    name = type(value).__name__
    if name == "User":
        return int(value.id)
    if name == "Channel":
        return -(10**12 + int(value.id))
    if name == "Chat":
        return -int(value.id)
    raise TypeError(f"unsupported fake peer: {name}")


def _reader() -> PersonalAccountReader:
    # The production implementation receives real Telethon User/Chat/Channel
    # objects. These small fakes intentionally patch only Telethon's marked-peer
    # conversion so the tests preserve the real id contract without constructing
    # huge TL objects.
    reader_module.get_peer_id = _fake_get_peer_id
    service = SimpleNamespace(client=FakeClient())
    return PersonalAccountReader(service, cursor_codec=CursorCodec(b"x" * 32))


def test_cursor_is_query_bound_and_tamper_evident() -> None:
    codec = CursorCodec(b"a" * 32)
    token = codec.encode("dialogs.list", {"type": "private"}, {"rank": 1, "chat_id": 4})
    assert codec.decode(token, "dialogs.list", {"type": "private"}) == {"rank": 1, "chat_id": 4}
    with pytest.raises(TelegramBridgeError) as mismatch:
        codec.decode(token, "dialogs.list", {"type": "bot"})
    assert mismatch.value.code == INVALID_CURSOR
    bad = token[:-1] + ("A" if token[-1] != "A" else "B")
    with pytest.raises(TelegramBridgeError) as tamper:
        codec.decode(bad, "dialogs.list", {"type": "private"})
    assert tamper.value.code == INVALID_CURSOR


def test_dialogs_cover_private_bot_saved_and_page_without_overlap() -> None:
    reader = _reader()
    first = asyncio.run(reader.dialogs_page(limit=2))
    second = asyncio.run(reader.dialogs_page(limit=2, cursor=first.next_cursor))
    first_ids = {row.chat_id for row in first.items}
    second_ids = {row.chat_id for row in second.items}
    assert first.has_more is True
    assert first_ids.isdisjoint(second_ids)
    all_types = {row.dialog_type for row in [*first.items, *second.items]}
    assert {"saved", "private", "bot", "supergroup"}.issubset(all_types)
    saved = next(row for row in [*first.items, *second.items] if row.dialog_type == "saved")
    assert saved.reference == "me"


def test_dialog_filters_are_stable_and_bounded() -> None:
    reader = _reader()
    private = asyncio.run(reader.dialogs_page(dialog_type="private", unread="yes", limit=500))
    assert [row.title for row in private.items] == ["Alice"]
    with pytest.raises(TelegramBridgeError):
        asyncio.run(reader.dialogs_page(limit=501))


def test_rich_history_keeps_media_metadata_without_download(monkeypatch) -> None:
    reader = _reader()
    monkeypatch.setattr(reader_module, "Message", FakeMessage)
    sender = reader.client.entities[1]
    media = MessageMediaDocument()
    message = FakeMessage(9, "caption", sender, media=media, reply_to=SimpleNamespace(reply_to_msg_id=7, reply_to_top_id=None, forum_topic=False))
    message.file = SimpleNamespace(name="paper.pdf", mime_type="application/pdf", size=1234, width=None, height=None, duration=None)
    reader.client.messages = [message]
    page = asyncio.run(reader.messages_history_page(CHANNEL_ID, limit=10))
    assert page.count == 1
    row = page.items[0]
    assert row.text is None
    assert row.caption == "caption"
    assert row.reply_to_message_id == 7
    assert row.sender.sender_id == 1
    assert row.media.media_type == "document"
    assert row.media.filename == "paper.pdf"
    serialized = json.dumps(reader_module.Page(items=[row]), default=lambda value: getattr(value, "__dict__", str(value)))
    assert "access_hash" not in serialized
    assert "file_reference" not in serialized


def test_tgctl_parser_accepts_v3_reader_commands() -> None:
    parser = tgctl.build_parser()
    args = parser.parse_args(["dialogs", "list", "--type", "private", "--limit", "500", "--jsonl"])
    assert args.command == "dialogs"
    assert args.dialog_type == "private"
    assert args.limit == 500
    assert args.jsonl is True
    history = parser.parse_args(["messages", "history", "--chat", "me", "--limit", "100", "--json"])
    assert history.messages_command == "history"
    members = parser.parse_args(["chats", "members", "--chat", "-1001", "--role", "admin", "--json"])
    assert members.chats_command == "members"


def test_jsonl_contract_meta_item_end(capsys) -> None:
    payload = tgctl.success(
        {
            "items": [{"chat_id": 1}, {"chat_id": 2}],
            "count": 2,
            "next_cursor": "abc",
            "has_more": True,
            "timing": {"network_ms": 1, "local_filter_ms": 0, "serialization_ms": 0},
        }
    )
    tgctl.emit(payload, json_mode=False, jsonl_mode=True)
    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [row["type"] for row in rows] == ["meta", "item", "item", "end"]
    assert rows[0]["data"]["schema"] == "tgctl.reader.v1"
    assert rows[-1]["data"]["next_cursor"] == "abc"


def test_reader_exit_code_contract_is_stable() -> None:
    assert tgctl._exit_code("SESSION_BUSY") == 8
    assert tgctl._exit_code("INVALID_CURSOR") == 12
    assert tgctl._exit_code("MEMBERS_UNAVAILABLE") == 13
