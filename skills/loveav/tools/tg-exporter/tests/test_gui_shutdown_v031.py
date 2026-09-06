from __future__ import annotations

import asyncio
from types import SimpleNamespace

from telegram_exporter import daemon_gui as daemon_gui_module
from telegram_exporter.main import _run_app
from telegram_exporter.telegram_proxy import DaemonTelegramProxy


class FakeSignal:
    def __init__(self):
        self.callbacks = []

    def connect(self, callback):
        self.callbacks.append(callback)

    def disconnect(self, callback):
        self.callbacks.remove(callback)

    def emit(self):
        for callback in tuple(self.callbacks):
            callback()


class FakeApp:
    def __init__(self):
        self.lastWindowClosed = FakeSignal()
        self.quit_on_last_window_closed = True

    def setQuitOnLastWindowClosed(self, value: bool) -> None:
        self.quit_on_last_window_closed = bool(value)


class FakeWindow:
    def __init__(self):
        self.title = None
        self.shown = False
        self.shutdown_called = False

    def setWindowTitle(self, title: str) -> None:
        self.title = title

    def show(self) -> None:
        self.shown = True

    async def shutdown(self) -> None:
        await asyncio.sleep(0)
        self.shutdown_called = True


def test_run_app_waits_for_shutdown_before_returning() -> None:
    async def scenario() -> None:
        app = FakeApp()
        window = FakeWindow()
        task = asyncio.create_task(_run_app(app, window_factory=lambda: window))
        await asyncio.sleep(0)
        assert window.shown is True
        assert task.done() is False
        assert app.quit_on_last_window_closed is False

        app.lastWindowClosed.emit()
        result = await task
        assert result == 0
        assert window.shutdown_called is True
        assert app.lastWindowClosed.callbacks == []

    asyncio.run(scenario())


def test_daemon_gui_shutdown_cancels_local_tasks_and_only_detaches(monkeypatch) -> None:
    class FakeProxy:
        def __init__(self):
            self.closed = False
            self.shutdown_requested = False

        async def close(self):
            await asyncio.sleep(0)
            self.closed = True

        async def request_daemon_shutdown(self, *args, **kwargs):
            self.shutdown_requested = True
            raise AssertionError("GUI close must not shut down shared daemon")

    monkeypatch.setattr(daemon_gui_module, "DaemonTelegramProxy", FakeProxy)

    async def pending_forever():
        await asyncio.Event().wait()

    async def scenario() -> None:
        init_task = asyncio.create_task(pending_forever(), name="synthetic-init")
        monitor_task = asyncio.create_task(pending_forever(), name="synthetic-monitor")
        proxy = FakeProxy()
        window = SimpleNamespace(
            _shutdown_started=False,
            _initialize_task=init_task,
            _job_monitor_task=monitor_task,
            service=proxy,
        )
        await daemon_gui_module.MainWindow.shutdown(window)
        assert init_task.cancelled() is True
        assert monitor_task.cancelled() is True
        assert proxy.closed is True
        assert proxy.shutdown_requested is False
        assert window._shutdown_started is True
        assert window._initialize_task is None
        assert window._job_monitor_task is None

        # Idempotent second close must not create work or touch the daemon again.
        await daemon_gui_module.MainWindow.shutdown(window)
        assert proxy.shutdown_requested is False

    asyncio.run(scenario())


def test_proxy_close_stops_heartbeat_then_detaches_without_daemon_shutdown() -> None:
    class FakeIPC:
        def __init__(self):
            self.calls = []

        async def request(self, method, payload=None, **_kwargs):
            self.calls.append((method, payload))
            return {}

    async def heartbeat_forever():
        await asyncio.Event().wait()

    async def scenario() -> None:
        proxy = object.__new__(DaemonTelegramProxy)
        proxy.client_kind = "gui"
        proxy.ipc = FakeIPC()
        proxy._lease_token = "synthetic-lease"
        proxy._heartbeat_task = asyncio.create_task(heartbeat_forever(), name="synthetic-heartbeat")
        heartbeat = proxy._heartbeat_task

        await proxy.close()

        assert heartbeat.cancelled() is True
        assert proxy._heartbeat_task is None
        assert proxy._lease_token is None
        assert proxy.ipc.calls == [("client.detach", {"lease_token": "synthetic-lease"})]
        assert all(method != "system.shutdown" for method, _payload in proxy.ipc.calls)

    asyncio.run(scenario())
