import asyncio
from datetime import datetime, timezone

from telegram_exporter.exporter import export_group
from telegram_exporter.models import ExportMode, GroupExportPlan, GroupInfo


class FakeClient:
    def __init__(self):
        self.iter_calls = []

    async def get_entity(self, chat_id):
        return chat_id

    def iter_messages(self, entity, **kwargs):
        self.iter_calls.append((entity, kwargs))

        async def empty():
            if False:
                yield None

        return empty()


def test_date_range_reads_legacy_basic_group_before_current_supergroup(tmp_path):
    client = FakeClient()
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 8, 29, tzinfo=timezone.utc)
    group = GroupInfo(
        chat_id=-100999,
        title="数学群",
        migrated_from_chat_id=-123,
    )
    plan = GroupExportPlan(
        group=group,
        mode=ExportMode.DATE_RANGE,
        category="第一类",
        start_at=start,
        end_at=end,
    )

    asyncio.run(export_group(client, plan, tmp_path, export_moment=end))

    assert [entity for entity, _kwargs in client.iter_calls] == [-123, -100999]
    assert all(kwargs == {"reverse": True, "offset_date": start} for _entity, kwargs in client.iter_calls)
