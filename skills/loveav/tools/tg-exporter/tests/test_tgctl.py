from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from telegram_exporter import telegram_service as service_module
from telegram_exporter.bridge_errors import (
    AMBIGUOUS_CHAT,
    CHAT_NOT_FOUND,
    INVALID_ARGUMENT,
    MESSAGE_NOT_FOUND,
    TelegramBridgeError,
)
from telegram_exporter.models import GroupInfo
from telegram_exporter.telegram_service import TelegramService
from telegram_exporter import tgctl


def test_cli_parser_accepts_required_commands() -> None:
    parser = tgctl.build_parser()
    args = parser.parse_args(["messages", "search", "--chat", "-1001", "--contains", "预推免", "--json"])
    assert args.command == "messages"
    assert args.messages_command == "search"
    assert args.chat == "-1001"
    assert args.contains == "预推免"
    assert args.json is True


def test_version_is_machine_readable_without_starting_daemon(monkeypatch, capsys) -> None:
    class ForbiddenProxy:
        def __init__(self, _client_kind: str):
            raise AssertionError("version must not create a daemon proxy")

    monkeypatch.setattr(tgctl, "DaemonTelegramProxy", ForbiddenProxy)
    def forbidden_logging() -> None:
        raise AssertionError("version must not create a log file")

    monkeypatch.setattr(tgctl, "setup_logging", forbidden_logging)
    code = tgctl.main(["version", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload == {
        "ok": True,
        "data": {
            "tgctl_version": "0.3.3",
            "reader_schema": "tgctl.reader.v1",
            "ipc_protocol": "tgipc/1",
        },
    }


def test_status_adds_versions_schema_capabilities_and_compatibility(monkeypatch) -> None:
    class FakeIPC:
        async def request(self, method: str):
            assert method == "system.hello"
            return {
                "daemon_app_version": "0.3.3",
                "protocol": "tgipc/1",
                "reader_schema": "tgctl.reader.v1",
                "capabilities": ["messages.history"],
            }

    class FakeProxy:
        def __init__(self, client_kind: str):
            assert client_kind == "tgctl"
            self.ipc = FakeIPC()

        async def status(self):
            return {"authorized": True, "state": "connected"}

    monkeypatch.setattr(tgctl, "DaemonTelegramProxy", FakeProxy)
    args = tgctl.build_parser().parse_args(["status", "--json"])
    payload = asyncio.run(tgctl.run_command(args))

    assert payload["ok"] is True
    assert payload["data"] == {
        "authorized": True,
        "state": "connected",
        "tgctl_version": "0.3.3",
        "daemon_version": "0.3.3",
        "reader_schema": "tgctl.reader.v1",
        "ipc_protocol": "tgipc/1",
        "compatible": True,
        "same_version": True,
        "capabilities": ["messages.history"],
    }


def test_json_mode_writes_only_json_stdout(monkeypatch, capsys) -> None:
    async def fake_run(_args):
        return tgctl.success({"authorized": True})

    monkeypatch.setattr(tgctl, "setup_logging", lambda: None)
    monkeypatch.setattr(tgctl, "run_command", fake_run)
    code = tgctl.main(["status", "--json"])
    captured = capsys.readouterr()
    assert code == 0
    assert captured.err == ""
    assert json.loads(captured.out) == {"ok": True, "data": {"authorized": True}}


def test_resolve_group_rejects_ambiguous_title() -> None:
    service = object.__new__(TelegramService)
    groups = [
        GroupInfo(chat_id=-1001, title="AI交流群", chat_type="supergroup"),
        GroupInfo(chat_id=-1002, title="AI交流群", chat_type="supergroup"),
    ]
    with pytest.raises(TelegramBridgeError) as exc_info:
        asyncio.run(service.resolve_group("AI交流群", groups))
    assert exc_info.value.code == AMBIGUOUS_CHAT
    assert {item["chat_id"] for item in exc_info.value.details} == {-1001, -1002}


def test_resolve_group_reports_chat_not_found() -> None:
    service = object.__new__(TelegramService)
    with pytest.raises(TelegramBridgeError) as exc_info:
        asyncio.run(service.resolve_group("不存在", [GroupInfo(chat_id=-1001, title="存在")]))
    assert exc_info.value.code == CHAT_NOT_FOUND


class FakeMessage:
    def __init__(self, message_id: int, text: str, date: datetime, *, media=None):
        self.id = message_id
        self.message = text
        self.date = date
        self.media = media
        self.action = None
        self.grouped_id = None
        self.noforwards = False

    async def get_sender(self):
        return SimpleNamespace(first_name="测试", last_name="发送者", title=None, username="sender")


class FakeClient:
    def __init__(self, messages: list[FakeMessage]):
        self.messages = messages
        self.forward_calls = []
        self.send_calls = []

    async def get_entity(self, value):
        return value

    def iter_messages(self, _entity, **_kwargs):
        async def iterator():
            for message in self.messages:
                yield message
        return iterator()

    async def get_messages(self, _entity, ids):
        by_id = {message.id: message for message in self.messages}
        return [by_id.get(int(message_id)) for message_id in ids]

    async def forward_messages(self, destination, ids, from_peer=None):
        self.forward_calls.append((destination, list(ids), from_peer))
        return [SimpleNamespace(id=1000 + int(message_id)) for message_id in ids]

    async def send_message(self, destination, text, **kwargs):
        self.send_calls.append((destination, text, kwargs))
        return SimpleNamespace(id=999)


def _fake_service(monkeypatch, messages: list[FakeMessage]) -> TelegramService:
    monkeypatch.setattr(service_module, "Message", FakeMessage)
    service = object.__new__(TelegramService)
    service.client = FakeClient(messages)

    async def list_groups():
        return [GroupInfo(chat_id=-1001, title="保研群", username="baoyan", chat_type="supergroup")]

    service.list_groups = list_groups
    return service


def test_search_filter_is_deterministic(monkeypatch) -> None:
    service = _fake_service(
        monkeypatch,
        [
            FakeMessage(3, "今天有预推免通知", datetime(2026, 8, 29, 12, tzinfo=timezone.utc)),
            FakeMessage(2, "普通通知", datetime(2026, 8, 29, 10, tzinfo=timezone.utc)),
            FakeMessage(1, "更早的预推免", datetime(2026, 8, 28, 10, tzinfo=timezone.utc)),
        ],
    )
    rows = asyncio.run(
        service.search_messages(
            -1001,
            contains="预推免",
            since=datetime(2026, 8, 29, 0, tzinfo=timezone.utc),
            until=datetime(2026, 8, 30, 0, tzinfo=timezone.utc),
            limit=20,
        )
    )
    assert [row.message_id for row in rows] == [3]
    assert rows[0].text == "今天有预推免通知"


def test_get_messages_reports_missing_id(monkeypatch) -> None:
    service = _fake_service(
        monkeypatch,
        [FakeMessage(10, "存在", datetime(2026, 8, 29, 12, tzinfo=timezone.utc))],
    )
    with pytest.raises(TelegramBridgeError) as exc_info:
        asyncio.run(service.get_messages(-1001, [10, 11]))
    assert exc_info.value.code == MESSAGE_NOT_FOUND
    assert exc_info.value.details == {"missing_ids": [11]}


def test_forward_dry_run_never_calls_telegram_write(monkeypatch) -> None:
    service = _fake_service(
        monkeypatch,
        [FakeMessage(10, "safe text", datetime(2026, 8, 29, 12, tzinfo=timezone.utc))],
    )
    result = asyncio.run(service.forward_messages(-1001, "me", [10], dry_run=True))
    assert result.dry_run is True
    assert result.successful_ids == (10,)
    assert service.client.forward_calls == []


def test_forward_real_uses_true_telegram_forward(monkeypatch) -> None:
    service = _fake_service(
        monkeypatch,
        [FakeMessage(10, "safe text", datetime(2026, 8, 29, 12, tzinfo=timezone.utc))],
    )
    result = asyncio.run(service.forward_messages(-1001, "me", [10], dry_run=False))
    assert result.dry_run is False
    assert result.successful_ids == (10,)
    assert result.target_message_ids == (1010,)
    assert service.client.forward_calls == [("me", [10], -1001)]
    assert service.client.send_calls == []


def test_send_dry_run_never_calls_telegram_write_or_log_body(monkeypatch, caplog) -> None:
    service = _fake_service(monkeypatch, [])
    secret_body = "TG Exporter Codex bridge test SECRET-BODY"
    caplog.set_level(logging.INFO)
    result = asyncio.run(service.send_text_message("me", secret_body, dry_run=True))
    assert result.dry_run is True
    assert service.client.send_calls == []
    assert secret_body not in caplog.text


def test_send_real_is_plain_text_without_parse_mode(monkeypatch, caplog) -> None:
    service = _fake_service(monkeypatch, [])
    body = "plain text only"
    caplog.set_level(logging.INFO)
    result = asyncio.run(service.send_text_message("me", body, dry_run=False))
    assert result.message_id == 999
    assert service.client.send_calls == [
        ("me", body, {"parse_mode": None, "link_preview": False})
    ]
    assert body not in caplog.text


def test_forward_batch_limit_requires_explicit_override() -> None:
    with pytest.raises(TelegramBridgeError) as exc_info:
        tgctl.validate_forward_batch(list(range(21)), False)
    assert exc_info.value.code == INVALID_ARGUMENT
    tgctl.validate_forward_batch(list(range(20)), False)
    tgctl.validate_forward_batch(list(range(21)), True)
    tgctl.validate_forward_batch(list(range(200)), True)
    with pytest.raises(TelegramBridgeError):
        tgctl.validate_forward_batch(list(range(201)), True)


def test_flood_wait_maps_to_structured_error(monkeypatch, capsys) -> None:
    class FakeFloodWait(Exception):
        def __init__(self, seconds: int):
            self.seconds = seconds

    async def fake_run(_args):
        raise FakeFloodWait(37)

    monkeypatch.setattr(tgctl, "FloodWaitError", FakeFloodWait)
    monkeypatch.setattr(tgctl, "setup_logging", lambda: None)
    monkeypatch.setattr(tgctl, "run_command", fake_run)
    code = tgctl.main(["status", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 6
    assert payload["ok"] is False
    assert payload["error"]["code"] == "FLOOD_WAIT"
    assert payload["error"]["details"]["retry_after_seconds"] == 37


def test_safe_output_never_contains_credential_fields() -> None:
    payload = tgctl.success(
        {
            "authorized": True,
            "account": {"user_id": 123, "display_name": "Example", "username": "example"},
            "session": tgctl.SAFE_SESSION_LABEL,
            "proxy": "direct",
        }
    )
    serialized = json.dumps(payload, ensure_ascii=False)
    for forbidden in ("api_hash", "phone", "otp", "2fa", "session_content"):
        assert forbidden not in serialized.casefold()
