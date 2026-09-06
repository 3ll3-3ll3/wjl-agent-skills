from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMenu, QStyle, QSystemTrayIcon

from .daemon_server import DaemonServer

logger = logging.getLogger("telegram_exporter.daemon_tray")


class DaemonTray:
    """Best-effort system tray for the background daemon.

    Explorer/tray failures must never affect Telegram/export jobs.
    """

    def __init__(self, app: QApplication, server: DaemonServer):
        self.app = app
        self.server = server
        self.tray: QSystemTrayIcon | None = None
        self.status_action: QAction | None = None
        self._timer: QTimer | None = None

        if not QSystemTrayIcon.isSystemTrayAvailable():
            logger.warning("Windows/system tray is not available; daemon continues without tray UI")
            return

        try:
            tray = QSystemTrayIcon(app.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon), app)
            menu = QMenu()
            status = QAction("TG 后台：启动中", menu)
            status.setEnabled(False)
            open_gui = QAction("打开 TG Exporter", menu)
            exit_daemon = QAction("退出后台", menu)
            menu.addAction(status)
            menu.addSeparator()
            menu.addAction(open_gui)
            menu.addAction(exit_daemon)
            tray.setContextMenu(menu)
            tray.setToolTip("TG Exporter Telegram 后台")
            open_gui.triggered.connect(self._open_gui)
            exit_daemon.triggered.connect(self._request_exit)
            tray.show()

            timer = QTimer(app)
            timer.setInterval(1000)
            timer.timeout.connect(self.refresh)
            timer.start()

            self.tray = tray
            self.status_action = status
            self._timer = timer
            self.refresh()
        except Exception:
            logger.warning("Creating daemon tray failed; daemon continues", exc_info=True)

    def _status_text(self) -> str:
        snapshot = self.server.status_snapshot()
        if snapshot["export_active"]:
            job = snapshot.get("active_job") or {}
            done = job.get("completed_groups", 0)
            total = job.get("total_groups", 0)
            return f"TG 后台：正在导出 {done}/{total}"
        if snapshot["authorized"]:
            return "TG 后台：Telegram 已连接"
        return "TG 后台：空闲 / 未登录"

    def refresh(self) -> None:
        text = self._status_text()
        if self.status_action is not None:
            self.status_action.setText(text)
        if self.tray is not None:
            self.tray.setToolTip(text)

    def _candidate_gui(self) -> Path | None:
        configured = self.server.gui_executable
        if configured:
            path = Path(configured)
            if path.exists():
                return path
        if getattr(sys, "frozen", False):
            current = Path(sys.executable)
            if current.name.lower().startswith("tgexporter"):
                return current
            for candidate in current.parent.glob("TGExporter*.exe"):
                if candidate.is_file():
                    return candidate
        return None

    def _open_gui(self) -> None:
        target = self._candidate_gui()
        if target is None:
            if self.tray is not None:
                self.tray.showMessage(
                    "TG Exporter",
                    "暂未找到 GUI 程序路径。请手动打开 TGExporter.exe。",
                    QSystemTrayIcon.MessageIcon.Information,
                    4000,
                )
            return
        try:
            creationflags = 0
            if os.name == "nt":
                creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            subprocess.Popen([str(target)], creationflags=creationflags, close_fds=True)
        except OSError:
            logger.warning("Failed to open TG Exporter from tray", exc_info=True)

    def _request_exit(self) -> None:
        async def request() -> None:
            if self.server.exports.has_active_job:
                self.server.shutdown_after_export = True
                if self.tray is not None:
                    self.tray.showMessage(
                        "TG Exporter",
                        "导出正在进行。后台会在导出完成后退出。",
                        QSystemTrayIcon.MessageIcon.Information,
                        4000,
                    )
                self.refresh()
                return
            await self.server.request_shutdown(after_export=True)

        try:
            asyncio.get_running_loop().create_task(request())
        except RuntimeError:
            logger.warning("Tray exit request could not access daemon event loop")

    def close(self) -> None:
        if self._timer is not None:
            self._timer.stop()
        if self.tray is not None:
            self.tray.hide()
