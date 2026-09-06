from datetime import datetime, timezone

import pytest

from telegram_exporter.models import ExportMode, GroupExportPlan, GroupInfo


def test_date_range_requires_valid_bounds():
    group = GroupInfo(chat_id=1, title="Test")
    with pytest.raises(ValueError):
        GroupExportPlan(group=group, mode=ExportMode.DATE_RANGE).validate()

    start = datetime(2026, 8, 28, tzinfo=timezone.utc)
    end = datetime(2026, 8, 27, tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        GroupExportPlan(group=group, mode=ExportMode.DATE_RANGE, start_at=start, end_at=end).validate()


def test_since_last_requires_checkpoint():
    group = GroupInfo(chat_id=1, title="Test")
    with pytest.raises(ValueError):
        GroupExportPlan(group=group, mode=ExportMode.SINCE_LAST_EXPORT).validate()

    GroupExportPlan(
        group=group,
        mode=ExportMode.SINCE_LAST_EXPORT,
        last_export_message_id=123,
    ).validate()
