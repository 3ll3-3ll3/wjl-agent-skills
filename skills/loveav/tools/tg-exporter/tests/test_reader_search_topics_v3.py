from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from telethon.tl import functions, types

from telegram_exporter import reader_search as search_module
from telegram_exporter.cursor_codec import CursorCodec
from telegram_exporter.reader_models import DialogInfo, MessageInfoV3, SenderInfo
from telegram_exporter.reader_search import domain_matches, search_messages_page
from telegram_exporter.reader_topics import topics_page

CHAT_ID = -(10**12 + 77)


class SearchMessage:
    def __init__(self, message_id: int, text: str, sender_id: int):
        self.id = message_id
        self.message = text
        self.date = datetime(2026, 8, 30, 2, message_id, tzinfo=timezone.utc)
        self.sender_id = sender_id
        self.entities = []
        self.media = None

    def get_entities_text(self):
        return []


class SearchClient:
    def __init__(self, messages):
        self.messages = list(messages)

    async def get_entity(self, value):
        return value

    def iter_messages(self, _entity, **kwargs):
        offset = int(kwargs.get("offset_id", 0) or 0)
        search = kwargs.get("search")
        rows = [row for row in self.messages if not offset or row.id < offset]
        if search:
            rows = [row for row in rows if str(search).casefold() in row.message.casefold()]

        async def iterator():
            for row in rows[: int(kwargs.get("limit", len(rows)))]:
                yield row
        return iterator()


class SearchReader:
    def __init__(self, messages):
        self.cursor = CursorCodec(b"s" * 32)
        self.client = SearchClient(messages)
        self.row = DialogInfo(chat_id=CHAT_ID, title="Svip", username="svip", dialog_type="supergroup")

    async def resolve_dialog(self, _reference):
        return self.row, CHAT_ID

    async def _admin_snapshot(self, _row, _entity):
        return {}, True

    async def _message_info_v3(self, logical_row, source_chat_id, message, _roles, _available):
        is_admin = message.sender_id == 1
        return MessageInfoV3(
            chat_id=logical_row.chat_id,
            source_chat_id=source_chat_id,
            message_id=message.id,
            date=message.date,
            edit_date=None,
            sender=SenderInfo(
                sender_id=message.sender_id,
                sender_type="user",
                display_name=f"user-{message.sender_id}",
                username=None,
                posted_as_chat_id=None,
                is_creator=False,
                is_admin=is_admin,
                admin_title="Admin" if is_admin else None,
                anonymous_admin=False,
                via_bot_id=None,
                role_basis="current_snapshot",
            ),
            text=message.message,
            caption=None,
            entities=(),
            reply_to_message_id=None,
            reply_to_top_id=None,
            forum_topic_id=None,
            forward_origin=None,
            grouped_id=None,
            views=None,
            forwards=None,
            reactions=(),
            poll=None,
            service_action=None,
            pinned=False,
            media=None,
        )


class ForumTopic:
    def __init__(self, topic_id: int, title: str, top_message: int):
        self.id = topic_id
        self.title = title
        self.icon_color = 0x6FB9F0
        self.icon_emoji_id = None
        self.top_message = top_message
        self.unread_count = 0
        self.pinned = topic_id == 1
        self.closed = False
        self.hidden = False
        self.date = datetime(2026, 8, 30, 3, topic_id, tzinfo=timezone.utc)


class ForumClient:
    async def __call__(self, request):
        assert type(request).__name__ == "GetForumTopicsRequest"
        assert hasattr(request, "peer")
        all_topics = [ForumTopic(1, "General", 101), ForumTopic(2, "PikPak", 102), ForumTopic(3, "News", 103)]
        if int(getattr(request, "offset_topic", 0) or 0) == 2:
            topics = all_topics[2:]
        else:
            topics = all_topics
        return SimpleNamespace(topics=topics, count=3)


class ForumReader:
    def __init__(self):
        self.cursor = CursorCodec(b"f" * 32)
        self.client = ForumClient()
        self.row = DialogInfo(chat_id=CHAT_ID, title="Forum", username=None, dialog_type="supergroup", forum=True)

    async def resolve_dialog(self, _reference):
        return self.row, types.InputChannel(channel_id=77, access_hash=123)


def test_domain_matching_rejects_lookalike_suffix() -> None:
    wanted = "mypikpak.com"
    assert domain_matches("mypikpak.com", wanted)
    assert domain_matches("cdn.mypikpak.com", wanted)
    assert not domain_matches("mypikpak.com.evil.com", wanted)
    assert not domain_matches("notmypikpak.com", wanted)


def test_search_domain_and_current_admin_role(monkeypatch) -> None:
    monkeypatch.setattr(search_module, "Message", SearchMessage)
    reader = SearchReader(
        [
            SearchMessage(5, "fake https://mypikpak.com.evil.com/x", 1),
            SearchMessage(4, "good https://cdn.mypikpak.com/x", 1),
            SearchMessage(3, "member https://mypikpak.com/x", 2),
        ]
    )
    page = asyncio.run(
        search_messages_page(
            reader,
            chat=CHAT_ID,
            sender_role="admin",
            url_domain="mypikpak.com",
            limit=20,
        )
    )
    assert [row.message_id for row in page.items] == [4]
    assert page.scanned_count == 3


def test_search_cursor_continues_without_overlap(monkeypatch) -> None:
    monkeypatch.setattr(search_module, "Message", SearchMessage)
    reader = SearchReader([SearchMessage(value, f"pikpak {value}", 1) for value in range(6, 0, -1)])
    first = asyncio.run(search_messages_page(reader, chat=CHAT_ID, contains="pikpak", limit=2))
    second = asyncio.run(
        search_messages_page(reader, chat=CHAT_ID, contains="pikpak", limit=2, cursor=first.next_cursor)
    )
    first_ids = {row.message_id for row in first.items}
    second_ids = {row.message_id for row in second.items}
    assert first.has_more is True
    assert first.next_cursor
    assert first_ids.isdisjoint(second_ids)
    assert max(second_ids) < min(first_ids)


def test_telethon_forum_request_signature_is_available() -> None:
    request = functions.messages.GetForumTopicsRequest(
        peer=types.InputChannel(channel_id=77, access_hash=123),
        q=None,
        offset_date=None,
        offset_id=0,
        offset_topic=0,
        limit=10,
    )
    assert request.limit == 10
    assert type(request.peer).__name__ == "InputChannel"


def test_topics_list_returns_bounded_page_and_cursor() -> None:
    reader = ForumReader()
    first = asyncio.run(topics_page(reader, CHAT_ID, limit=2))
    assert [row.topic_id for row in first.items] == [1, 2]
    assert first.has_more is True
    assert first.next_cursor
    second = asyncio.run(topics_page(reader, CHAT_ID, limit=2, cursor=first.next_cursor))
    assert [row.topic_id for row in second.items] == [3]
