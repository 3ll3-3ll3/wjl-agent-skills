from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from .bridge_errors import EXPORT_IN_PROGRESS, TelegramBridgeError

T = TypeVar("T")


class OperationCoordinator:
    """Implements the user-selected 3B/4B scheduling policy.

    Telegram work is deliberately serialized for v0.2.0. Export reservations
    make reads wait and true writes fail immediately. Pure local daemon RPCs do
    not pass through this coordinator.
    """

    def __init__(self) -> None:
        self._operation_lock = asyncio.Lock()
        self._state_lock = asyncio.Lock()
        self._export_done = asyncio.Event()
        self._export_done.set()
        self._export_reserved = False
        self._queued_reads = 0

    @property
    def export_active(self) -> bool:
        return self._export_reserved

    @property
    def queued_reads(self) -> int:
        return self._queued_reads

    async def reserve_export(self) -> None:
        async with self._state_lock:
            if self._export_reserved:
                raise TelegramBridgeError(EXPORT_IN_PROGRESS, "已有导出任务正在运行。")
            self._export_reserved = True
            self._export_done.clear()

    async def run_reserved_export(self, operation: Callable[[], Awaitable[T]]) -> T:
        if not self._export_reserved:
            raise RuntimeError("export must be reserved before execution")
        try:
            async with self._operation_lock:
                return await operation()
        finally:
            async with self._state_lock:
                self._export_reserved = False
                self._export_done.set()

    async def cancel_export_reservation(self) -> None:
        async with self._state_lock:
            self._export_reserved = False
            self._export_done.set()

    async def run_read(self, operation: Callable[[], Awaitable[T]]) -> T:
        while True:
            if self._export_reserved:
                self._queued_reads += 1
                try:
                    await self._export_done.wait()
                finally:
                    self._queued_reads = max(0, self._queued_reads - 1)
            async with self._operation_lock:
                # An export may have been reserved while this read waited for
                # the operation lock. Loop and wait for it instead of racing.
                if self._export_reserved:
                    continue
                return await operation()

    async def run_write(self, operation: Callable[[], Awaitable[T]], *, dry_run: bool) -> T:
        if dry_run:
            return await self.run_read(operation)
        if self._export_reserved:
            raise TelegramBridgeError(
                EXPORT_IN_PROGRESS,
                "当前正在导出。请等待导出完成后再发送或转发。",
            )
        async with self._operation_lock:
            if self._export_reserved:
                raise TelegramBridgeError(
                    EXPORT_IN_PROGRESS,
                    "当前正在导出。请等待导出完成后再发送或转发。",
                )
            return await operation()
