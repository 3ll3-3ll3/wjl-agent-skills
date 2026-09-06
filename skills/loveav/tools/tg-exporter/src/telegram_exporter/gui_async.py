from __future__ import annotations

import asyncio
import logging

from PySide6.QtWidgets import QDialog, QInputDialog, QLineEdit, QMessageBox
from qasync import asyncSlot

from .diagnostics import friendly_error_message
from .gui import CredentialsDialog, MainWindow as BaseMainWindow
from .logging_setup import log_file_path
from .storage import write_json_atomic
from .paths import credentials_path
from .telegram_proxy import DaemonTelegramProxy
from .telegram_service import ApiCredentials

logger = logging.getLogger("telegram_exporter.gui")


class MainWindow(BaseMainWindow):
    """qasync-safe GUI using the single daemon as Telegram owner."""

    def __init__(self):
        super().__init__()
        self._open_message_boxes: set[QMessageBox] = set()

    async def _await_dialog(self, dialog: QDialog) -> int:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[int] = loop.create_future()

        def on_finished(result: int) -> None:
            if not future.done():
                future.set_result(result)

        dialog.finished.connect(on_finished)
        dialog.open()
        try:
            return await future
        finally:
            try:
                dialog.finished.disconnect(on_finished)
            except (RuntimeError, TypeError):
                pass

    async def _prompt_text(
        self,
        title: str,
        label: str,
        *,
        echo_mode: QLineEdit.EchoMode = QLineEdit.Normal,
    ) -> tuple[str, bool]:
        dialog = QInputDialog(self)
        dialog.setWindowTitle(title)
        dialog.setLabelText(label)
        dialog.setInputMode(QInputDialog.TextInput)
        dialog.setTextEchoMode(echo_mode)
        result = await self._await_dialog(dialog)
        text = dialog.textValue()
        dialog.deleteLater()
        return text, result == QDialog.Accepted

    async def _edit_credentials_dialog(self, initial: ApiCredentials | None) -> ApiCredentials | None:
        dialog = CredentialsDialog(self, initial)
        result = await self._await_dialog(dialog)
        if result != QDialog.Accepted:
            dialog.deleteLater()
            return None
        value = dialog.value()
        dialog.deleteLater()
        return value

    async def _ask_yes_no(self, title: str, text: str) -> bool:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle(title)
        box.setText(text)
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        box.setDefaultButton(QMessageBox.No)
        await self._await_dialog(box)
        clicked = box.standardButton(box.clickedButton())
        box.deleteLater()
        return clicked == QMessageBox.Yes

    def _show_message(self, icon: QMessageBox.Icon, title: str, text: str) -> None:
        box = QMessageBox(self)
        box.setIcon(icon)
        box.setWindowTitle(title)
        box.setText(text)
        box.setStandardButtons(QMessageBox.Ok)
        self._open_message_boxes.add(box)

        def cleanup(_result: int) -> None:
            self._open_message_boxes.discard(box)
            box.deleteLater()

        box.finished.connect(cleanup)
        box.open()

    def _save_credentials(self, creds: ApiCredentials) -> bool:
        if creds.api_id <= 0 or not creds.api_hash:
            self._show_message(QMessageBox.Warning, "配置无效", "API ID 和 API Hash 不能为空。")
            return False
        write_json_atomic(credentials_path(), {"api_id": creds.api_id, "api_hash": creds.api_hash})
        logger.info("Telegram API credentials saved locally")
        return True

    async def _load_credentials_async(self) -> ApiCredentials | None:
        saved = self._saved_credentials()
        if saved:
            return saved
        creds = await self._edit_credentials_dialog(None)
        if creds is None:
            return None
        return creds if self._save_credentials(creds) else None

    async def _ensure_daemon_proxy(self) -> DaemonTelegramProxy:
        service = self.service
        if not isinstance(service, DaemonTelegramProxy):
            service = DaemonTelegramProxy("gui")
            self.service = service
        await service.attach_gui()
        return service

    @asyncSlot()
    async def edit_api_settings(self) -> None:
        if self._busy:
            return
        creds = await self._edit_credentials_dialog(self._saved_credentials())
        if creds is None or not self._save_credentials(creds):
            return
        self._set_busy(True, "正在把 API 配置同步到 Telegram 后台…")
        try:
            service = await self._ensure_daemon_proxy()
            await service.configure_api(creds)
            self._mark_disconnected(clear_groups=True)
            self.status.setText("API 设置已保存。请点击『连接 Telegram』继续。")
        except Exception as exc:
            self._show_error(exc)
        finally:
            self._set_busy(False)

    @asyncSlot()
    async def reset_login(self) -> None:
        if self._busy:
            return
        confirmed = await self._ask_yes_no(
            "重置 Telegram 登录",
            "这会删除本机由本程序创建的 Telegram Session，并要求下次重新输入手机号/验证码。\n\n"
            "不会删除 API ID/API Hash，也不会影响 Telegram 官方客户端。确定继续吗？",
        )
        if not confirmed:
            return
        self._set_busy(True, "正在重置本地登录状态…")
        try:
            service = await self._ensure_daemon_proxy()
            removed = await service.reset_session()
            logger.info("Telegram local session reset by daemon; removed_files=%s", removed)
            self._mark_disconnected(clear_groups=True)
            self._show_message(
                QMessageBox.Information,
                "重置完成",
                "本地 Telegram Session 已清除。下次连接会重新登录。",
            )
        except Exception as exc:
            self._show_error(exc)
        finally:
            self._set_busy(False)

    async def _first_login(self) -> bool:
        assert isinstance(self.service, DaemonTelegramProxy)
        phone, ok = await self._prompt_text(
            "Telegram 登录",
            "手机号（含国家区号，例如 +86...）：",
        )
        if not ok or not phone.strip():
            logger.info("First login cancelled before phone submission")
            return False

        self.status.setText("正在发送 Telegram 验证码…")
        await self.service.send_code(phone.strip())

        code, ok = await self._prompt_text(
            "Telegram 验证码",
            "请输入 Telegram 收到的验证码：",
        )
        if not ok or not code.strip():
            logger.info("First login cancelled before code submission")
            return False

        complete = await self.service.sign_in_code(phone.strip(), code.strip())
        if not complete:
            password, ok = await self._prompt_text(
                "两步验证",
                "账号已启用两步验证，请输入 Telegram 2FA 密码：",
                echo_mode=QLineEdit.Password,
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
        creds = await self._load_credentials_async()
        if not creds:
            return
        self._set_busy(True, "正在连接 Telegram 后台…")
        logger.info("User started Telegram daemon connection")
        try:
            service = await self._ensure_daemon_proxy()
            auth = await service.auth_status()
            if not auth.get("configured"):
                authorized = await service.configure_api(creds)
            else:
                authorized = bool(auth.get("authorized"))
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
            logger.info("Telegram daemon connection and dialog loading succeeded")
        except Exception as exc:
            self._show_error(exc)
        finally:
            self._set_busy(False)

    def _show_error(self, exc: Exception) -> None:
        # Do not log raw exception messages here: Telegram/auth exceptions may
        # contain request-specific data. The safe type + friendly diagnostic is
        # enough for ordinary logs/UI.
        logger.error("GUI operation failed error_type=%s", type(exc).__name__)
        friendly = friendly_error_message(exc)
        self.status.setText("操作失败。可点击『打开日志目录』查看详细日志。")
        self._show_message(
            QMessageBox.Critical,
            "Telegram 操作失败",
            f"{friendly}\n\n错误类型：{type(exc).__name__}\n\n日志文件：\n{log_file_path()}",
        )
