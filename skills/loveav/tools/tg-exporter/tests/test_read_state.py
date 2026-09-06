from __future__ import annotations

import asyncio

from telegram_exporter.models import GroupInfo
from telegram_exporter.read_state import mark_unread_snapshot_read


class FakeClient:
    def __init__(self):
        self.entity_requests: list[int] = []
        self.acks: list[tuple[object, int]] = []

    async def get_entity(self, chat_id: int):
        self.entity_requests.append(chat_id)
        return {"chat_id": chat_id}

    async def send_read_acknowledge(self, entity, *, max_id: int):
        self.acks.append((entity, max_id))
        return True


def test_marks_exact_refreshed_unread_snapshot() -> None:
    client = FakeClient()
    group = GroupInfo(
        chat_id=-100123,
        title="Example",
        unread_count=12,
        read_inbox_max_id=100,
        latest_message_id=112,
    )

    acknowledged = asyncio.run(mark_unread_snapshot_read(client, group))

    assert acknowledged == 112
    assert client.entity_requests == [-100123]
    assert client.acks == [({"chat_id": -100123}, 112)]


def test_does_nothing_when_snapshot_has_no_unread_messages() -> None:
    client = FakeClient()
    group = GroupInfo(
        chat_id=-100123,
        title="Example",
        unread_count=0,
        read_inbox_max_id=112,
        latest_message_id=112,
    )

    acknowledged = asyncio.run(mark_unread_snapshot_read(client, group))

    assert acknowledged is None
    assert client.entity_requests == []
    assert client.acks == []


def test_does_not_move_read_marker_backwards() -> None:
    client = FakeClient()
    group = GroupInfo(
        chat_id=-100123,
        title="Example",
        unread_count=2,
        read_inbox_max_id=120,
        latest_message_id=118,
    )

    acknowledged = asyncio.run(mark_unread_snapshot_read(client, group))

    assert acknowledged is None
    assert client.entity_requests == []
    assert client.acks == []
