from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from telegram_exporter import reader_search as search_module
from telegram_exporter import tgctl as tgctl_module
from telegram_exporter.bridge_errors import INVALID_ARGUMENT, INVALID_CURSOR, TelegramBridgeError
from telegram_exporter.cursor_codec import CursorCodec
from telegram_exporter.reader_models import DialogInfo, MessageInfoV3, SenderInfo
from telegram_exporter.reader_search import MAX_REGEX_PATTERN_LENGTH, search_messages_page

CHAT_ID = -(10**12 + 3191)


class FakeMessage:
    def __init__(self, message_id: int, text: str, sender_id: int = 1):
        self.id = message_id
        self.message = text
        self.date = datetime(2026, 8, 30, 5, 0, message_id, tzinfo=timezone.utc)
        self.sender_id = sender_id
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
        contains = kwargs.get("search")
        if contains:
            rows = [row for row in rows if str(contains).casefold() in row.message.casefold()]

        async def iterator():
            for row in rows[: int(kwargs.get("limit", len(rows)))]:
                yield row

        return iterator()


class FakeReader:
    def __init__(self, messages: list[FakeMessage]):
        self.cursor = CursorCodec(b"g" * 32)
        self.client = FakeClient(messages)
        self.resolve_calls = 0
        self.row = DialogInfo(
            chat_id=CHAT_ID,
            title="Synthetic Regex Fixture",
            username=None,
            dialog_type="supergroup",
        )

    async def resolve_dialog(self, _reference):
        self.resolve_calls += 1
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
                display_name="Synthetic Sender",
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


def test_regex_search_is_case_insensitive_by_default(monkeypatch) -> None:
    monkeypatch.setattr(search_module, "Message", FakeMessage)
    reader = FakeReader(
        [
            FakeMessage(3, "PikPak release-42"),
            FakeMessage(2, "other text"),
        ]
    )
    page = asyncio.run(search_messages_page(reader, chat=CHAT_ID, regex=r"pikpak\s+release-\d+", limit=10))
    assert [row.message_id for row in page.items] == [3]


def test_regex_search_respects_case_sensitive(monkeypatch) -> None:
    monkeypatch.setattr(search_module, "Message", FakeMessage)
    reader = FakeReader([FakeMessage(2, "pikpak"), FakeMessage(1, "PikPak")])
    page = asyncio.run(
        search_messages_page(reader, chat=CHAT_ID, regex=r"^PikPak$", case_sensitive=True, limit=10)
    )
    assert [row.message_id for row in page.items] == [1]


@pytest.mark.parametrize("pattern", ["(", "x" * (MAX_REGEX_PATTERN_LENGTH + 1)])
def test_invalid_regex_is_structured_before_telegram_work(pattern: str) -> None:
    reader = FakeReader([])
    with pytest.raises(TelegramBridgeError) as captured:
        asyncio.run(search_messages_page(reader, chat=CHAT_ID, regex=pattern, limit=10))
    assert captured.value.code == INVALID_ARGUMENT
    assert reader.resolve_calls == 0


def test_regex_cursor_has_no_overlap_and_is_query_bound(monkeypatch) -> None:
    monkeypatch.setattr(search_module, "Message", FakeMessage)
    reader = FakeReader(
        [
            FakeMessage(4, "code-400"),
            FakeMessage(3, "code-300"),
            FakeMessage(2, "code-200"),
        ]
    )
    first = asyncio.run(search_messages_page(reader, chat=CHAT_ID, regex=r"code-\d+", limit=1))
    assert first.next_cursor
    second = asyncio.run(
        search_messages_page(reader, chat=CHAT_ID, regex=r"code-\d+", limit=1, cursor=first.next_cursor)
    )
    assert {row.message_id for row in first.items}.isdisjoint({row.message_id for row in second.items})

    with pytest.raises(TelegramBridgeError) as captured:
        asyncio.run(
            search_messages_page(
                reader,
                chat=CHAT_ID,
                regex=r"code-[12]00",
                limit=1,
                cursor=first.next_cursor,
            )
        )
    assert captured.value.code == INVALID_CURSOR


def test_regex_composes_with_domain_and_sender_role(monkeypatch) -> None:
    monkeypatch.setattr(search_module, "Message", FakeMessage)
    reader = FakeReader(
        [
            FakeMessage(4, "release-42 https://cdn.mypikpak.com/x", sender_id=1),
            FakeMessage(3, "release-42 https://mypikpak.com/x", sender_id=2),
            FakeMessage(2, "other https://mypikpak.com/x", sender_id=1),
        ]
    )
    page = asyncio.run(
        search_messages_page(
            reader,
            chat=CHAT_ID,
            regex=r"release-\d+",
            url_domain="mypikpak.com",
            sender_role="admin",
            limit=10,
        )
    )
    assert [row.message_id for row in page.items] == [4]


def test_tgctl_source_cli_passes_regex_to_v3_ipc(monkeypatch) -> None:
    class FakeIPC:
        def __init__(self):
            self.calls = []

        async def request(self, method, params=None, **_kwargs):
            self.calls.append((method, params))
            return {"items": [], "count": 0, "has_more": False}

    class FakeProxy:
        last = None

        def __init__(self, kind):
            assert kind == "tgctl"
            self.ipc = FakeIPC()
            FakeProxy.last = self

    monkeypatch.setattr(tgctl_module, "DaemonTelegramProxy", FakeProxy)
    args = tgctl_module.build_parser().parse_args(
        ["messages", "search", "--chat", str(CHAT_ID), "--regex", r"release-\d+", "--json"]
    )
    payload = asyncio.run(tgctl_module.run_command(args))
    assert payload["ok"] is True
    method, params = FakeProxy.last.ipc.calls[-1]
    assert method == "messages.search"
    assert params["schema"] == "v3"
    assert params["regex"] == r"release-\d+"


def test_legacy_search_rejects_regex(monkeypatch) -> None:
    class FakeProxy:
        def __init__(self, _kind):
            self.ipc = None

    monkeypatch.setattr(tgctl_module, "DaemonTelegramProxy", FakeProxy)
    args = tgctl_module.build_parser().parse_args(
        ["messages", "search", "--chat", str(CHAT_ID), "--regex", "x", "--legacy-schema", "--json"]
    )
    with pytest.raises(TelegramBridgeError) as captured:
        asyncio.run(tgctl_module.run_command(args))
    assert captured.value.code == INVALID_ARGUMENT
