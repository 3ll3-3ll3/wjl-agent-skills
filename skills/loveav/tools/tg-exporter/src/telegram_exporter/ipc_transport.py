from __future__ import annotations

import asyncio
import os
import threading
from multiprocessing import AuthenticationError
from multiprocessing.connection import Client, Listener
from pathlib import Path
from typing import Awaitable, Callable

from .ipc_identity import IPCIdentity
from .ipc_protocol import MAX_FRAME_BYTES
from .paths import app_data_dir


class IPCConnectError(ConnectionError):
    """The request was never sent because no authenticated daemon was reachable."""


class IPCTransportError(ConnectionError):
    """The pipe failed after a connection was established.

    ``stage`` matters for Telegram writes: once a request was sent, callers must
    not automatically retry because the daemon may already have committed the
    write before the response connection failed.
    """

    def __init__(self, message: str, *, stage: str):
        super().__init__(message)
        self.stage = stage


def pipe_address(identity: IPCIdentity) -> tuple[str, str]:
    if os.name == "nt":
        return rf"\\.\pipe\TGExporter-{identity.instance_id}-v1", "AF_PIPE"
    # Developer/test fallback. Production Windows uses AF_PIPE.
    return str(app_data_dir() / f"tgipc-{identity.instance_id}-v1.sock"), "AF_UNIX"


def call_once(identity: IPCIdentity, payload: bytes) -> bytes:
    address, family = pipe_address(identity)
    try:
        connection = Client(address, family=family, authkey=identity.authkey)
    except (OSError, EOFError, ConnectionError, AuthenticationError) as exc:
        raise IPCConnectError(f"无法连接 TG daemon：{type(exc).__name__}") from exc

    sent = False
    try:
        connection.send_bytes(payload)
        sent = True
        return connection.recv_bytes(MAX_FRAME_BYTES)
    except (OSError, EOFError, ConnectionError, AuthenticationError) as exc:
        raise IPCTransportError(
            f"TG daemon IPC 连接中断：{type(exc).__name__}",
            stage="after_send" if sent else "before_send",
        ) from exc
    finally:
        try:
            connection.close()
        except OSError:
            pass


class PipeServer:
    """Blocking multiprocessing Listener isolated from the asyncio/Qt thread."""

    def __init__(
        self,
        identity: IPCIdentity,
        loop: asyncio.AbstractEventLoop,
        handler: Callable[[bytes], Awaitable[bytes]],
    ):
        self.identity = identity
        self.loop = loop
        self.handler = handler
        self._listener: Listener | None = None
        self._accept_thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._startup_error: BaseException | None = None
        self._workers: set[threading.Thread] = set()
        self._workers_lock = threading.Lock()

    @property
    def ready(self) -> bool:
        return self._ready.is_set() and self._startup_error is None

    @property
    def startup_error(self) -> BaseException | None:
        return self._startup_error

    def start(self) -> None:
        if self._accept_thread and self._accept_thread.is_alive():
            return
        self._accept_thread = threading.Thread(target=self._accept_loop, name="tg-ipc-accept", daemon=True)
        self._accept_thread.start()

    def wait_ready(self, timeout: float = 5.0) -> None:
        if not self._ready.wait(timeout):
            raise TimeoutError("TG daemon IPC listener startup timed out")
        if self._startup_error is not None:
            raise RuntimeError("TG daemon IPC listener failed") from self._startup_error

    def _accept_loop(self) -> None:
        address, family = pipe_address(self.identity)
        if family == "AF_UNIX":
            try:
                Path(address).unlink(missing_ok=True)
            except OSError:
                pass
        try:
            self._listener = Listener(address, family=family, backlog=16, authkey=self.identity.authkey)
        except BaseException as exc:
            self._startup_error = exc
            self._ready.set()
            return

        self._ready.set()
        try:
            while not self._stop.is_set():
                try:
                    connection = self._listener.accept()
                except AuthenticationError:
                    # A process with a wrong local authkey must not be able to
                    # kill the daemon accept loop. Drop it and keep serving.
                    continue
                except (OSError, EOFError):
                    if self._stop.is_set():
                        break
                    continue
                worker = threading.Thread(
                    target=self._serve_connection,
                    args=(connection,),
                    name="tg-ipc-client",
                    daemon=True,
                )
                with self._workers_lock:
                    self._workers.add(worker)
                worker.start()
        finally:
            listener = self._listener
            self._listener = None
            if listener is not None:
                try:
                    listener.close()
                except OSError:
                    pass
            if family == "AF_UNIX":
                try:
                    Path(address).unlink(missing_ok=True)
                except OSError:
                    pass

    def _serve_connection(self, connection) -> None:
        try:
            data = connection.recv_bytes(MAX_FRAME_BYTES)
            future = asyncio.run_coroutine_threadsafe(self.handler(data), self.loop)
            response = future.result()
            connection.send_bytes(response)
        except BaseException:
            # The daemon logger owns detailed diagnostics. The connection is
            # simply closed here; protocol-level exceptions are converted by
            # the async handler before reaching this thread.
            pass
        finally:
            try:
                connection.close()
            except OSError:
                pass
            current = threading.current_thread()
            with self._workers_lock:
                self._workers.discard(current)

    def stop(self) -> None:
        self._stop.set()
        listener = self._listener
        if listener is not None:
            try:
                listener.close()
            except OSError:
                pass
        thread = self._accept_thread
        if thread and thread.is_alive():
            thread.join(timeout=1.5)
