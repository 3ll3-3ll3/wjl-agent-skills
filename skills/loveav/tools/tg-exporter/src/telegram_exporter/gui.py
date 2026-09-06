from __future__ import annotations

import logging
from datetime import datetime, time, timezone
from pathlib import Path

from PySide6.QtCore import QDate, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QInputDialog,
)
from qasync import asyncSlot

from .diagnostics import friendly_error_message
from .exporter import export_group
from .logging_setup import log_file_path
from .models import ExportMode, GroupExportPlan, GroupInfo
from .paths import credentials_path, logs_dir, session_files, session_path, settings_path, state_path
from .storage import LocalState, read_json, write_json_atomic
from .telegram_service import ApiCredentials, TelegramService

logger = logging.getLogger("telegram_exporter.gui")

MODE_LABELS = {
    ExportMode.DATE_RANGE: "指定时间范围",
    ExportMode.UNREAD: "当前未读",
    ExportMode.SINCE_LAST_EXPORT: "上次导出以后",
}
MODE_BY_LABEL = {v: k for k, v in MODE_LABELS.items()}


class CredentialsDialog(QDialog):
    def __init__(self, parent=None, initial: ApiCredentials | None = None):
        super().__init__(parent)
        self.setWindowTitle("Telegram API 配置")
        self.resize(520, 220)
        layout = QFormLayout(self)
        self.api_id = QSpinBox()
        self.api_id.setMinimum(1)
        self.api_id.setMaximum(2_147_483_647)
        self.api_hash = QLineEdit()
        self.api_hash.setEchoMode(QLineEdit.Password)
        if initial:
            self.api_id.setValue(initial.api_id)
            self.api_hash.setText(initial.api_hash)
        info = QLabel(
            '请使用 <a href="https://my.telegram.org">my.telegram.org</a> → API development tools 中'
            '你自己的 <b>api_id</b> 与 <b>api_hash</b>。这里不是 BotFather 的 Bot Token。'
        )
        info.setOpenExternalLinks(True)
        info.setWordWrap(True)
        layout.addRow(info)
        layout.addRow("API ID", self.api_id)
        layout.addRow("API Hash", self.api_hash)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def value(self) -> ApiCredentials:
        return ApiCredentials(self.api_id.value(), self.api_hash.text().strip())


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Telegram 多群批次导出器")
        self.resize(1260, 780)
        self.groups: list[GroupInfo] = []
        self.state = LocalState(state_path())
        self.service: TelegramService | None = None
        self._busy = False

        central = QWidget()
        root = QVBoxLayout(central)
        self.setCentralWidget(central)

        top = QHBoxLayout()
        self.connect_btn = QPushButton("连接 Telegram")
        self.api_btn = QPushButton("API 设置")
        self.reset_login_btn = QPushButton("重置登录")
        self.logs_btn = QPushButton("打开日志目录")
        self.refresh_btn = QPushButton("刷新群组")
        self.refresh_btn.setEnabled(False)
        self.output_btn = QPushButton("选择输出目录")
        self.output_label = QLabel(str(self._default_output_dir()))
        self.output_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        top.addWidget(self.connect_btn)
        top.addWidget(self.api_btn)
        top.addWidget(self.reset_login_btn)
        top.addWidget(self.logs_btn)
        top.addWidget(self.refresh_btn)
        top.addWidget(self.output_btn)
        top.addStretch(1)
        root.addLayout(top)
        root.addWidget(self.output_label)

        hint = QLabel(
            "一次可导出多个群；每个群可单独选择『指定时间范围 / 当前未读 / 上次导出以后』。"
            "每次导出都是独立批次，不会合并历史消息。连接失败时请先查看错误提示；详细信息会写入本地日志。"
        )
        hint.setWordWrap(True)
        root.addWidget(hint)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["导出", "群组", "导出方式", "开始日期", "结束日期", "未读", "状态"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        root.addWidget(self.table, 1)

        actions = QHBoxLayout()
        self.select_all_btn = QPushButton("全选")
        self.select_none_btn = QPushButton("全不选")
        self.bulk_10_btn = QPushButton("选中群设为最近 10 天")
        self.export_btn = QPushButton("开始导出")
        self.export_btn.setEnabled(False)
        actions.addWidget(self.select_all_btn)
        actions.addWidget(self.select_none_btn)
        actions.addWidget(self.bulk_10_btn)
        actions.addStretch(1)
        actions.addWidget(self.export_btn)
        root.addLayout(actions)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.status = QLabel("尚未连接 Telegram。")
        root.addWidget(self.progress)
        root.addWidget(self.status)

        self.connect_btn.clicked.connect(self.connect_telegram)
        self.api_btn.clicked.connect(self.edit_api_settings)
        self.reset_login_btn.clicked.connect(self.reset_login)
        self.logs_btn.clicked.connect(self.open_logs)
        self.refresh_btn.clicked.connect(self.refresh_groups)
        self.output_btn.clicked.connect(self.choose_output)
        self.select_all_btn.clicked.connect(lambda: self._set_all_checked(True))
        self.select_none_btn.clicked.connect(lambda: self._set_all_checked(False))
        self.bulk_10_btn.clicked.connect(self.bulk_recent_10)
        self.export_btn.clicked.connect(self.start_export)

        logger.info("Main window initialized")

    def _default_output_dir(self) -> Path:
        saved = read_json(settings_path(), {})
        return Path(saved.get("output_dir", str(Path.home() / "Documents" / "Telegram Exports")))

    def choose_output(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择导出目录", str(self._default_output_dir()))
        if path:
            self.output_label.setText(path)
            write_json_atomic(settings_path(), {"output_dir": path})
            logger.info("Output directory changed to %s", path)

    def open_logs(self) -> None:
        path = logs_dir()
        opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        if not opened:
            QMessageBox.information(self, "日志目录", f"日志目录：\n{path}")

    def _saved_credentials(self) -> ApiCredentials | None:
        payload = read_json(credentials_path(), None)
        if not payload:
            return None
        try:
            return ApiCredentials(int(payload["api_id"]), str(payload["api_hash"]))
        except (KeyError, TypeError, ValueError):
            logger.warning("Stored API credential file is invalid; asking user to re-enter it")
            return None

    def _save_credentials(self, creds: ApiCredentials) -> bool:
        if creds.api_id <= 0 or not creds.api_hash:
            QMessageBox.warning(self, "配置无效", "API ID 和 API Hash 不能为空。")
            return False
        write_json_atomic(credentials_path(), {"api_id": creds.api_id, "api_hash": creds.api_hash})
        logger.info("Telegram API credentials saved locally (api_id=%s; api_hash not logged)", creds.api_id)
        return True

    def _load_credentials(self) -> ApiCredentials | None:
        saved = self._saved_credentials()
        if saved:
            return saved
        dlg = CredentialsDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return None
        creds = dlg.value()
        return creds if self._save_credentials(creds) else None

    @asyncSlot()
    async def edit_api_settings(self) -> None:
        if self._busy:
            return
        current = self._saved_credentials()
        dlg = CredentialsDialog(self, current)
        if dlg.exec() != QDialog.Accepted:
            return
        creds = dlg.value()
        if not self._save_credentials(creds):
            return
        if self.service:
            await self.service.close()
            self.service = None
        self._mark_disconnected(clear_groups=True)
        self.status.setText("API 设置已保存。请点击『连接 Telegram』重新连接。")

    @asyncSlot()
    async def reset_login(self) -> None:
        if self._busy:
            return
        answer = QMessageBox.question(
            self,
            "重置 Telegram 登录",
            "这会删除本机由本程序创建的 Telegram Session，并要求下次重新输入手机号/验证码。\n\n"
            "不会删除 API ID/API Hash，也不会影响 Telegram 官方客户端。确定继续吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._set_busy(True, "正在重置本地登录状态…")
        try:
            if self.service:
                await self.service.close()
                self.service = None
            removed = 0
            for path in session_files():
                try:
                    if path.exists():
                        path.unlink()
                        removed += 1
                except OSError as exc:
                    logger.error("Failed to remove session file %s: %s", path.name, exc)
                    raise
            logger.info("Telegram local session reset; removed_files=%s", removed)
            self._mark_disconnected(clear_groups=True)
            QMessageBox.information(self, "重置完成", "本地 Telegram Session 已清除。下次连接会重新登录。")
        except Exception as exc:
            self._show_error(exc)
        finally:
            self._set_busy(False)

    async def _first_login(self) -> bool:
        assert self.service
        phone, ok = QInputDialog.getText(self, "Telegram 登录", "手机号（含国家区号，例如 +86...）：")
        if not ok or not phone.strip():
            logger.info("First login cancelled before phone submission")
            return False
        self.status.setText("正在发送 Telegram 验证码…")
        await self.service.send_code(phone.strip())

        code, ok = QInputDialog.getText(self, "Telegram 验证码", "请输入 Telegram 收到的验证码：")
        if not ok or not code.strip():
            logger.info("First login cancelled before code submission")
            return False
        needs_password = not await self.service.sign_in_code(phone.strip(), code.strip())
        if needs_password:
            password, ok = QInputDialog.getText(
                self,
                "两步验证",
                "账号已启用两步验证，请输入 Telegram 2FA 密码：",
                QLineEdit.Password,
            )
            if not ok or not password:
                logger.info("First login cancelled before 2FA submission")
                return False
            await self.service.sign_in_password(password)
        return True

    @asyncSlot()
    async def connect_telegram(self) -> None:
        if self._busy:
            return
        creds = self._load_credentials()
        if not creds:
            return
        self._set_busy(True, "正在连接 Telegram…")
        logger.info("User started Telegram connection (api_id=%s)", creds.api_id)
        try:
            if self.service:
                await self.service.close()
            self.service = TelegramService(creds, session_path())
            authorized = await self.service.connect()
            if not authorized:
                self.status.setText("网络已连接，账号尚未登录，准备发送验证码…")
                authorized = await self._first_login()
            if not authorized:
                self.status.setText("登录已取消。")
                return
            self.refresh_btn.setEnabled(True)
            self.export_btn.setEnabled(True)
            self.connect_btn.setText("Telegram 已连接")
            await self._refresh_groups_impl()
            logger.info("Telegram connection and dialog loading succeeded")
        except Exception as exc:
            self._show_error(exc)
        finally:
            self._set_busy(False)

    @asyncSlot()
    async def refresh_groups(self) -> None:
        if self._busy or not self.service:
            return
        self._set_busy(True, "正在刷新群组…")
        try:
            await self._refresh_groups_impl()
        except Exception as exc:
            self._show_error(exc)
        finally:
            self._set_busy(False)

    async def _refresh_groups_impl(self) -> None:
        assert self.service
        groups = await self.service.list_groups()
        self._groups_loaded(groups)

    def _groups_loaded(self, groups: list[GroupInfo]) -> None:
        self.groups = groups
        self.table.setRowCount(len(groups))
        today = QDate.currentDate()
        for row, group in enumerate(groups):
            check = QCheckBox()
            check.setChecked(True)
            self.table.setCellWidget(row, 0, check)
            title = QTableWidgetItem(group.title)
            title.setToolTip(f"Telegram peer id: {group.chat_id}")
            self.table.setItem(row, 1, title)

            mode = QComboBox()
            for export_mode, label in MODE_LABELS.items():
                mode.addItem(label, export_mode.value)
            self.table.setCellWidget(row, 2, mode)

            start = QDateEdit(today.addDays(-9))
            start.setCalendarPopup(True)
            start.setDisplayFormat("yyyy-MM-dd")
            end = QDateEdit(today)
            end.setCalendarPopup(True)
            end.setDisplayFormat("yyyy-MM-dd")
            self.table.setCellWidget(row, 3, start)
            self.table.setCellWidget(row, 4, end)
            self.table.setItem(row, 5, QTableWidgetItem(str(group.unread_count)))
            self.table.setItem(row, 6, QTableWidgetItem("待导出"))
            mode.currentTextChanged.connect(lambda _text, r=row: self._update_row_mode(r))
        self.status.setText(f"已加载 {len(groups)} 个群组/频道。")

    def _update_row_mode(self, row: int) -> None:
        mode = self.table.cellWidget(row, 2)
        start = self.table.cellWidget(row, 3)
        end = self.table.cellWidget(row, 4)
        assert isinstance(mode, QComboBox) and isinstance(start, QDateEdit) and isinstance(end, QDateEdit)
        enabled = ExportMode(mode.currentData()) is ExportMode.DATE_RANGE
        start.setEnabled(enabled)
        end.setEnabled(enabled)
        status_item = self.table.item(row, 6)
        if status_item:
            if ExportMode(mode.currentData()) is ExportMode.UNREAD:
                status_item.setText("将按当前未读位置导出")
            elif ExportMode(mode.currentData()) is ExportMode.SINCE_LAST_EXPORT:
                last_id = self.state.last_message_id(self.groups[row].chat_id)
                status_item.setText(f"上次位置：{last_id}" if last_id else "尚无上次导出记录")
            else:
                status_item.setText("待导出")

    def _set_all_checked(self, checked: bool) -> None:
        for row in range(self.table.rowCount()):
            widget = self.table.cellWidget(row, 0)
            if isinstance(widget, QCheckBox):
                widget.setChecked(checked)

    def bulk_recent_10(self) -> None:
        today = QDate.currentDate()
        for row in range(self.table.rowCount()):
            check = self.table.cellWidget(row, 0)
            if not isinstance(check, QCheckBox) or not check.isChecked():
                continue
            mode = self.table.cellWidget(row, 2)
            start = self.table.cellWidget(row, 3)
            end = self.table.cellWidget(row, 4)
            assert isinstance(mode, QComboBox) and isinstance(start, QDateEdit) and isinstance(end, QDateEdit)
            mode.setCurrentIndex(mode.findData(ExportMode.DATE_RANGE.value))
            start.setDate(today.addDays(-9))
            end.setDate(today)

    def _plans(self) -> list[tuple[int, GroupExportPlan]]:
        plans: list[tuple[int, GroupExportPlan]] = []
        local_tz = datetime.now().astimezone().tzinfo or timezone.utc
        for row, group in enumerate(self.groups):
            check = self.table.cellWidget(row, 0)
            if not isinstance(check, QCheckBox) or not check.isChecked():
                continue
            mode_box = self.table.cellWidget(row, 2)
            start_edit = self.table.cellWidget(row, 3)
            end_edit = self.table.cellWidget(row, 4)
            assert isinstance(mode_box, QComboBox)
            mode = ExportMode(mode_box.currentData())
            start_at = end_at = None
            if mode is ExportMode.DATE_RANGE:
                assert isinstance(start_edit, QDateEdit) and isinstance(end_edit, QDateEdit)
                start_at = datetime.combine(start_edit.date().toPython(), time.min, local_tz)
                end_at = datetime.combine(end_edit.date().toPython(), time.max, local_tz)
            plan = GroupExportPlan(
                group=group,
                mode=mode,
                start_at=start_at,
                end_at=end_at,
                last_export_message_id=self.state.last_message_id(group.chat_id),
            )
            plan.validate()
            plans.append((row, plan))
        return plans

    @asyncSlot()
    async def start_export(self) -> None:
        if self._busy or not self.service:
            return
        try:
            plans = self._plans()
        except ValueError as exc:
            QMessageBox.warning(self, "导出配置无效", str(exc))
            return
        if not plans:
            QMessageBox.information(self, "没有选择群组", "请至少选择一个群组。")
            return

        batch_name = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        batch_dir = Path(self.output_label.text()) / batch_name
        self._set_busy(True, f"准备导出 {len(plans)} 个群组…")
        self.progress.setRange(0, len(plans))
        self.progress.setValue(0)
        results = []
        failures: list[tuple[str, str]] = []
        logger.info("Starting export batch %s with %s groups", batch_name, len(plans))
        try:
            for done, (row, plan) in enumerate(plans, start=1):
                status_item = self.table.item(row, 6)
                if status_item:
                    status_item.setText("导出中…")
                try:
                    logger.info("Exporting group '%s' mode=%s", plan.group.title, plan.mode.value)
                    result = await export_group(self.service.client, plan, batch_dir)
                    results.append(result)
                    if result.latest_message_id:
                        self.state.mark_success(
                            result.chat_id,
                            result.latest_message_id,
                            datetime.now().astimezone().isoformat(timespec="seconds"),
                        )
                    if status_item:
                        status_item.setText(f"完成：{result.message_count} 条")
                    logger.info("Exported group '%s': %s messages", plan.group.title, result.message_count)
                except Exception as exc:
                    logger.error(
                        "Export failed for group '%s'",
                        plan.group.title,
                        exc_info=(type(exc), exc, exc.__traceback__),
                    )
                    failures.append((plan.group.title, f"{type(exc).__name__}: {exc}"))
                    if status_item:
                        status_item.setText("失败")
                self.progress.setValue(done)
                self.status.setText(f"进度：{done}/{len(plans)} 个群组")
        finally:
            self._set_busy(False)

        total = sum(r.message_count for r in results)
        logger.info("Export batch completed: success=%s failed=%s messages=%s", len(results), len(failures), total)
        if failures:
            detail = "\n".join(f"• {name}: {err}" for name, err in failures[:8])
            QMessageBox.warning(
                self,
                "导出部分完成",
                f"成功 {len(results)} 个群，共 {total} 条；失败 {len(failures)} 个。\n\n{detail}\n\n日志：{log_file_path()}",
            )
        else:
            QMessageBox.information(
                self,
                "导出完成",
                f"成功导出 {len(results)} 个群组，共 {total} 条纯文本消息。\n\n输出目录：\n{batch_dir}",
            )
        self.status.setText(f"本批次完成：成功 {len(results)}，失败 {len(failures)}，共 {total} 条文本。")

    def _mark_disconnected(self, clear_groups: bool = False) -> None:
        self.connect_btn.setText("连接 Telegram")
        self.refresh_btn.setEnabled(False)
        self.export_btn.setEnabled(False)
        if clear_groups:
            self.groups = []
            self.table.setRowCount(0)

    def _set_busy(self, busy: bool, status: str | None = None) -> None:
        self._busy = busy
        self.connect_btn.setEnabled(not busy)
        self.api_btn.setEnabled(not busy)
        self.reset_login_btn.setEnabled(not busy)
        self.logs_btn.setEnabled(True)
        self.refresh_btn.setEnabled(not busy and self.service is not None)
        self.output_btn.setEnabled(not busy)
        self.export_btn.setEnabled(not busy and self.service is not None and bool(self.groups))
        if status:
            self.status.setText(status)

    def _show_error(self, exc: Exception) -> None:
        logger.error("GUI operation failed", exc_info=(type(exc), exc, exc.__traceback__))
        friendly = friendly_error_message(exc)
        raw = f"{type(exc).__name__}: {exc}"
        self.status.setText("操作失败。可点击『打开日志目录』查看详细日志。")
        QMessageBox.critical(
            self,
            "Telegram 操作失败",
            f"{friendly}\n\n原始错误：{raw}\n\n日志文件：\n{log_file_path()}",
        )

    async def shutdown(self) -> None:
        logger.info("Application shutdown requested")
        if self.service:
            await self.service.close()
