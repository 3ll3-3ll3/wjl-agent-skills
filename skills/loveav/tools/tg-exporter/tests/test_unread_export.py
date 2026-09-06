from __future__ import annotations

import asyncio
from datetime import datetime

from telegram_exporter.exporter import export_group
from telegram_exporter.models import ExportMode, GroupExportPlan, GroupInfo


class FakeClient:
    def __init__(self):
        self.kwargs = None

    async def get_entity(self, chat_id):
        return chat_id

    def iter_messages(self, entity, **kwargs):
        self.kwargs = kwargs

        async def empty():
            if False:
                yield None

        return empty()


def test_unread_export_uses_frozen_export_start_bounds_and_category_layout(tmp_path):
    client = FakeClient()
    group = GroupInfo(
        chat_id=-100123,
        title="Example",
        unread_count=15,
        read_inbox_max_id=40,
        latest_message_id=55,
    )
    plan = GroupExportPlan(group=group, mode=ExportMode.UNREAD, category="第一类")
    local_tz = datetime.now().astimezone().tzinfo
    moment = datetime(2026, 8, 29, 11, 1, 18, tzinfo=local_tz)

    result = asyncio.run(export_group(client, plan, tmp_path, export_moment=moment))

    assert result.message_count == 0
    # Upper=55 was frozen before this export call. Telethon max_id is
    # exclusive, so anything arriving later (>55) is outside this run.
    assert client.kwargs == {"reverse": True, "min_id": 40, "max_id": 56}
    assert result.result_path.parent == tmp_path / "第一类" / "Example"
    assert result.result_path.name == "2026-08-29_11-01-18.json"
