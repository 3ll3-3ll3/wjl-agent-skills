from __future__ import annotations

from typing import Any

from telethon.errors import FloodWaitError

from .bridge_errors import WRITE_FAILED, TelegramBridgeError
from .daemon_server import DaemonServer as V2DaemonServer
from .live_capture import send_and_capture
from .reader_rpc import READER_METHODS, _reader, dispatch_reader
from .reader_unread import mark_snapshot_read


class DaemonServer(V2DaemonServer):
    """v0.3 daemon surface layered over the preserved v0.2 coordinator.

    The v0.2 server remains the implementation of auth, export, legacy tgctl
    calls and write safety. This subclass adds read-only Personal Account Reader
    RPCs without copying or weakening those paths.
    """

    async def dispatch(self, request: dict[str, Any]) -> Any:
        method = str(request["method"])
        params = dict(request.get("params") or {})

        if method == "system.hello":
            result = await super().dispatch(request)
            capabilities = list(result.get("capabilities") or [])
            for capability in (
                "account.get",
                "dialogs.list",
                "chats.get",
                "chats.members",
                "messages.history",
                "messages.replies",
                "messages.current_unread_snapshot",
                "messages.mark_read_frozen_snapshot",
                "send.capture",
                "messages.advanced_search",
                "messages.rich_get",
                "topics.list",
                "topics.history",
                "media.download.confirmed",
            ):
                if capability not in capabilities:
                    capabilities.append(capability)
            result["capabilities"] = capabilities
            result["reader_schema"] = "tgctl.reader.v1"
            return result

        is_v3_message = method in {"messages.get", "messages.search"} and params.get("schema") == "v3"
        if method in READER_METHODS or is_v3_message:
            return await dispatch_reader(self, method, params)

        if method == "send.capture":
            dry_run = bool(params.get("dry_run", False))

            async def capture():
                reader = await _reader(self)
                try:
                    return await send_and_capture(
                        reader,
                        params.get("destination_chat", ""),
                        str(params.get("text") or ""),
                        first_reply_timeout_seconds=float(params.get("first_reply_timeout_seconds", 8.0)),
                        settle_seconds=float(params.get("settle_seconds", 2.0)),
                        max_messages=int(params.get("max_messages", 20)),
                        url_domain=params.get("url_domain"),
                        dry_run=dry_run,
                    )
                except (TelegramBridgeError, FloodWaitError):
                    raise
                except Exception as exc:
                    raise TelegramBridgeError(WRITE_FAILED, f"Telegram 发送并捕获失败：{type(exc).__name__}") from exc

            return await self.operations.run_write(capture, dry_run=dry_run)

        if method == "messages.mark_read":
            async def acknowledge():
                reader = await _reader(self)
                try:
                    return await mark_snapshot_read(
                        reader,
                        params.get("chat", ""),
                        snapshot_token=str(params.get("snapshot_token") or ""),
                        max_id=int(params.get("max_id", 0)),
                        confirmation=str(params.get("confirmation") or ""),
                    )
                except (TelegramBridgeError, FloodWaitError):
                    raise
                except Exception as exc:
                    raise TelegramBridgeError(WRITE_FAILED, f"Telegram 已读确认失败：{type(exc).__name__}") from exc

            return await self.operations.run_write(acknowledge, dry_run=False)

        return await super().dispatch(request)
