from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from telegram_exporter import telegram_service as service_module
from telegram_exporter.bridge_errors import (
    CONTENT_PROTECTED,
    FLOOD_WAIT,
    MESSAGE_NOT_FOUND,
    UNKNOWN_OUTCOME,
    TelegramBridgeError,
)
from telegram_exporter.models import GroupInfo
from telegram_exporter.telegram_service import TelegramService

SOURCE_CHAT = -900001
DESTINATION_CHAT = -900002


class MessageMediaPhoto:
    pass


class MessageMediaDocument:
    pass


class FakeEntity:
    def __init__(self, entity_id: int, *, noforwards: bool = False) -> None:
        self.id = entity_id
        self.noforwards = noforwards


class FakeMessage:
    def __init__(
        self,
        message_id: int,
        *,
        text: str = "",
        media=None,
        grouped_id: int | None = None,
        action=None,
        noforwards: bool = False,
        entities=None,
    ) -> None:
        self.id = message_id
        self.message = text
        self.date = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.media = media
        self.grouped_id = grouped_id
        self.action = action
        self.noforwards = noforwards
        self.entities = entities
        self.photo = object() if isinstance(media, MessageMediaPhoto) else None

    async def get_sender(self):
        return None


class FakeClient:
    def __init__(
        self,
        messages: list[FakeMessage],
        *,
        source_protected: bool = False,
        forward_error: Exception | None = None,
        mismatch_result: bool = False,
    ) -> None:
        self.messages = messages
        self.source_entity = FakeEntity(SOURCE_CHAT, noforwards=source_protected)
        self.destination_entity = FakeEntity(DESTINATION_CHAT)
        self.forward_error = forward_error
        self.mismatch_result = mismatch_result
        self.forward_calls: list[tuple[object, list[int], object]] = []
        self.send_calls: list[tuple] = []
        self.download_media_calls = 0
        self.destination_messages = [FakeMessage(7000, text="existing")]

    async def get_entity(self, value):
        if value == SOURCE_CHAT:
            return self.source_entity
        if value == DESTINATION_CHAT:
            return self.destination_entity
        return value

    async def get_messages(self, entity, ids=None, limit=None):
        if ids is None:
            if (entity is self.destination_entity or entity == "me") and limit == 1:
                return [self.destination_messages[-1]] if self.destination_messages else []
            return []
        by_id = {message.id: message for message in self.messages}
        return [by_id.get(int(message_id)) for message_id in ids]

    async def forward_messages(self, destination, ids, from_peer=None):
        source_ids = [int(value) for value in ids]
        self.forward_calls.append((destination, source_ids, from_peer))
        if self.forward_error is not None:
            raise self.forward_error
        returned = []
        for _source_id in source_ids:
            new_id = self.destination_messages[-1].id + 1
            target = FakeMessage(new_id, text="forwarded")
            self.destination_messages.append(target)
            returned.append(target)
        if self.mismatch_result and returned:
            return returned[:-1]
        return returned

    async def send_message(self, *args, **kwargs):
        self.send_calls.append((args, kwargs))
        raise AssertionError("native forward must not rebuild media with send_message")

    async def download_media(self, *args, **kwargs):
        self.download_media_calls += 1
        raise AssertionError("native forward must not download media")


def make_service(monkeypatch, messages: list[FakeMessage], **client_kwargs) -> TelegramService:
    monkeypatch.setattr(service_module, "Message", FakeMessage)
    service = object.__new__(TelegramService)
    service.client = FakeClient(messages, **client_kwargs)

    async def list_groups():
        return [
            GroupInfo(chat_id=SOURCE_CHAT, title="Synthetic Source", chat_type="supergroup"),
            GroupInfo(chat_id=DESTINATION_CHAT, title="Synthetic Destination", chat_type="supergroup"),
        ]

    service.list_groups = list_groups
    return service


def photo(message_id: int, *, caption: str = "", grouped_id: int | None = None, entities=None) -> FakeMessage:
    return FakeMessage(
        message_id,
        text=caption,
        media=MessageMediaPhoto(),
        grouped_id=grouped_id,
        entities=entities,
    )


def test_single_photo_with_caption_uses_native_forward_and_returns_destination_id(monkeypatch) -> None:
    entities = [SimpleNamespace(offset=0, length=7)]
    source = photo(101, caption="caption", entities=entities)
    service = make_service(monkeypatch, [source])

    result = asyncio.run(service.forward_messages(SOURCE_CHAT, DESTINATION_CHAT, [101]))

    assert result.successful_ids == (101,)
    assert result.photo_count == 1
    assert result.album_count == 0
    assert result.destination_message_ids == (7001,)
    assert result.forwarded_messages[0].source_message_id == 101
    assert result.forwarded_messages[0].destination_message_id == 7001
    assert result.destination_before_message_id == 7000
    assert result.destination_after_message_id == 7001
    assert service.client.forward_calls == [(service.client.destination_entity, [101], service.client.source_entity)]
    assert service.client.send_calls == []
    assert service.client.download_media_calls == 0
    assert source.message == "caption"
    assert source.entities is entities


def test_dry_run_reports_complete_album_and_never_writes(monkeypatch) -> None:
    messages = [photo(201, grouped_id=8801), photo(202, caption="album caption", grouped_id=8801), photo(203, grouped_id=8801)]
    service = make_service(monkeypatch, messages)

    result = asyncio.run(service.forward_messages(SOURCE_CHAT, DESTINATION_CHAT, [202], dry_run=True))

    assert result.requested_count == 1
    assert result.forwardable_count == 3
    assert result.photo_count == 3
    assert result.album_count == 1
    assert result.planned_ids == (201, 202, 203)
    assert result.albums[0].grouped_id == 8801
    assert result.albums[0].message_ids == (201, 202, 203)
    assert result.excluded == ()
    assert service.client.forward_calls == []
    assert service.client.download_media_calls == 0


def test_multiple_albums_and_single_photo_preserve_unit_order(monkeypatch) -> None:
    messages = [
        photo(301, grouped_id=9101),
        photo(302, grouped_id=9101),
        photo(350),
        photo(401, grouped_id=9102),
        photo(402, grouped_id=9102),
        photo(403, grouped_id=9102),
    ]
    service = make_service(monkeypatch, messages)

    result = asyncio.run(service.forward_messages(SOURCE_CHAT, DESTINATION_CHAT, [302, 350, 402]))

    assert result.planned_ids == (301, 302, 350, 401, 402, 403)
    assert result.photo_count == 6
    assert result.album_count == 2
    assert [album.message_ids for album in result.albums] == [(301, 302), (401, 402, 403)]
    assert service.client.forward_calls[0][1] == [301, 302, 350, 401, 402, 403]
    assert result.destination_message_ids == (7001, 7002, 7003, 7004, 7005, 7006)


def test_album_is_never_split_across_native_forward_batches(monkeypatch) -> None:
    singles = [photo(message_id) for message_id in range(1, 99)]
    album = [photo(100, grouped_id=9901), photo(101, grouped_id=9901), photo(102, grouped_id=9901)]
    service = make_service(monkeypatch, [*singles, *album])

    requested = [message.id for message in singles] + [101]
    result = asyncio.run(service.forward_messages(SOURCE_CHAT, DESTINATION_CHAT, requested))

    assert len(result.planned_ids) == 101
    assert [len(call[1]) for call in service.client.forward_calls] == [98, 3]
    assert service.client.forward_calls[1][1] == [100, 101, 102]


def test_partial_missing_is_machine_readable_while_valid_photo_remains_forwardable(monkeypatch) -> None:
    service = make_service(monkeypatch, [photo(501)])

    result = asyncio.run(service.forward_messages(SOURCE_CHAT, DESTINATION_CHAT, [501, 599], dry_run=True))

    assert result.planned_ids == (501,)
    assert result.failed_ids == (599,)
    assert [(item.message_id, item.reason) for item in result.excluded] == [(599, MESSAGE_NOT_FOUND)]


def test_service_and_unsupported_media_have_per_message_reasons(monkeypatch) -> None:
    service_message = FakeMessage(601, text="", action=SimpleNamespace())
    unsupported = FakeMessage(602, text="document", media=MessageMediaDocument())
    service = make_service(monkeypatch, [service_message, unsupported])

    result = asyncio.run(service.forward_messages(SOURCE_CHAT, DESTINATION_CHAT, [601, 602], dry_run=True))

    assert result.planned_ids == ()
    assert [(item.message_id, item.reason) for item in result.excluded] == [
        (601, "SERVICE_MESSAGE"),
        (602, "UNSUPPORTED_MESSAGE"),
    ]


def test_protected_source_returns_content_protected_without_download_or_write(monkeypatch) -> None:
    service = make_service(monkeypatch, [photo(701), photo(702, grouped_id=7701), photo(703, grouped_id=7701)], source_protected=True)

    result = asyncio.run(service.forward_messages(SOURCE_CHAT, DESTINATION_CHAT, [701, 702], dry_run=False))

    assert result.successful_ids == ()
    assert result.failed_ids == (701, 702)
    assert {item.reason for item in result.excluded} == {CONTENT_PROTECTED}
    assert service.client.forward_calls == []
    assert service.client.download_media_calls == 0


def test_flood_wait_stops_without_automatic_retry(monkeypatch) -> None:
    class FakeFloodWait(Exception):
        def __init__(self, seconds: int) -> None:
            super().__init__(seconds)
            self.seconds = seconds

    monkeypatch.setattr(service_module, "FloodWaitError", FakeFloodWait)
    service = make_service(monkeypatch, [photo(801)], forward_error=FakeFloodWait(23))

    with pytest.raises(TelegramBridgeError) as exc_info:
        asyncio.run(service.forward_messages(SOURCE_CHAT, DESTINATION_CHAT, [801]))

    assert exc_info.value.code == FLOOD_WAIT
    assert exc_info.value.details["retry_after_seconds"] == 23
    assert len(service.client.forward_calls) == 1


def test_transport_uncertainty_returns_unknown_outcome_without_retry(monkeypatch) -> None:
    service = make_service(monkeypatch, [photo(901)], forward_error=ConnectionError("synthetic disconnect"))

    with pytest.raises(TelegramBridgeError) as exc_info:
        asyncio.run(service.forward_messages(SOURCE_CHAT, DESTINATION_CHAT, [901]))

    assert exc_info.value.code == UNKNOWN_OUTCOME
    assert exc_info.value.details["uncertain_source_ids"] == [901]
    assert len(service.client.forward_calls) == 1


def test_incomplete_returned_destination_ids_are_unknown_outcome(monkeypatch) -> None:
    service = make_service(monkeypatch, [photo(1001), photo(1002)], mismatch_result=True)

    with pytest.raises(TelegramBridgeError) as exc_info:
        asyncio.run(service.forward_messages(SOURCE_CHAT, DESTINATION_CHAT, [1001, 1002]))

    assert exc_info.value.code == UNKNOWN_OUTCOME
    assert len(service.client.forward_calls) == 1
