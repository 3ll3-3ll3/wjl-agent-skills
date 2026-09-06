from __future__ import annotations

import asyncio
import logging
import sys

from PySide6.QtWidgets import QApplication
from qasync import QEventLoop

from .daemon_server_v3 import DaemonServer
from .daemon_tray import DaemonTray
from .ipc_identity import load_or_create_identity
from .ipc_transport import PipeServer
from .logging_setup import setup_logging
from .paths import daemon_lock_path
from .session_lock import FileBusyError, FileLease

IDLE_SHUTDOWN_SECONDS = 10 * 60


async def _run_daemon(app: QApplication) -> int:
    logger = logging.getLogger("telegram_exporter.daemon")
    server = DaemonServer()
    identity = load_or_create_identity()
    pipe = PipeServer(identity, asyncio.get_running_loop(), server.handle_bytes)
    pipe.start()
    await asyncio.to_thread(pipe.wait_ready, 5.0)
    tray = DaemonTray(app, server)
    logger.info("TG daemon ready (protocol pipe instance=%s)", identity.instance_id)

    async def lifecycle() -> None:
        while not server.shutdown_event.is_set():
            if server.shutdown_after_export and not server.exports.has_active_job:
                logger.info("Daemon exit-after-export condition reached")
                server.shutdown_event.set()
                return
            if server.can_idle_shutdown(IDLE_SHUTDOWN_SECONDS):
                logger.info("Daemon idle timeout reached; shutting down")
                server.shutdown_event.set()
                return
            await asyncio.sleep(2.0)

    lifecycle_task = asyncio.create_task(lifecycle(), name="tg-daemon-lifecycle")
    try:
        await server.shutdown_event.wait()
    finally:
        lifecycle_task.cancel()
        try:
            await lifecycle_task
        except asyncio.CancelledError:
            pass
        pipe.stop()
        tray.close()
        try:
            await server.close()
        except Exception:
            logger.exception("Daemon Telegram cleanup failed")
    return 0


def main() -> int:
    setup_logging()
    logger = logging.getLogger("telegram_exporter.daemon")
    lease = FileLease(
        daemon_lock_path(),
        busy_message="另一个 TG daemon 已经在运行。",
    )
    try:
        lease.acquire()
    except FileBusyError:
        logger.info("Daemon start skipped because another daemon owns the singleton lock")
        return 0

    try:
        app = QApplication.instance() or QApplication([sys.argv[0]])
        app.setApplicationName("TG Exporter Background")
        app.setOrganizationName("WJL")
        app.setQuitOnLastWindowClosed(False)
        return asyncio.run(_run_daemon(app), loop_factory=QEventLoop)
    except Exception:
        logger.exception("Fatal TG daemon error")
        return 1
    finally:
        lease.release()


if __name__ == "__main__":
    raise SystemExit(main())
