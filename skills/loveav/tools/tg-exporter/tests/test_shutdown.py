from __future__ import annotations

import asyncio

from telegram_exporter.telegram_service import TelegramService


class FakeClient:
    def __init__(self, disconnect_result):
        self._disconnect_result = disconnect_result
        self.disconnect_calls = 0

    def is_connected(self) -> bool:
        return True

    def disconnect(self):
        self.disconnect_calls += 1
        return self._disconnect_result


def _service_with_client(client: FakeClient) -> TelegramService:
    service = object.__new__(TelegramService)
    service.client = client
    return service


def test_close_accepts_synchronous_disconnect_returning_none() -> None:
    client = FakeClient(None)
    service = _service_with_client(client)

    asyncio.run(service.close())

    assert client.disconnect_calls == 1


def test_close_awaits_async_disconnect_result() -> None:
    completed = False

    async def disconnect_coro() -> None:
        nonlocal completed
        completed = True

    client = FakeClient(disconnect_coro())
    service = _service_with_client(client)

    asyncio.run(service.close())

    assert client.disconnect_calls == 1
    assert completed is True
