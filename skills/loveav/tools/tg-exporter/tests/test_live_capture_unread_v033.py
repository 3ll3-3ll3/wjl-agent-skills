from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from telegram_exporter import live_capture, reader_unread, tgctl
from telegram_exporter.bridge_errors import EXPORT_IN_PROGRESS, INVALID_ARGUMENT, TelegramBridgeError
from telegram_exporter.cursor_codec import CursorCodec
from telegram_exporter.daemon_server_v3 import DaemonServer


class FakeMessage:
    def __init__(self, message_id: int, text: str, *, out: bool = False):
        self.id = message_id
        self.message = text
        self.out = out
        self.date = datetime(2026, 9, 8, tzinfo=timezone.utc)
        self.entities = []
        self.peer_id = -1009


class FakeReader:
    def __init__(self, client):
        self.client = client
        self.cursor = CursorCodec(b"unit-test-secret")
        self.telegram_service = SimpleNamespace()

    async def resolve_dialog(self, _chat):
        return SimpleNamespace(chat_id=-1009, title="test"), "entity"

    async def _message_info_v3(self, _row, chat_id, message, _roles, _available):
        return SimpleNamespace(
            chat_id=chat_id,
            source_chat_id=chat_id,
            message_id=message.id,
            text=message.message,
            caption=None,
        )


def test_unread_snapshot_pages_keep_the_same_signed_bounds(monkeypatch) -> None:
    class Client:
        def __init__(self):
            self.rows = [FakeMessage(value, f"m{value}") for value in range(11, 16)]
            self.ack = None

        def iter_messages(self, _entity, **kwargs):
            async def iterator():
                rows = [
                    row for row in self.rows
                    if row.id > kwargs["min_id"] and row.id < kwargs["max_id"]
                ]
                for row in rows[: kwargs["limit"]]:
                    yield row
            return iterator()

        async def send_read_acknowledge(self, _entity, *, max_id):
            self.ack = max_id

    async def snapshot(_client, _group):
        return SimpleNamespace(read_inbox_max_id=10, latest_message_id=15, unread_count=5)

    reader = FakeReader(Client())
    reader.telegram_service.list_groups = lambda: _async_value([SimpleNamespace(chat_id=-1009)])
    reader.telegram_service.resolve_group = lambda *_args: _async_value(SimpleNamespace(chat_id=-1009))
    monkeypatch.setattr(reader_unread, "capture_current_unread_snapshot", snapshot)

    first = asyncio.run(reader_unread.unread_snapshot_page(reader, -1009, limit=2))
    second = asyncio.run(reader_unread.unread_snapshot_page(reader, -1009, cursor=first["next_cursor"], limit=2))
    third = asyncio.run(reader_unread.unread_snapshot_page(reader, -1009, cursor=second["next_cursor"], limit=2))

    assert [row.message_id for row in first["items"]] == [11, 12]
    assert [row.message_id for row in second["items"]] == [13, 14]
    assert [row.message_id for row in third["items"]] == [15]
    assert {page["lower"] for page in (first, second, third)} == {10}
    assert {page["upper"] for page in (first, second, third)} == {15}
    assert {page["snapshot_token"] for page in (first, second, third)} == {first["snapshot_token"]}

    result = asyncio.run(
        reader_unread.mark_snapshot_read(
            reader,
            -1009,
            snapshot_token=first["snapshot_token"],
            max_id=15,
            confirmation=reader_unread.READ_ACK_CONFIRMATION,
        )
    )
    assert result["acknowledged_max_id"] == 15
    assert reader.client.ack == 15


def _async_value(value):
    async def result():
        return value
    return result()


def test_mark_read_rejects_wrong_confirmation_and_out_of_bounds() -> None:
    reader = FakeReader(SimpleNamespace())
    token = reader.cursor.encode("messages.mark_read", {"chat_id": -1009}, {"lower": 10, "upper": 15})

    with pytest.raises(TelegramBridgeError) as wrong:
        asyncio.run(reader_unread.mark_snapshot_read(reader, -1009, snapshot_token=token, max_id=15, confirmation="no"))
    assert wrong.value.code == INVALID_ARGUMENT

    with pytest.raises(TelegramBridgeError) as beyond:
        asyncio.run(
            reader_unread.mark_snapshot_read(
                reader,
                -1009,
                snapshot_token=token,
                max_id=16,
                confirmation=reader_unread.READ_ACK_CONFIRMATION,
            )
        )
    assert beyond.value.code == INVALID_ARGUMENT


def test_send_capture_subscribes_before_send_filters_domain_and_hides_body_from_logs(monkeypatch, caplog) -> None:
    class Client:
        def __init__(self):
            self.handler = None
            self.builder = None
            self.removed = False

        def add_event_handler(self, handler, builder):
            self.handler = handler
            self.builder = builder

        def remove_event_handler(self, handler, builder):
            assert handler is self.handler and builder is self.builder
            self.removed = True

        async def send_message(self, _entity, _body, **_kwargs):
            assert self.handler is not None
            await self.handler(SimpleNamespace(chat_id=-1009, message=FakeMessage(90, "https://evil.example/x")))
            await self.handler(SimpleNamespace(chat_id=-1009, message=FakeMessage(88, "https://mypikpak.com/s/stale")))
            await self.handler(SimpleNamespace(chat_id=-1009, message=FakeMessage(91, "https://mypikpak.com/s/good\n密码: a1")))
            return SimpleNamespace(id=89)

    client = Client()
    reader = FakeReader(client)
    monkeypatch.setattr(live_capture, "Message", FakeMessage)
    caplog.set_level("INFO")
    secret = "#private-keyword"
    result = asyncio.run(
        live_capture.send_and_capture(
            reader,
            -1009,
            secret,
            first_reply_timeout_seconds=0.2,
            settle_seconds=0.1,
            url_domain="mypikpak.com",
        )
    )

    assert result["sent_message_id"] == 89
    assert result["captured_count"] == 1
    assert result["captured"][0].message_id == 91
    assert client.removed is True
    assert secret not in caplog.text


def test_send_capture_dry_run_does_not_subscribe_or_write(monkeypatch) -> None:
    class Client:
        def add_event_handler(self, *_args):
            raise AssertionError("dry-run must not subscribe")

        async def send_message(self, *_args, **_kwargs):
            raise AssertionError("dry-run must not send")

    monkeypatch.setattr(live_capture, "Message", FakeMessage)
    result = asyncio.run(live_capture.send_and_capture(FakeReader(Client()), -1009, "#demo", dry_run=True))
    assert result["dry_run"] is True
    assert result["captured_count"] == 0


def test_tgctl_write_commands_never_retry_after_request_send(monkeypatch) -> None:
    calls = []

    class IPC:
        async def request(self, method, params=None, **kwargs):
            calls.append((method, params, kwargs))
            return {"ok": True}

    class Proxy:
        def __init__(self, _kind):
            self.ipc = IPC()

    monkeypatch.setattr(tgctl, "DaemonTelegramProxy", Proxy)
    mark = tgctl.build_parser().parse_args(
        [
            "messages", "mark-read", "--chat", "-1009", "--snapshot-token", "signed",
            "--max-id", "15", "--confirm", reader_unread.READ_ACK_CONFIRMATION, "--json",
        ]
    )
    capture = tgctl.build_parser().parse_args(
        ["send-capture", "--to", "-1008", "--text", "#demo", "--url-domain", "mypikpak.com", "--json"]
    )
    asyncio.run(tgctl.run_command(mark))
    asyncio.run(tgctl.run_command(capture))

    assert calls[0][0] == "messages.mark_read"
    assert calls[0][2] == {"side_effect_after_send": True, "retry_read_once": False}
    assert calls[1][0] == "send.capture"
    assert calls[1][2] == {"side_effect_after_send": True, "retry_read_once": False}


def test_daemon_advertises_new_capabilities_and_rejects_write_during_export() -> None:
    async def scenario():
        server = DaemonServer()
        client = {"kind": "tgctl", "app_version": "0.3.3"}
        hello = await server.dispatch({"method": "system.hello", "params": {}, "client": client})
        assert {
            "messages.current_unread_snapshot",
            "messages.mark_read_frozen_snapshot",
            "send.capture",
        }.issubset(set(hello["capabilities"]))

        await server.operations.reserve_export()
        try:
            with pytest.raises(TelegramBridgeError) as exc_info:
                await server.dispatch({
                    "method": "send.capture",
                    "params": {"destination_chat": "me", "text": "#demo", "dry_run": False},
                    "client": client,
                })
            assert exc_info.value.code == EXPORT_IN_PROGRESS
        finally:
            await server.operations.cancel_export_reservation()

    asyncio.run(scenario())
