from __future__ import annotations

import asyncio
from types import SimpleNamespace

from telegram_exporter import reader_runtime as runtime_module
from telegram_exporter.cursor_codec import CursorCodec
from telegram_exporter.reader_models import DialogInfo
from telegram_exporter.reader_runtime import PersonalAccountReaderV3
from telegram_exporter.reader_service import PersonalAccountReader

CURRENT_ID = -(10**12 + 77)
LEGACY_ID = -77


class FakeMessage:
    def __init__(self, message_id: int):
        self.id = message_id


class FakeClient:
    def __init__(self):
        self.requested = []
        self.get_messages_calls = []

    async def get_entity(self, value):
        self.requested.append(value)
        return CURRENT_ID

    async def get_messages(self, entity, ids):
        self.get_messages_calls.append((entity, list(ids)))
        return [FakeMessage(int(value)) for value in ids]


def test_migrated_source_uses_current_logical_entity_for_role_snapshot(monkeypatch) -> None:
    client = FakeClient()
    reader = PersonalAccountReaderV3(SimpleNamespace(client=client), cursor_codec=CursorCodec(b"r" * 32))
    row = DialogInfo(
        chat_id=CURRENT_ID,
        title="Current supergroup",
        username=None,
        dialog_type="supergroup",
        migrated_from_chat_id=LEGACY_ID,
    )
    seen = {}

    async def fake_base_snapshot(_self, received_row, entity):
        seen["row"] = received_row
        seen["entity"] = entity
        return {}, True

    monkeypatch.setattr(PersonalAccountReader, "_admin_snapshot", fake_base_snapshot)
    snapshot, available = asyncio.run(reader._admin_snapshot(row, LEGACY_ID))

    assert snapshot == {}
    assert available is True
    assert client.requested == [CURRENT_ID]
    assert seen["row"] is row
    assert seen["entity"] == CURRENT_ID


def test_rich_get_from_legacy_source_keeps_current_logical_chat_id(monkeypatch) -> None:
    monkeypatch.setattr(runtime_module, "Message", FakeMessage)
    client = FakeClient()
    reader = PersonalAccountReaderV3(SimpleNamespace(client=client), cursor_codec=CursorCodec(b"g" * 32))
    legacy = DialogInfo(
        chat_id=LEGACY_ID,
        title="Legacy group",
        username=None,
        dialog_type="group",
        migrated_to_chat_id=CURRENT_ID,
    )
    current = DialogInfo(
        chat_id=CURRENT_ID,
        title="Current supergroup",
        username=None,
        dialog_type="supergroup",
        migrated_from_chat_id=LEGACY_ID,
    )

    async def fake_resolve(reference):
        return (legacy, LEGACY_ID) if int(reference) == LEGACY_ID else (current, CURRENT_ID)

    async def fake_snapshot(_row, _entity):
        return {}, True

    async def fake_message_info(logical_row, source_chat_id, message, _roles, _available):
        return {
            "chat_id": logical_row.chat_id,
            "source_chat_id": source_chat_id,
            "message_id": message.id,
        }

    monkeypatch.setattr(reader, "resolve_dialog", fake_resolve)
    monkeypatch.setattr(reader, "_admin_snapshot", fake_snapshot)
    monkeypatch.setattr(reader, "_message_info_v3", fake_message_info)

    rows = asyncio.run(reader.messages_get_v3(LEGACY_ID, [5]))

    assert client.get_messages_calls == [(LEGACY_ID, [5])]
    assert rows == [{"chat_id": CURRENT_ID, "source_chat_id": LEGACY_ID, "message_id": 5}]
