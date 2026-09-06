from __future__ import annotations

import asyncio

from . import __version__
from .bridge_errors import (
    IPC_PROTOCOL_ERROR,
    WRITE_OUTCOME_UNKNOWN,
    TelegramBridgeError,
)
from .daemon_manager import ensure_running
from .ipc_identity import IPCIdentity, load_or_create_identity
from .ipc_protocol import PROTOCOL, decode_frame, encode_frame, make_request
from .ipc_transport import IPCConnectError, IPCTransportError, call_once


class DaemonIPCClient:
    def __init__(self, client_kind: str, *, app_version: str = __version__):
        self.client_kind = client_kind
        self.app_version = app_version
        self.identity: IPCIdentity = load_or_create_identity()

    def _call_sync(
        self,
        method: str,
        params: dict | None,
        *,
        side_effect_after_send: bool,
        retry_read_once: bool,
    ):
        self.identity = ensure_running(identity=self.identity)
        request = make_request(
            client_kind=self.client_kind,
            app_version=self.app_version,
            method=method,
            params=params or {},
        )
        encoded = encode_frame(request)
        attempts = 0
        while True:
            attempts += 1
            try:
                raw = call_once(self.identity, encoded)
                break
            except IPCConnectError:
                # Request was definitely not sent. Restarting is safe even for
                # writes because no daemon received the operation.
                self.identity = ensure_running(identity=self.identity)
                if attempts >= 2:
                    raise
            except IPCTransportError as exc:
                if exc.stage == "after_send" and side_effect_after_send:
                    raise TelegramBridgeError(
                        WRITE_OUTCOME_UNKNOWN,
                        "请求已交给 TG daemon，但连接在返回结果前中断。请先检查 Telegram 目标聊天，勿自动重试。",
                        {"method": method},
                    ) from exc
                if not retry_read_once or attempts >= 2:
                    raise
                self.identity = ensure_running(identity=self.identity)

        response = decode_frame(raw)
        if response.get("protocol") != PROTOCOL:
            raise TelegramBridgeError(IPC_PROTOCOL_ERROR, "TG daemon 返回了不兼容的 IPC protocol。")
        if response.get("request_id") != request["request_id"]:
            raise TelegramBridgeError(IPC_PROTOCOL_ERROR, "TG daemon response request_id 不匹配。")
        if not response.get("ok"):
            error = response.get("error") or {}
            raise TelegramBridgeError(
                str(error.get("code") or "TELEGRAM_ERROR"),
                str(error.get("message") or "TG daemon 操作失败。"),
                error.get("details"),
            )
        return response.get("result")

    async def request(
        self,
        method: str,
        params: dict | None = None,
        *,
        side_effect_after_send: bool = False,
        retry_read_once: bool = True,
    ):
        return await asyncio.to_thread(
            self._call_sync,
            method,
            params,
            side_effect_after_send=side_effect_after_send,
            retry_read_once=retry_read_once,
        )
