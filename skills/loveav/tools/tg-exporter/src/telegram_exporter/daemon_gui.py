from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox
from qasync import asyncSlot

from .export_categories import ensure_category_dirs
from .focused_gui import MainWindow as FocusedMainWindow
from .telegram_proxy import DaemonTelegramProxy

logger = logging.getLogger("telegram_exporter.daemon_gui")

TERMINAL_JOB_STATES = {"completed", "completed_with_failures", "failed", "interrupted"}


class MainWindow(FocusedMainWindow):
    """Production window backed by the single Telegram daemon."""

    def __init__(self):
        super().__init__()
        self._active_job_id: str | None = None
        self._job_monitor_task: asyncio.Task[None] | None = None
        self._initialize_task: asyncio.Task[None] | None = None
        self._shutdown_started = False
        QTimer.singleShot(0, self._schedule_daemon_initialize)

    def _schedule_daemon_initialize(self) -> None:
        if self._shutdown_started:
            return
        try:
            task = asyncio.get_running_loop().create_task(self._initialize_daemon(), name="tg-gui-daemon-init")
            self._initialize_task = task
            task.add_done_callback(self._initialize_done)
        except RuntimeError:
            logger.warning("GUI daemon initialization could not find qasync loop")

    def _initialize_done(self, task: asyncio.Task[None]) -> None:
        if self._initialize_task is task:
            self._initialize_task = None
        if task.cancelled():
            return
        try:
            task.result()
        except Exception:
            # _initialize_daemon normally handles recoverable attach/status
            # failures itself. This only catches an unexpected programming
            # failure so it is not silently lost as an un-retrieved task error.
            logger.exception("Unexpected GUI daemon initialization task failure")

    async def _initialize_daemon(self) -> None:
        try:
            service = await self._ensure_daemon_proxy()
            if self._shutdown_started:
                return
            jobs = await service.list_export_jobs()
            if self._shutdown_started:
                return
            active = next((job for job in jobs if job.get("state") in {"queued", "running"}), None)

            # A restarted GUI must be able to recover an active export
            # immediately. auth.status is a Telegram read and intentionally
            # waits for export completion, so only use local daemon status here.
            if active:
                daemon_status = await service.daemon_status()
                if self._shutdown_started:
                    return
                if daemon_status.get("authorized"):
                    self.connect_btn.setText("Telegram 已连接")
                    self.refresh_btn.setEnabled(True)
                self._active_job_id = str(active["job_id"])
                self.status.setText("检测到仍在后台运行的导出任务，已恢复进度显示。")
                self._start_job_monitor(self._active_job_id, restored=True)
                return

            auth = await service.auth_status()
            if self._shutdown_started:
                return
            if auth.get("authorized"):
                self.connect_btn.setText("Telegram 已连接")
                self.refresh_btn.setEnabled(True)
                self.export_btn.setEnabled(bool(self.groups))
            if jobs:
                latest = jobs[0]
                if latest.get("state") == "interrupted":
                    self.status.setText("上次后台任务因 daemon 退出而中断；没有伪报为成功。")
                elif auth.get("authorized"):
                    self.status.setText("Telegram 后台已连接。可刷新群组目录或开始新的导出。")
            elif auth.get("authorized"):
                self.status.setText("Telegram 后台已连接。可刷新群组目录。")
            else:
                self.status.setText("TG 后台已启动；Telegram 尚未登录。请点击『连接 Telegram』。")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if self._shutdown_started:
                return
            logger.warning("Initial daemon attach/status failed", exc_info=(type(exc), exc, exc.__traceback__))
            self.status.setText("TG 后台暂未就绪；点击『连接 Telegram』时会再次尝试启动。")

    @asyncSlot()
    async def start_export(self) -> None:
        if self._busy or self._shutdown_started:
            return
        service = self.service
        if not isinstance(service, DaemonTelegramProxy):
            try:
                service = await self._ensure_daemon_proxy()
            except Exception as exc:
                self._show_error(exc)
                return

        try:
            row_plans = self._plans()
        except ValueError as exc:
            self._show_message(QMessageBox.Warning, "导出配置无效", str(exc))
            return
        if not row_plans:
            self._show_message(QMessageBox.Information, "没有选择群组", "请至少选择一个群组。")
            return

        output_root = Path(self.output_label.text())
        try:
            ensure_category_dirs(output_root, self._custom_categories())
        except OSError as exc:
            self._show_message(QMessageBox.Warning, "无法准备输出目录", str(exc))
            return

        export_moment = datetime.now().astimezone()
        try:
            job = await service.start_export_batch(
                [(plan, mark_read) for _row, plan, mark_read in row_plans],
                output_root,
                export_moment=export_moment,
            )
        except Exception as exc:
            self._show_error(exc)
            return

        self._active_job_id = str(job["job_id"])
        self.progress.setRange(0, int(job.get("total_groups", len(row_plans))))
        self.progress.setValue(0)
        for row, _plan, _mark_read in row_plans:
            item = self.table.item(row, 8)
            if item:
                item.setText("等待后台导出…")
        self._set_busy(True, f"后台开始导出 {len(row_plans)} 个群组。关闭窗口也会继续。")
        self._start_job_monitor(self._active_job_id, restored=False)

    def _start_job_monitor(self, job_id: str, *, restored: bool) -> None:
        if self._shutdown_started:
            return
        task = self._job_monitor_task
        if task is not None and not task.done():
            task.cancel()
        self._job_monitor_task = asyncio.create_task(
            self._monitor_job(job_id, restored=restored),
            name=f"tg-gui-job-{job_id[:8]}",
        )

    async def _monitor_job(self, job_id: str, *, restored: bool) -> None:
        service = self.service
        if not isinstance(service, DaemonTelegramProxy):
            return
        terminal: dict | None = None
        try:
            while not self._shutdown_started:
                job = await service.export_job_status(job_id)
                state = str(job.get("state"))
                total = int(job.get("total_groups", 0))
                done = int(job.get("completed_groups", 0))
                self.progress.setRange(0, max(1, total))
                self.progress.setValue(done)
                current_title = job.get("current_title")
                current_messages = int(job.get("current_message_count", 0))
                if state not in TERMINAL_JOB_STATES:
                    self._set_busy(
                        True,
                        f"后台导出：{done}/{total} 个群组"
                        + (f"；当前 {current_title}，已读取 {current_messages} 条文本" if current_title else ""),
                    )
                    self._apply_running_job_rows(job)
                    await asyncio.sleep(0.5)
                    continue
                terminal = job
                break
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if not self._shutdown_started:
                logger.error("GUI export job monitor failed", exc_info=(type(exc), exc, exc.__traceback__))
                self._set_busy(False, "后台任务状态读取失败；可重新打开程序恢复查看。")
            return
        finally:
            if self._job_monitor_task is asyncio.current_task():
                self._job_monitor_task = None

        if self._shutdown_started:
            return
        self._active_job_id = None
        self._set_busy(False)
        if terminal is not None:
            self._apply_terminal_job_rows(terminal)
            self._show_job_summary(terminal, restored=restored)

    def _row_by_chat_id(self, chat_id: int) -> int | None:
        for row, group in enumerate(self.groups):
            if group.chat_id == chat_id:
                return row
        return None

    def _apply_running_job_rows(self, job: dict) -> None:
        completed_ids = {int(item["chat_id"]) for item in job.get("results", []) if item.get("chat_id") is not None}
        failed_ids = {int(item["chat_id"]) for item in job.get("failures", []) if item.get("chat_id") is not None}
        current = job.get("current_chat_id")
        for row, group in enumerate(self.groups):
            item = self.table.item(row, 8)
            if not item:
                continue
            if group.chat_id in completed_ids:
                item.setText("后台导出完成")
            elif group.chat_id in failed_ids:
                item.setText("后台导出失败；未改变已读状态")
            elif current is not None and group.chat_id == int(current):
                item.setText(f"后台导出中… {int(job.get('current_message_count', 0))} 条")

    def _apply_terminal_job_rows(self, job: dict) -> None:
        for result in job.get("results", []):
            chat_id = int(result["chat_id"])
            row = self._row_by_chat_id(chat_id)
            if row is None:
                continue
            read_ack = result.get("read_ack")
            suffix = ""
            if read_ack == "success":
                suffix = "；已标已读"
                unread = self.table.item(row, 6)
                if unread:
                    unread.setText("0")
                self.groups[row].unread_count = 0
            elif read_ack == "failed":
                suffix = "；标已读失败"
            item = self.table.item(row, 8)
            if item:
                item.setText(f"完成：{int(result.get('message_count', 0))} 条{suffix}")
        for failure in job.get("failures", []):
            row = self._row_by_chat_id(int(failure["chat_id"]))
            if row is not None:
                item = self.table.item(row, 8)
                if item:
                    item.setText("失败；未改变已读状态")

    def _show_job_summary(self, job: dict, *, restored: bool) -> None:
        state = str(job.get("state"))
        success = int(job.get("success_count", 0))
        failed = int(job.get("failure_count", 0))
        total_messages = int(job.get("total_messages", 0))
        marked = int(job.get("marked_read_count", 0))
        output_root = str(job.get("output_root", ""))

        if state == "interrupted":
            self.status.setText("后台导出曾中断；未完成任务没有被标记成功。")
            if not restored:
                self._show_message(QMessageBox.Warning, "后台导出中断", str(job.get("error") or "daemon 已退出。"))
            return

        self.status.setText(
            f"后台导出完成：成功 {success}，失败 {failed}，共 {total_messages} 条文本；已标已读 {marked} 个群。"
        )
        icon = QMessageBox.Warning if failed or state == "failed" else QMessageBox.Information
        title = "后台导出完成（有失败）" if failed or state == "failed" else "后台导出完成"
        self._show_message(
            icon,
            title,
            f"成功 {success} 个群，失败 {failed} 个，共 {total_messages} 条纯文本消息。"
            f"\n已按设置标已读 {marked} 个群。\n\n总输出目录：\n{output_root}",
        )

    async def shutdown(self) -> None:
        if self._shutdown_started:
            return
        self._shutdown_started = True
        logger.info("GUI shutdown: detach from daemon; active export is not cancelled")

        tasks = [self._initialize_task, self._job_monitor_task]
        self._initialize_task = None
        self._job_monitor_task = None
        pending = [task for task in tasks if task is not None and not task.done()]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

        if isinstance(self.service, DaemonTelegramProxy):
            await self.service.close()
