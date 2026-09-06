from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from telegram_exporter import reader_search as search_module
from telegram_exporter import reader_service as reader_module
from telegram_exporter.cursor_codec import CursorCodec
from telegram_exporter.reader_models import DialogInfo, MessageInfoV3, SenderInfo
from telegram_exporter.reader_search import search_messages_page
from telegram_exporter.reader_service import PersonalAccountReader
from telegram_exporter.tgctl import _parse_iso

CHAT_ID = 7311


class FakeMessage:
    def __init__(self, message_id: int, date: datetime):
        self.id = message_id
        self.date = date
        self.edit_date = None
        self.message = f"synthetic-{message_id}"
        self.sender_id = 7312
        self.entities = []
        self.media = None
        self.reply_to = None
        self.fwd_from = None
        self.grouped_id = None
        self.views = None
        self.forwards = None
        self.reactions = None
        self.action = None
        self.pinned = False
        self.via_bot_id = None
        self.post_author = None


class FakeClient:
    def __init__(self, messages: list[FakeMessage]):
        self.messages = messages

    async def get_entity(self, value):
        return value

    def iter_messages(self, _entity, **kwargs):
        offset_id = int(kwargs.get("offset_id", 0) or 0)
        rows = [row for row in self.messages if not offset_id or row.id < offset_id]

        async def iterator():
            for row in rows[: int(kwargs.get("limit", len(rows)))]:
                yield row

        return iterator()


class BoundaryReader(PersonalAccountReader):
    def __init__(self, messages: list[FakeMessage]):
        super().__init__(SimpleNamespace(client=FakeClient(messages)), cursor_codec=CursorCodec(b"t" * 32))
        self.row = DialogInfo(
            chat_id=CHAT_ID,
            title="Synthetic Time Boundary",
            username=None,
            dialog_type="private",
        )

    async def resolve_dialog(self, _reference):
        return self.row, CHAT_ID

    async def _message_info_v3(self, logical_row, source_chat_id, message, _roles, _available):
        return MessageInfoV3(
            chat_id=logical_row.chat_id,
            source_chat_id=source_chat_id,
            message_id=message.id,
            date=message.date,
            edit_date=None,
            sender=SenderInfo(
                sender_id=message.sender_id,
                sender_type="user",
                display_name="Synthetic Sender",
                username=None,
                posted_as_chat_id=None,
                is_creator=None,
                is_admin=None,
                admin_title=None,
                anonymous_admin=False,
                via_bot_id=None,
                role_basis="unavailable",
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


def _messages() -> list[FakeMessage]:
    return [
        FakeMessage(4, datetime(2026, 8, 30, 1, 0, tzinfo=timezone.utc)),
        FakeMessage(3, datetime(2026, 8, 30, 0, 30, tzinfo=timezone.utc)),
        FakeMessage(2, datetime(2026, 8, 30, 0, 0, tzinfo=timezone.utc)),
        FakeMessage(1, datetime(2026, 8, 29, 23, 59, 59, tzinfo=timezone.utc)),
    ]


def test_tgctl_parse_iso_preserves_explicit_offset_instant() -> None:
    parsed = _parse_iso("2026-08-30T08:00:00+08:00")
    assert parsed is not None
    assert parsed.astimezone(timezone.utc) == datetime(2026, 8, 30, 0, 0, tzinfo=timezone.utc)


def test_history_since_is_inclusive_until_is_exclusive_across_timezone(monkeypatch) -> None:
    monkeypatch.setattr(reader_module, "Message", FakeMessage)
    reader = BoundaryReader(_messages())
    since = _parse_iso("2026-08-30T08:00:00+08:00")
    until = _parse_iso("2026-08-30T09:00:00+08:00")
    page = asyncio.run(reader.messages_history_page(CHAT_ID, since=since, until=until, limit=20))
    # id=2 is exactly since and must be included. id=4 is exactly until and
    # must be excluded. id=1 is older than since and must be excluded.
    assert [row.message_id for row in page.items] == [3, 2]


def test_search_since_is_inclusive_until_is_exclusive_across_timezone(monkeypatch) -> None:
    monkeypatch.setattr(search_module, "Message", FakeMessage)
    reader = BoundaryReader(_messages())
    since = _parse_iso("2026-08-30T08:00:00+08:00")
    until = _parse_iso("2026-08-30T09:00:00+08:00")
    page = asyncio.run(
        search_messages_page(
            reader,
            chat=CHAT_ID,
            contains="synthetic",
            since=since,
            until=until,
            limit=20,
        )
    )
    assert [row.message_id for row in page.items] == [3, 2]
