from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from telegram_exporter import reader_search as search_module
from telegram_exporter.bridge_errors import INVALID_ARGUMENT, INVALID_CURSOR, TelegramBridgeError
from telegram_exporter.cursor_codec import CursorCodec
from telegram_exporter.reader_models import DialogInfo, MessageInfoV3, SenderInfo
from telegram_exporter.reader_search import (
    _normalize_domain,
    domain_filter_smoke_test,
    search_messages_page,
)

CHAT_ID = -(10**12 + 3101)


class FakeMessage:
    def __init__(self, message_id: int, text: str):
        self.id = message_id
        self.message = text
        self.date = datetime(2026, 8, 30, 4, 0, message_id, tzinfo=timezone.utc)
        self.sender_id = 3102
        self.entities = []
        self.media = None

    def get_entities_text(self):
        return []


class FakeClient:
    def __init__(self, messages: list[FakeMessage]):
        self.messages = messages

    async def get_entity(self, value):
        return value

    def iter_messages(self, _entity, **kwargs):
        offset = int(kwargs.get("offset_id", 0) or 0)
        rows = [row for row in self.messages if not offset or row.id < offset]

        async def iterator():
            for row in rows[: int(kwargs.get("limit", len(rows)))]:
                yield row

        return iterator()


class FakeReader:
    def __init__(self, messages: list[FakeMessage]):
        self.cursor = CursorCodec(b"d" * 32)
        self.client = FakeClient(messages)
        self.row = DialogInfo(
            chat_id=CHAT_ID,
            title="Synthetic Search Fixture",
            username=None,
            dialog_type="supergroup",
        )

    async def resolve_dialog(self, _reference):
        return self.row, CHAT_ID

    async def _admin_snapshot(self, _row, _entity):
        return {}, True

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
                is_creator=False,
                is_admin=False,
                admin_title=None,
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


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("mypikpak.com", "mypikpak.com"),
        ("www.mypikpak.com", "www.mypikpak.com"),
        ("MYPiKPAK.CoM", "mypikpak.com"),
        ("https://mypikpak.com/path?q=1", "mypikpak.com"),
        ("cdn.mypikpak.com", "cdn.mypikpak.com"),
        ("  mypikpak.com  ", "mypikpak.com"),
    ],
)
def test_domain_normalization_is_offline_and_canonical(raw: str, expected: str) -> None:
    assert _normalize_domain(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "not a domain",
        "bad..example.com",
        "-bad.example.com",
        "bad-.example.com",
        "https://user:password@example.com/path",
        "https://example.com:bad/path",
    ],
)
def test_invalid_domain_is_structured_invalid_argument(raw: str) -> None:
    with pytest.raises(TelegramBridgeError) as captured:
        _normalize_domain(raw)
    assert captured.value.code == INVALID_ARGUMENT


def test_source_domain_smoke_test() -> None:
    assert domain_filter_smoke_test() is True


def test_domain_filter_matches_base_and_subdomain_but_not_lookalike(monkeypatch) -> None:
    monkeypatch.setattr(search_module, "Message", FakeMessage)
    reader = FakeReader(
        [
            FakeMessage(5, "https://mypikpak.com.evil.example/x"),
            FakeMessage(4, "https://cdn.mypikpak.com/x"),
            FakeMessage(3, "https://mypikpak.com/x"),
            FakeMessage(2, "https://notmypikpak.com/x"),
        ]
    )
    page = asyncio.run(search_messages_page(reader, chat=CHAT_ID, url_domain="mypikpak.com", limit=10))
    assert [row.message_id for row in page.items] == [4, 3]


def test_domain_filter_no_match_returns_empty_page(monkeypatch) -> None:
    monkeypatch.setattr(search_module, "Message", FakeMessage)
    reader = FakeReader([FakeMessage(2, "https://example.invalid/x")])
    page = asyncio.run(search_messages_page(reader, chat=CHAT_ID, url_domain="mypikpak.com", limit=10))
    assert page.items == []
    assert page.matched_count == 0
    assert page.has_more is False


def test_domain_filter_pagination_has_no_duplicates_and_binds_cursor(monkeypatch) -> None:
    monkeypatch.setattr(search_module, "Message", FakeMessage)
    reader = FakeReader(
        [
            FakeMessage(6, "https://a.mypikpak.com/6"),
            FakeMessage(5, "https://mypikpak.com/5"),
            FakeMessage(4, "https://b.mypikpak.com/4"),
        ]
    )
    first = asyncio.run(search_messages_page(reader, chat=CHAT_ID, url_domain="MYPiKPAK.CoM", limit=1))
    assert first.next_cursor

    # Equivalent normalization is the same query fingerprint.
    second = asyncio.run(
        search_messages_page(
            reader,
            chat=CHAT_ID,
            url_domain="https://mypikpak.com/anything",
            limit=1,
            cursor=first.next_cursor,
        )
    )
    assert {row.message_id for row in first.items}.isdisjoint({row.message_id for row in second.items})

    with pytest.raises(TelegramBridgeError) as captured:
        asyncio.run(
            search_messages_page(
                reader,
                chat=CHAT_ID,
                url_domain="example.com",
                limit=1,
                cursor=first.next_cursor,
            )
        )
    assert captured.value.code == INVALID_CURSOR
