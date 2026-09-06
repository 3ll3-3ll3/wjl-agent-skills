from __future__ import annotations

import asyncio

import pytest

from telegram_exporter.bridge_errors import WRITE_OUTCOME_UNKNOWN, TelegramBridgeError
from telegram_exporter import ipc_client as client_module
from telegram_exporter.ipc_client import DaemonIPCClient
from telegram_exporter.ipc_transport import IPCTransportError


class FakeIdentity:
    authkey = b"x" * 32


def _client(monkeypatch) -> DaemonIPCClient:
    monkeypatch.setattr(client_module, "load_or_create_identity", lambda: FakeIdentity())
    monkeypatch.setattr(client_module, "ensure_running", lambda **_kwargs: FakeIdentity())
    return DaemonIPCClient("tgctl")


def test_true_write_after_send_disconnect_never_retries(monkeypatch) -> None:
    client = _client(monkeypatch)
    calls = 0

    def broken_call(_identity, _payload):
        nonlocal calls
        calls += 1
        raise IPCTransportError("lost response", stage="after_send")

    monkeypatch.setattr(client_module, "call_once", broken_call)

    with pytest.raises(TelegramBridgeError) as exc_info:
        asyncio.run(
            client.request(
                "send",
                {"destination_chat": "me", "text": "x", "dry_run": False},
                side_effect_after_send=True,
                retry_read_once=False,
            )
        )
    assert exc_info.value.code == WRITE_OUTCOME_UNKNOWN
    assert calls == 1


def test_read_after_send_transport_failure_retries_once(monkeypatch) -> None:
    client = _client(monkeypatch)
    calls = 0

    def flaky_call(_identity, payload):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise IPCTransportError("lost response", stage="after_send")
        request = client_module.decode_frame(payload)
        return client_module.encode_frame(
            {
                "protocol": "tgipc/1",
                "request_id": request["request_id"],
                "ok": True,
                "result": {"value": 1},
            }
        )

    monkeypatch.setattr(client_module, "call_once", flaky_call)
    result = asyncio.run(client.request("system.status", retry_read_once=True))
    assert result == {"value": 1}
    assert calls == 2
