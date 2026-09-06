from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime
from types import SimpleNamespace

from telegram_exporter.export_coordinator import ExportCoordinator
from telegram_exporter.exporter import ExportResult
from telegram_exporter.models import ExportMode, GroupExportPlan, GroupInfo
from telegram_exporter.operation_coordinator import OperationCoordinator
from telegram_exporter.unread_snapshot import capture_current_unread_snapshot


class FakeDialogClient:
    def __init__(self, dialogs):
        self.dialogs = dialogs

    def iter_dialogs(self):
        async def iterate():
            for dialog in self.dialogs:
                yield dialog

        return iterate()


def _dialog(chat_id: int, *, unread: int, lower: int, upper: int):
    return SimpleNamespace(
        is_group=True,
        is_channel=False,
        entity=SimpleNamespace(peer_id=chat_id),
        unread_count=unread,
        dialog=SimpleNamespace(read_inbox_max_id=lower, unread_mark=False),
        message=SimpleNamespace(id=upper),
    )


def _job(job_id: str = "job") -> dict:
    return {
        "job_id": job_id,
        "state": "queued",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "output_root": "",
        "total_groups": 1,
        "completed_groups": 0,
        "current_chat_id": None,
        "current_title": None,
        "current_message_count": 0,
        "total_messages": 0,
        "success_count": 0,
        "failure_count": 0,
        "marked_read_count": 0,
        "read_failure_count": 0,
        "results": [],
        "failures": [],
        "read_failures": [],
    }


def _configure_paths(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "telegram_exporter.export_coordinator.daemon_job_state_path",
        lambda: tmp_path / "daemon_jobs.json",
    )
    monkeypatch.setattr(
        "telegram_exporter.export_coordinator.state_path",
        lambda: tmp_path / "local_state.json",
    )


def test_capture_snapshot_refreshes_current_logical_group_without_mutating_catalogue(monkeypatch):
    stale = GroupInfo(
        chat_id=-100123,
        title="Example",
        unread_count=1,
        read_inbox_max_id=10,
        latest_message_id=11,
        migrated_from_chat_id=-456,
    )
    # The legacy Basic Group appears first and deliberately has very different
    # read state. Current-unread must ignore it and freeze only the active
    # logical Supergroup identified by group.chat_id.
    client = FakeDialogClient(
        [
            _dialog(-456, unread=99, lower=1, upper=99),
            _dialog(-100123, unread=5, lower=20, upper=25),
        ]
    )
    monkeypatch.setattr("telegram_exporter.unread_snapshot.get_peer_id", lambda entity: entity.peer_id)

    snapshot = asyncio.run(capture_current_unread_snapshot(client, stale))

    assert (stale.unread_count, stale.read_inbox_max_id, stale.latest_message_id) == (1, 10, 11)
    assert (snapshot.unread_count, snapshot.read_inbox_max_id, snapshot.latest_message_id) == (5, 20, 25)
    assert snapshot.chat_id == stale.chat_id
    assert snapshot.migrated_from_chat_id == -456


def test_daemon_snapshots_each_unread_group_when_that_group_begins(monkeypatch, tmp_path):
    _configure_paths(monkeypatch, tmp_path)

    snapshot_calls: list[int] = []
    exported_bounds: list[tuple[int, int, int]] = []
    acknowledged_bounds: list[tuple[int, int, int]] = []

    snapshots = {
        -1001: (3, 100, 103),
        -1002: (5, 200, 205),
    }

    async def fake_capture(_client, group):
        snapshot_calls.append(group.chat_id)
        unread, lower, upper = snapshots[group.chat_id]
        return replace(
            group,
            unread_count=unread,
            read_inbox_max_id=lower,
            latest_message_id=upper,
            is_unread=True,
        )

    async def fake_export(_client, plan, output_root, progress=None, export_moment=None):
        exported_bounds.append(
            (plan.group.chat_id, plan.group.read_inbox_max_id, plan.group.latest_message_id)
        )
        result_path = output_root / f"{abs(plan.group.chat_id)}.json"
        result_path.write_text("{}", encoding="utf-8")
        return ExportResult(
            chat_id=plan.group.chat_id,
            title=plan.group.title,
            message_count=1,
            latest_message_id=plan.group.latest_message_id,
            result_path=result_path,
        )

    async def fake_ack(_client, group):
        acknowledged_bounds.append((group.chat_id, group.read_inbox_max_id, group.latest_message_id))
        return group.latest_message_id

    monkeypatch.setattr("telegram_exporter.export_coordinator.capture_current_unread_snapshot", fake_capture)
    monkeypatch.setattr("telegram_exporter.export_coordinator.export_group", fake_export)
    monkeypatch.setattr("telegram_exporter.export_coordinator.mark_unread_snapshot_read", fake_ack)

    class FakeService:
        client = object()

    async def provider():
        return FakeService()

    async def scenario():
        operations = OperationCoordinator()
        await operations.reserve_export()
        coordinator = ExportCoordinator(operations, provider)
        job = _job()
        job["total_groups"] = 2
        plans = [
            (
                GroupExportPlan(
                    group=GroupInfo(
                        chat_id=-1001,
                        title="One",
                        unread_count=1,
                        read_inbox_max_id=10,
                        latest_message_id=11,
                    ),
                    mode=ExportMode.UNREAD,
                ),
                True,
            ),
            (
                GroupExportPlan(
                    group=GroupInfo(
                        chat_id=-1002,
                        title="Two",
                        unread_count=1,
                        read_inbox_max_id=20,
                        latest_message_id=21,
                    ),
                    mode=ExportMode.UNREAD,
                ),
                True,
            ),
        ]
        await coordinator._run_job(job, plans, tmp_path, datetime.now().astimezone())
        return job

    job = asyncio.run(scenario())

    assert snapshot_calls == [-1001, -1002]
    assert exported_bounds == [(-1001, 100, 103), (-1002, 200, 205)]
    assert acknowledged_bounds == exported_bounds
    assert job["state"] == "completed"
    assert job["success_count"] == 2
    assert job["marked_read_count"] == 2


def test_export_failure_never_acknowledges_snapshot(monkeypatch, tmp_path):
    _configure_paths(monkeypatch, tmp_path)
    ack_calls: list[int] = []

    async def fake_capture(_client, group):
        return replace(group, unread_count=2, read_inbox_max_id=40, latest_message_id=42)

    async def fake_export(*_args, **_kwargs):
        raise RuntimeError("export failed")

    async def fake_ack(_client, group):
        ack_calls.append(group.latest_message_id)
        return group.latest_message_id

    monkeypatch.setattr("telegram_exporter.export_coordinator.capture_current_unread_snapshot", fake_capture)
    monkeypatch.setattr("telegram_exporter.export_coordinator.export_group", fake_export)
    monkeypatch.setattr("telegram_exporter.export_coordinator.mark_unread_snapshot_read", fake_ack)

    class FakeService:
        client = object()

    async def provider():
        return FakeService()

    async def scenario():
        operations = OperationCoordinator()
        await operations.reserve_export()
        coordinator = ExportCoordinator(operations, provider)
        job = _job()
        plan = GroupExportPlan(
            group=GroupInfo(chat_id=-1001, title="One", unread_count=1),
            mode=ExportMode.UNREAD,
        )
        await coordinator._run_job(job, [(plan, True)], tmp_path, datetime.now().astimezone())
        return job

    job = asyncio.run(scenario())

    assert ack_calls == []
    assert job["failure_count"] == 1
    assert job["marked_read_count"] == 0


def test_read_ack_failure_keeps_successful_json(monkeypatch, tmp_path):
    _configure_paths(monkeypatch, tmp_path)
    output_file = tmp_path / "successful.json"

    async def fake_capture(_client, group):
        return replace(group, unread_count=2, read_inbox_max_id=70, latest_message_id=72)

    async def fake_export(_client, plan, _output_root, progress=None, export_moment=None):
        output_file.write_text('{"ok": true}', encoding="utf-8")
        return ExportResult(
            chat_id=plan.group.chat_id,
            title=plan.group.title,
            message_count=2,
            latest_message_id=plan.group.latest_message_id,
            result_path=output_file,
        )

    async def fake_ack(_client, _group):
        raise RuntimeError("ack failed")

    monkeypatch.setattr("telegram_exporter.export_coordinator.capture_current_unread_snapshot", fake_capture)
    monkeypatch.setattr("telegram_exporter.export_coordinator.export_group", fake_export)
    monkeypatch.setattr("telegram_exporter.export_coordinator.mark_unread_snapshot_read", fake_ack)

    class FakeService:
        client = object()

    async def provider():
        return FakeService()

    async def scenario():
        operations = OperationCoordinator()
        await operations.reserve_export()
        coordinator = ExportCoordinator(operations, provider)
        job = _job()
        plan = GroupExportPlan(
            group=GroupInfo(chat_id=-1001, title="One", unread_count=1),
            mode=ExportMode.UNREAD,
        )
        await coordinator._run_job(job, [(plan, True)], tmp_path, datetime.now().astimezone())
        return job

    job = asyncio.run(scenario())

    assert output_file.exists()
    assert job["success_count"] == 1
    assert job["read_failure_count"] == 1
    assert job["results"][0]["read_ack"] == "failed"
