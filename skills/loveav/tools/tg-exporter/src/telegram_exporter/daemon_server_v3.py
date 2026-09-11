from __future__ import annotations

from typing import Any

from telethon.errors import FloodWaitError

from .bridge_errors import INVALID_ARGUMENT, WRITE_FAILED, TelegramBridgeError
from .daemon_server import (
    DEFAULT_FORWARD_LIMIT,
    LARGE_FORWARD_LIMIT,
    DaemonServer as V2DaemonServer,
)
from .reader_rpc import READER_METHODS, dispatch_reader


class DaemonServer(V2DaemonServer):
    """v0.3 daemon surface layered over the preserved v0.2 coordinator.

    The v0.2 server remains the implementation of auth, export, legacy tgctl
    calls and write safety. This subclass adds read-only Personal Account Reader
    RPCs and the current forward planner without weakening those paths.
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
                "messages.advanced_search",
                "messages.rich_get",
                "topics.list",
                "topics.history",
                "media.download.confirmed",
                "forward.photos",
                "forward.albums.atomic",
                "forward.target_message_ids",
            ):
                if capability not in capabilities:
                    capabilities.append(capability)
            result["capabilities"] = capabilities
            result["reader_schema"] = "tgctl.reader.v1"
            return result

        # Keep the existing CLI/RPC method name. v0.3.3 additionally passes
        # the effective 20/200-message limit into the album-aware planner so
        # automatic album completion cannot silently bypass the batch policy.
        if method == "forward":
            ids = [int(value) for value in params.get("ids", [])]
            allow_large = bool(params.get("allow_large_batch", False))
            limit = LARGE_FORWARD_LIMIT if allow_large else DEFAULT_FORWARD_LIMIT
            if len(ids) > limit:
                raise TelegramBridgeError(
                    INVALID_ARGUMENT,
                    f"单次 forward 最多 {limit} 条。"
                    + ("" if allow_large else "如确有需要，请显式加入 --allow-large-batch。"),
                    {"requested_count": len(ids), "limit": limit},
                )
            dry_run = bool(params.get("dry_run", False))

            async def forward():
                service = await self._authorized_service()
                try:
                    return await service.forward_messages(
                        params.get("source_chat", ""),
                        params.get("destination_chat", ""),
                        ids,
                        dry_run=dry_run,
                        max_messages=limit,
                    )
                except (TelegramBridgeError, FloodWaitError):
                    raise
                except Exception as exc:
                    raise TelegramBridgeError(WRITE_FAILED, f"Telegram 转发失败：{type(exc).__name__}") from exc

            return await self.operations.run_write(forward, dry_run=dry_run)

        is_v3_message = method in {"messages.get", "messages.search"} and params.get("schema") == "v3"
        if method in READER_METHODS or is_v3_message:
            return await dispatch_reader(self, method, params)

        return await super().dispatch(request)
