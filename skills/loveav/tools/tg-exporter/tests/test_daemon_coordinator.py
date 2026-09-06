from __future__ import annotations

import asyncio

import pytest

from telegram_exporter.bridge_errors import EXPORT_IN_PROGRESS, TelegramBridgeError
from telegram_exporter.operation_coordinator import OperationCoordinator


def test_true_write_is_rejected_while_export_reserved() -> None:
    async def scenario() -> None:
        coordinator = OperationCoordinator()
        await coordinator.reserve_export()
        with pytest.raises(TelegramBridgeError) as exc_info:
            await coordinator.run_write(lambda: asyncio.sleep(0), dry_run=False)
        assert exc_info.value.code == EXPORT_IN_PROGRESS
        await coordinator.cancel_export_reservation()

    asyncio.run(scenario())


def test_read_waits_until_export_finishes() -> None:
    async def scenario() -> None:
        coordinator = OperationCoordinator()
        await coordinator.reserve_export()
        export_started = asyncio.Event()
        export_release = asyncio.Event()
        read_finished = asyncio.Event()

        async def export_op() -> None:
            export_started.set()
            await export_release.wait()

        async def read_op() -> str:
            read_finished.set()
            return "ok"

        export_task = asyncio.create_task(coordinator.run_reserved_export(export_op))
        await export_started.wait()
        read_task = asyncio.create_task(coordinator.run_read(read_op))
        await asyncio.sleep(0.02)
        assert not read_finished.is_set()
        assert not read_task.done()

        export_release.set()
        await export_task
        assert await read_task == "ok"
        assert read_finished.is_set()

    asyncio.run(scenario())


def test_dry_run_uses_read_wait_policy() -> None:
    async def scenario() -> None:
        coordinator = OperationCoordinator()
        await coordinator.reserve_export()
        release = asyncio.Event()

        async def export_op() -> None:
            await release.wait()

        export_task = asyncio.create_task(coordinator.run_reserved_export(export_op))
        dry_task = asyncio.create_task(coordinator.run_write(lambda: asyncio.sleep(0, result="dry"), dry_run=True))
        await asyncio.sleep(0.02)
        assert not dry_task.done()
        release.set()
        await export_task
        assert await dry_task == "dry"

    asyncio.run(scenario())
