from __future__ import annotations

from typing import Any

from .daemon_server import DaemonServer as V2DaemonServer
from .reader_rpc import READER_METHODS, dispatch_reader


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

        return await super().dispatch(request)
