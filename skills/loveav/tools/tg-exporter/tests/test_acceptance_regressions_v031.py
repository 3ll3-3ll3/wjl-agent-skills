from __future__ import annotations

import asyncio
import json
from datetime import datetime

from telegram_exporter.daemon_server import DaemonServer
from telegram_exporter.exporter import export_group
from telegram_exporter.ipc_protocol import decode_frame, encode_frame, make_request
from telegram_exporter.models import ExportMode, GroupExportPlan, GroupInfo
from telegram_exporter.proxy import parse_windows_proxy_server


def test_two_gui_leases_and_tgctl_status_coexist_without_daemon_shutdown() -> None:
    async def scenario() -> None:
        server = DaemonServer()

        async def call(kind: str, method: str, params=None):
            request = make_request(
                client_kind=kind,
                app_version="0.3.1",
                method=method,
                params=params or {},
            )
            return decode_frame(await server.handle_bytes(encode_frame(request)))

        gui_one = await call("gui", "client.attach")
        gui_two = await call("gui", "client.attach")
        assert gui_one["ok"] is True
        assert gui_two["ok"] is True
        token_one = gui_one["result"]["lease_token"]
        token_two = gui_two["result"]["lease_token"]
        assert token_one != token_two

        status = await call("tgctl", "system.status")
        assert status["ok"] is True
        assert status["result"]["gui_clients"] == 2
        assert server.shutdown_event.is_set() is False

        detached_one = await call("gui", "client.detach", {"lease_token": token_one})
        assert detached_one["ok"] is True
        status = await call("tgctl", "system.status")
        assert status["result"]["gui_clients"] == 1
        assert server.shutdown_event.is_set() is False

        detached_two = await call("gui", "client.detach", {"lease_token": token_two})
        assert detached_two["ok"] is True
        status = await call("tgctl", "system.status")
        assert status["result"]["gui_clients"] == 0
        assert server.shutdown_event.is_set() is False

    asyncio.run(scenario())


class EmptyUnreadClient:
    def __init__(self):
        self.iter_calls = 0
        self.read_ack_calls = 0

    async def get_entity(self, chat_id):
        return chat_id

    def iter_messages(self, _entity, **_kwargs):
        self.iter_calls += 1

        async def empty():
            if False:
                yield None

        return empty()

    async def send_read_acknowledge(self, *_args, **_kwargs):
        self.read_ack_calls += 1
        raise AssertionError("zero-unread export must not mark read")


def test_zero_current_unread_export_is_valid_json_and_does_not_mark_read(tmp_path) -> None:
    client = EmptyUnreadClient()
    plan = GroupExportPlan(
        group=GroupInfo(
            chat_id=-1007311,
            title="Synthetic Empty Group",
            unread_count=0,
            read_inbox_max_id=73,
            latest_message_id=73,
        ),
        mode=ExportMode.UNREAD,
        category="Synthetic",
    )
    result = asyncio.run(
        export_group(
            client,
            plan,
            tmp_path,
            export_moment=datetime.now().astimezone(),
        )
    )
    payload = json.loads(result.result_path.read_text(encoding="utf-8"))
    assert result.message_count == 0
    assert payload["messages"] == []
    # Zero unread is intentionally a no-history-scan fast path and export_group
    # itself never advances Telegram's read marker.
    assert client.iter_calls == 0
    assert client.read_ack_calls == 0


def test_proxy_parser_rejects_auth_or_query_bearing_input() -> None:
    # Windows ProxyServer support intentionally accepts endpoint metadata only.
    # Inputs carrying credentials/query data are rejected instead of being
    # normalized into a usable proxy configuration. This keeps authentication
    # material out of both Telethon proxy settings and normal logging.
    username = "synthetic-user"
    password = "synthetic-password"
    query_secret = "synthetic-query-secret"
    config = parse_windows_proxy_server(
        f"http://{username}:{password}@127.0.0.1:7890?token={query_secret}"
    )
    assert config is None


def test_proxy_safe_label_contains_endpoint_only() -> None:
    config = parse_windows_proxy_server("http://127.0.0.1:7890")
    assert config is not None
    assert config.safe_label == "http://127.0.0.1:7890"
    assert "@" not in config.safe_label
    assert "?" not in config.safe_label
