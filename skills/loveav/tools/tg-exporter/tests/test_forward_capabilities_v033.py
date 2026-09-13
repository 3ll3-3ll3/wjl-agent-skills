from __future__ import annotations

import asyncio

from telegram_exporter.daemon_server_v3 import DaemonServer


def test_system_hello_advertises_native_photo_album_forwarding() -> None:
    server = DaemonServer()
    result = asyncio.run(
        server.dispatch(
            {
                "method": "system.hello",
                "params": {},
                "client": {"kind": "tgctl"},
            }
        )
    )
    capabilities = set(result["capabilities"])
    assert "forward.photos" in capabilities
    assert "forward.albums.atomic" in capabilities
    assert "forward.target_message_ids" in capabilities
    assert "forward.capture" not in capabilities
