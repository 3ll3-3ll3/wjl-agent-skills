from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from telegram_exporter import reader_search as search_module
from telegram_exporter.bridge_errors import CURSOR_STALE, TelegramBridgeError
from telegram_exporter.cursor_codec import CursorCodec
from telegram_exporter.reader_models import DialogInfo, MessageInfoV3, SenderInfo
from telegram_exporter.reader_search import search_messages_page

CURRENT_ID = -(10**12 + 77)
LEGACY_ID = -77


class SearchMessage:
    def __init__(self, message_id: int, text: str):
        self.id = message_id
        self.message = text
        self.date = datetime(2026, 8, 30, 2, message_id % 60, tzinfo=timezone.utc)
        self.sender_id = 1
        self.entities = []
        self.media = None

    def get_entities_text(self):
        return []


class MigratedSearchClient:
    def __init__(self):
        self.messages = {
            CURRENT_ID: [SearchMessage(10, "current noise"), SearchMessage(9, "current noise")],
            LEGACY_ID: [
                SearchMessage(5, "pikpak legacy five"),
                SearchMessage(4, "pikpak legacy four"),
                SearchMessage(3, "pikpak legacy three"),
            ],
        }

    async def get_entity(self, value):
        return value

    def iter_messages(self, entity, **kwargs):
        offset = int(kwargs.get("offset_id", 0) or 0)
        search = kwargs.get("search")
        rows = list(self.messages.get(int(entity), ()))
        if offset:
            rows = [row for row in rows if row.id < offset]
        if search:
            rows = [row for row in rows if str(search).casefold() in row.message.casefold()]
        rows = rows[: int(kwargs.get("limit", len(rows)))]

        async def iterator():
            for row in rows:
                yield row

        return iterator()


class MigratedSearchReader:
    def __init__(self):
        self.cursor = CursorCodec(b"m" * 32)
        self.client = MigratedSearchClient()
        self.row = DialogInfo(
            chat_id=CURRENT_ID,
            title="Migrated",
            username=None,
            dialog_type="supergroup",
            migrated_from_chat_id=LEGACY_ID,
        )

    async def _dialog_catalogue(self):
        return [self.row], {CURRENT_ID: CURRENT_ID, LEGACY_ID: LEGACY_ID}

    async def resolve_dialog(self, _reference):
        return self.row, CURRENT_ID

    async def _admin_snapshot(self, _row, _entity):
        return {}, False

    async def _message_info_v3(self, logical_row, source_chat_id, message, _roles, _available):
        return MessageInfoV3(
            chat_id=logical_row.chat_id,
            source_chat_id=source_chat_id,
            message_id=message.id,
            date=message.date,
            edit_date=None,
            sender=SenderInfo(
                sender_id=1,
                sender_type="user",
                display_name="sender",
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


def test_global_search_cursor_resumes_legacy_segment_without_duplicate(monkeypatch) -> None:
    monkeypatch.setattr(search_module, "Message", SearchMessage)
    reader = MigratedSearchReader()

    first = asyncio.run(search_messages_page(reader, chat=None, contains="pikpak", limit=1))
    assert [(row.source_chat_id, row.message_id) for row in first.items] == [(LEGACY_ID, 5)]
    assert first.has_more is True
    assert first.next_cursor

    second = asyncio.run(
        search_messages_page(reader, chat=None, contains="pikpak", limit=1, cursor=first.next_cursor)
    )
    assert [(row.source_chat_id, row.message_id) for row in second.items] == [(LEGACY_ID, 4)]


def test_single_chat_legacy_cursor_becomes_stale_if_migration_relation_disappears(monkeypatch) -> None:
    monkeypatch.setattr(search_module, "Message", SearchMessage)
    reader = MigratedSearchReader()
    first = asyncio.run(search_messages_page(reader, chat=CURRENT_ID, contains="pikpak", limit=1))
    assert first.next_cursor
    reader.row.migrated_from_chat_id = None

    with pytest.raises(TelegramBridgeError) as caught:
        asyncio.run(
            search_messages_page(
                reader,
                chat=CURRENT_ID,
                contains="pikpak",
                limit=1,
                cursor=first.next_cursor,
            )
        )
    assert caught.value.code == CURSOR_STALE
