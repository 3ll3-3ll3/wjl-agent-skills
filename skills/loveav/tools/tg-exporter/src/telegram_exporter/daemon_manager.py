from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from . import __version__
from .bridge_errors import DAEMON_UNAVAILABLE, DAEMON_UPGRADE_REQUIRED, TelegramBridgeError
from .ipc_identity import IPCIdentity, load_or_create_identity
from .ipc_protocol import PROTOCOL, decode_frame, encode_frame, make_request
from .ipc_transport import IPCConnectError, IPCTransportError, call_once


def _spawn_command() -> list[str]:
    if getattr(sys, "frozen", False):
        # Both TGExporter.exe and tgctl.exe understand this private switch.
        return [sys.executable, "--tg-daemon-worker"]
    return [sys.executable, "-m", "telegram_exporter.daemon_main"]


def _spawn_daemon() -> None:
    kwargs: dict = {"close_fds": True}
    if os.name == "nt":
        kwargs["creationflags"] = (
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        )
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(_spawn_command(), **kwargs)


def _hello(identity: IPCIdentity) -> dict:
    request = make_request(
        client_kind="daemon-test",
        app_version=__version__,
        method="system.hello",
    )
    raw = call_once(identity, encode_frame(request))
    response = decode_frame(raw)
    if response.get("protocol") != PROTOCOL:
        raise TelegramBridgeError(
            DAEMON_UPGRADE_REQUIRED,
            "正在运行的 TG daemon IPC 版本不兼容。请退出旧后台后重试。",
        )
    if not response.get("ok"):
        error = response.get("error") or {}
        raise TelegramBridgeError(
            str(error.get("code") or DAEMON_UNAVAILABLE),
            str(error.get("message") or "TG daemon hello 失败。"),
            error.get("details"),
        )
    result = response.get("result")
    return result if isinstance(result, dict) else {}


def ensure_running(*, timeout: float = 10.0, identity: IPCIdentity | None = None) -> IPCIdentity:
    identity = identity or load_or_create_identity()
    try:
        _hello(identity)
        return identity
    except IPCConnectError:
        pass
    except IPCTransportError:
        # No Telegram write is involved in hello; restart/retry is safe.
        pass

    _spawn_daemon()
    deadline = time.monotonic() + max(1.0, timeout)
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            _hello(identity)
            return identity
        except (IPCConnectError, IPCTransportError, OSError) as exc:
            last_error = exc
            time.sleep(0.1)
        except TelegramBridgeError:
            raise

    raise TelegramBridgeError(
        DAEMON_UNAVAILABLE,
        "TG Telegram 后台未能在限定时间内启动。请查看本地日志。",
        {"last_error": type(last_error).__name__ if last_error else None},
    )
