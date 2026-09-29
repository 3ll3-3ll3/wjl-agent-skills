from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from telegram_exporter import forwarding
from telegram_exporter.bridge_errors import (
    CONTENT_PROTECTED,
    MESSAGE_NOT_FOUND,
    SERVICE_MESSAGE,
    WRITE_OUTCOME_UNKNOWN,
    TelegramBridgeError,
)
from telegram_exporter.models import GroupInfo
from telegram_exporter.telegram_service import TelegramService


class MessageMediaPhoto:
    pass


class FakeMessage:
    def __init__(
        self,
        message_id: int,
        *,
        text: str = "",
        photo: bool = False,
        grouped_id: int | None = None,
        action=None,
        noforwards: bool = False,
    ) -> None:
        self.id = message_id
        self.message = text
        self.date = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.media = MessageMediaPhoto() if photo else None
        self.grouped_id = grouped_id
        self.action = action
        self.noforwards = noforwards
        self.entities = (SimpleNamespace(kind="bold"),) if text else ()


class FakeClient:
    def __init__(self, messages: list[FakeMessage], *, protected_source: bool = False) -> None:
        self.messages = {message.id: message for message in messages}
        self.source_entity = SimpleNamespace(noforwards=protected_source)
        self.forward_calls: list[tuple[object, list[int], object]] = []
        self.download_calls = 0
        self.send_calls = 0
        self.forward_error: Exception | None = None
        self.forward_result_override = None

    async def get_entity(self, value):
        if value == -1001:
            return self.source_entity
        return value

    async def get_messages(self, _entity, ids):
        return [self.messages.get(int(message_id)) for message_id in ids]

    async def forward_messages(self, destination, ids, from_peer=None):
        self.forward_calls.append((destination, list(ids), from_peer))
        if self.forward_error is not None:
            raise self.forward_error
        if self.forward_result_override is not None:
            return self.forward_result_override
        return [SimpleNamespace(id=5000 + int(message_id)) for message_id in ids]

    async def download_media(self, *_args, **_kwargs):
        self.download_calls += 1
        raise AssertionError("native forward must never call download_media")

    async def send_message(self, *_args, **_kwargs):
        self.send_calls += 1
        raise AssertionError("native forward must never rebuild a message with send_message")


def make_service(messages: list[FakeMessage], *, protected_source: bool = False) -> TelegramService:
    service = object.__new__(TelegramService)
    service.client = FakeClient(messages, protected_source=protected_source)

    async def list_groups():
        return [GroupInfo(chat_id=-1001, title="测试来源", chat_type="supergroup")]

    service.list_groups = list_groups
    return service


@pytest.mark.parametrize("caption", ["", "示例 caption"])
def test_single_photo_and_caption_use_native_forward(caption: str) -> None:
    message = FakeMessage(10, text=caption, photo=True)
    service = make_service([message])

    result = asyncio.run(service.forward_messages(-1001, "me", [10], dry_run=False))

    assert result.requested_count == 1
    assert result.forwardable_count == 1
    assert result.photo_count == 1
    assert result.album_count == 0
    assert result.successful_ids == (10,)
    assert result.target_message_ids == (5010,)
    assert result.forwarded[0].source_message_id == 10
    assert result.forwarded[0].target_message_id == 5010
    assert service.client.forward_calls == [("me", [10], service.client.source_entity)]
    assert service.client.download_calls == 0
    assert service.client.send_calls == 0
    assert message.message == caption
    assert len(message.entities) == (1 if caption else 0)


def test_dry_run_expands_complete_album_without_remote_write() -> None:
    album = [
        FakeMessage(20, photo=True, grouped_id=700),
        FakeMessage(21, text="album caption", photo=True, grouped_id=700),
        FakeMessage(22, photo=True, grouped_id=700),
    ]
    service = make_service(album)

    result = asyncio.run(service.forward_messages(-1001, "me", [21], dry_run=True))

    assert result.requested_count == 1
    assert result.forwardable_count == 3
    assert result.photo_count == 3
    assert result.album_count == 1
    assert result.planned_ids == (20, 21, 22)
    assert result.expanded_ids == (20, 22)
    assert result.albums[0].grouped_id == 700
    assert result.albums[0].message_ids == (20, 21, 22)
    assert result.target_message_ids == ()
    assert service.client.forward_calls == []
    assert service.client.download_calls == 0
    assert service.client.send_calls == 0


def test_complete_album_is_forwarded_contiguously_in_one_native_call() -> None:
    album = [
        FakeMessage(20, photo=True, grouped_id=700),
        FakeMessage(21, text="album caption", photo=True, grouped_id=700),
        FakeMessage(22, photo=True, grouped_id=700),
    ]
    service = make_service(album)

    result = asyncio.run(service.forward_messages(-1001, "me", [21], dry_run=False))

    assert result.successful_ids == (20, 21, 22)
    assert result.target_message_ids == (5020, 5021, 5022)
    assert [call[1] for call in service.client.forward_calls] == [[20, 21, 22]]


def test_multiple_albums_and_single_photo_preserve_unit_order() -> None:
    messages = [
        FakeMessage(20, photo=True, grouped_id=700),
        FakeMessage(21, photo=True, grouped_id=700),
        FakeMessage(30, photo=True),
        FakeMessage(40, photo=True, grouped_id=800),
        FakeMessage(41, text="second album", photo=True, grouped_id=800),
        FakeMessage(42, photo=True, grouped_id=800),
    ]
    service = make_service(messages)

    result = asyncio.run(service.forward_messages(-1001, "me", [21, 30, 41], dry_run=False))

    assert result.planned_ids == (20, 21, 30, 40, 41, 42)
    assert result.photo_count == 6
    assert result.album_count == 2
    assert [album.message_ids for album in result.albums] == [(20, 21), (40, 41, 42)]
    assert service.client.forward_calls[0][1] == [20, 21, 30, 40, 41, 42]
    assert service.client.download_calls == 0
    assert service.client.send_calls == 0


def test_source_protected_content_returns_per_item_failures_and_no_write() -> None:
    service = make_service(
        [FakeMessage(10, photo=True), FakeMessage(11, text="text")],
        protected_source=True,
    )

    result = asyncio.run(service.forward_messages(-1001, "me", [10, 11], dry_run=False))

    assert result.forwardable_count == 0
    assert result.successful_ids == ()
    assert result.failed_ids == (10, 11)
    assert [failure.code for failure in result.failures] == [CONTENT_PROTECTED, CONTENT_PROTECTED]
    assert service.client.forward_calls == []
    assert service.client.download_calls == 0


def test_partial_missing_message_is_machine_readable_while_existing_message_forwards() -> None:
    service = make_service([FakeMessage(10, photo=True)])

    result = asyncio.run(service.forward_messages(-1001, "me", [10, 99], dry_run=False))

    assert result.successful_ids == (10,)
    assert result.failed_ids == (99,)
    assert len(result.failures) == 1
    assert result.failures[0].message_id == 99
    assert result.failures[0].code == MESSAGE_NOT_FOUND
    assert result.target_message_ids == (5010,)


def test_service_message_is_excluded_with_reason() -> None:
    service = make_service([FakeMessage(10, action=SimpleNamespace(kind="service"))])

    result = asyncio.run(service.forward_messages(-1001, "me", [10], dry_run=True))

    assert result.failed_ids == (10,)
    assert result.failures[0].code == SERVICE_MESSAGE
    assert result.forwardable_count == 0


def test_flood_wait_is_not_retried(monkeypatch) -> None:
    class FakeFloodWait(Exception):
        pass

    monkeypatch.setattr(forwarding, "FloodWaitError", FakeFloodWait)
    service = make_service([FakeMessage(10, photo=True)])
    service.client.forward_error = FakeFloodWait()

    with pytest.raises(FakeFloodWait):
        asyncio.run(service.forward_messages(-1001, "me", [10], dry_run=False))

    assert len(service.client.forward_calls) == 1


def test_unknown_outcome_is_structured_and_never_retried() -> None:
    service = make_service([FakeMessage(10, photo=True)])
    service.client.forward_error = RuntimeError("simulated transport ambiguity")

    with pytest.raises(TelegramBridgeError) as exc_info:
        asyncio.run(service.forward_messages(-1001, "me", [10], dry_run=False))

    assert exc_info.value.code == WRITE_OUTCOME_UNKNOWN
    assert len(service.client.forward_calls) == 1
    assert service.client.download_calls == 0


def test_incomplete_target_id_response_is_unknown_outcome() -> None:
    service = make_service([FakeMessage(10, photo=True), FakeMessage(11, photo=True)])
    service.client.forward_result_override = [SimpleNamespace(id=9001)]

    with pytest.raises(TelegramBridgeError) as exc_info:
        asyncio.run(service.forward_messages(-1001, "me", [10, 11], dry_run=False))

    assert exc_info.value.code == WRITE_OUTCOME_UNKNOWN
    assert len(service.client.forward_calls) == 1


def test_forwardable_text_compatibility_remains() -> None:
    service = make_service([FakeMessage(10, text="plain text")])

    result = asyncio.run(service.forward_messages(-1001, "me", [10], dry_run=False))

    assert result.successful_ids == (10,)
    assert result.photo_count == 0
    assert result.target_message_ids == (5010,)
