from __future__ import annotations

import asyncio

from telegram_exporter.bridge_errors import AUTH_GUI_ONLY, EXPORT_IN_PROGRESS, INVALID_ARGUMENT
from telegram_exporter.daemon_server import DaemonServer
from telegram_exporter.ipc_protocol import decode_frame, encode_frame, make_request


def test_system_hello_is_local_and_reports_protocol() -> None:
    async def scenario() -> None:
        server = DaemonServer()
        request = make_request(client_kind="tgctl", app_version="0.2.0", method="system.hello")
        response = decode_frame(await server.handle_bytes(encode_frame(request)))
        assert response["ok"] is True
        assert response["result"]["protocol"] == "tgipc/1"
        assert "export.jobs" in response["result"]["capabilities"]

    asyncio.run(scenario())


def test_auth_rpc_is_gui_only() -> None:
    async def scenario() -> None:
        server = DaemonServer()
        request = make_request(client_kind="tgctl", app_version="0.2.0", method="auth.status")
        response = decode_frame(await server.handle_bytes(encode_frame(request)))
        assert response["ok"] is False
        assert response["error"]["code"] == AUTH_GUI_ONLY

    asyncio.run(scenario())


def test_true_send_is_rejected_before_telegram_when_export_active() -> None:
    async def scenario() -> None:
        server = DaemonServer()
        await server.operations.reserve_export()
        request = make_request(
            client_kind="tgctl",
            app_version="0.2.0",
            method="send",
            params={"destination_chat": "me", "text": "should-not-send", "dry_run": False},
        )
        response = decode_frame(await server.handle_bytes(encode_frame(request)))
        assert response["ok"] is False
        assert response["error"]["code"] == EXPORT_IN_PROGRESS
        await server.operations.cancel_export_reservation()

    asyncio.run(scenario())


def test_server_revalidates_200_message_hard_cap_before_telegram() -> None:
    async def scenario() -> None:
        server = DaemonServer()
        request = make_request(
            client_kind="tgctl",
            app_version="0.2.0",
            method="forward",
            params={
                "source_chat": "-1001",
                "destination_chat": "me",
                "ids": list(range(201)),
                "allow_large_batch": True,
                "dry_run": False,
            },
        )
        response = decode_frame(await server.handle_bytes(encode_frame(request)))
        assert response["ok"] is False
        assert response["error"]["code"] == INVALID_ARGUMENT
        assert response["error"]["details"]["limit"] == 200

    asyncio.run(scenario())


def test_invalid_frame_does_not_decrement_other_active_request_count() -> None:
    async def scenario() -> None:
        server = DaemonServer()
        server.active_requests = 1
        response = decode_frame(await server.handle_bytes(b"not-json"))
        assert response["ok"] is False
        assert server.active_requests == 1

    asyncio.run(scenario())


def test_gui_lease_keeps_daemon_non_idle() -> None:
    async def scenario() -> None:
        server = DaemonServer()
        request = make_request(client_kind="gui", app_version="0.2.0", method="client.attach")
        response = decode_frame(await server.handle_bytes(encode_frame(request)))
        assert response["ok"] is True
        assert server.has_live_gui is True
        server.last_activity -= 9999
        assert server.can_idle_shutdown(1) is False

    asyncio.run(scenario())
