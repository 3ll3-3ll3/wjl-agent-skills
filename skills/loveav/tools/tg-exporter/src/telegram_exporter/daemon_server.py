from __future__ import annotations

import base64
import logging
import secrets
import time
from datetime import datetime
from typing import Any

from telethon.errors import FloodWaitError

from . import __version__
from .bridge_errors import (
    AUTH_GUI_ONLY,
    CHAT_NOT_FOUND,
    EXPORT_IN_PROGRESS,
    FLOOD_WAIT,
    INVALID_ARGUMENT,
    NOT_AUTHORIZED,
    SESSION_BUSY,
    WRITE_FAILED,
    TelegramBridgeError,
)
from .credentials_store import load_saved_credentials, save_credentials
from .export_coordinator import ExportCoordinator
from .ipc_protocol import (
    PROTOCOL,
    decode_frame,
    encode_frame,
    error_response,
    success_response,
    validate_request,
)
from .models import GroupInfo
from .operation_coordinator import OperationCoordinator
from .paths import session_files, session_path
from .rpc_models import group_from_dict, group_to_dict
from .session_lock import SessionBusyError
from .telegram_service import ApiCredentials, TelegramService

logger = logging.getLogger("telegram_exporter.daemon_server")

DEFAULT_FORWARD_LIMIT = 20
LARGE_FORWARD_LIMIT = 200
SAFE_SESSION_LABEL = r"%APPDATA%\TelegramMultiChatExporter\telegram.session"
GUI_LEASE_SECONDS = 45.0


def _parse_iso(value: Any) -> datetime | None:
    if value in {None, ""}:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError as exc:
        raise TelegramBridgeError(INVALID_ARGUMENT, f"无法解析时间：{value}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.now().astimezone().tzinfo)
    return parsed


def _chat_dict(group: GroupInfo) -> dict[str, Any]:
    return {
        "chat_id": group.chat_id,
        "title": group.title,
        "username": group.username,
        "type": group.chat_type,
    }


class DaemonServer:
    def __init__(self) -> None:
        self.operations = OperationCoordinator()
        self.service: TelegramService | None = None
        self.authorized: bool | None = None
        self.exports = ExportCoordinator(self.operations, self._authorized_service)
        self.shutdown_event = __import__("asyncio").Event()
        self.active_requests = 0
        self.last_activity = time.monotonic()
        self.gui_leases: dict[str, float] = {}
        self.gui_executable: str | None = None
        self.shutdown_after_export = False

    async def _close_service(self) -> None:
        service = self.service
        self.service = None
        self.authorized = None
        if service is not None:
            await service.close()

    async def close(self) -> None:
        for task in list(self.exports.tasks.values()):
            if not task.done():
                task.cancel()
        await self._close_service()

    async def _ensure_service(self, *, require_authorized: bool) -> tuple[TelegramService, bool]:
        if self.service is None:
            credentials = load_saved_credentials()
            if credentials is None:
                raise TelegramBridgeError(
                    NOT_AUTHORIZED,
                    "未找到 Telegram API 配置。请先在 TG Exporter GUI 中完成设置和登录。",
                )
            service = TelegramService(credentials, session_path())
            try:
                authorized = await service.connect()
            except Exception:
                await service.close()
                raise
            self.service = service
            self.authorized = bool(authorized)
        authorized = bool(self.authorized)
        if require_authorized and not authorized:
            raise TelegramBridgeError(
                NOT_AUTHORIZED,
                "当前 Telegram Session 尚未登录。请先在 TG Exporter GUI 中完成登录。",
            )
        return self.service, authorized

    async def _authorized_service(self) -> TelegramService:
        service, _ = await self._ensure_service(require_authorized=True)
        return service

    def _require_gui(self, request: dict[str, Any]) -> None:
        if request["client"].get("kind") != "gui":
            raise TelegramBridgeError(AUTH_GUI_ONLY, "Telegram 登录/本地 Session 管理只能由 TG Exporter GUI 执行。")

    def _prune_leases(self) -> None:
        now = time.monotonic()
        for token in [token for token, expiry in self.gui_leases.items() if expiry <= now]:
            self.gui_leases.pop(token, None)

    @property
    def has_live_gui(self) -> bool:
        self._prune_leases()
        return bool(self.gui_leases)

    def status_snapshot(self) -> dict[str, Any]:
        self._prune_leases()
        active = self.exports.active_job
        state = "exporting" if active else ("connected" if self.service is not None and self.authorized else "idle")
        return {
            "state": state,
            "authorized": bool(self.authorized),
            "export_active": self.operations.export_active,
            "active_job": self.exports._safe_row(active) if active else None,
            "queued_reads": self.operations.queued_reads,
            "gui_clients": len(self.gui_leases),
            "shutdown_after_export": self.shutdown_after_export,
        }

    def can_idle_shutdown(self, idle_seconds: float) -> bool:
        self._prune_leases()
        if self.has_live_gui or self.exports.has_active_job or self.active_requests or self.operations.queued_reads:
            return False
        return (time.monotonic() - self.last_activity) >= idle_seconds

    async def request_shutdown(self, *, after_export: bool) -> dict[str, Any]:
        if self.exports.has_active_job:
            if after_export:
                self.shutdown_after_export = True
                return {"deferred": True, "reason": "export_in_progress"}
            raise TelegramBridgeError(EXPORT_IN_PROGRESS, "导出正在进行；不能直接结束后台。")
        self.shutdown_event.set()
        return {"deferred": False}

    async def handle_bytes(self, data: bytes) -> bytes:
        request_id = "unknown"
        counted = False
        try:
            request = validate_request(decode_frame(data))
            request_id = str(request["request_id"])
            self.active_requests += 1
            counted = True
            self.last_activity = time.monotonic()
            started = time.monotonic()
            result = await self.dispatch(request)
            logger.info(
                "IPC request completed request_id=%s method=%s client=%s duration_ms=%s",
                request_id,
                request.get("method"),
                request.get("client", {}).get("kind"),
                int((time.monotonic() - started) * 1000),
            )
            response = success_response(request_id, result)
        except TelegramBridgeError as exc:
            response = error_response(request_id, exc.code, exc.message, exc.details)
        except SessionBusyError as exc:
            response = error_response(request_id, SESSION_BUSY, str(exc))
        except FloodWaitError as exc:
            seconds = int(getattr(exc, "seconds", 0) or 0)
            response = error_response(
                request_id,
                FLOOD_WAIT,
                f"Telegram 要求等待 {seconds} 秒后再试。" if seconds else "Telegram 触发 Flood Wait。",
                {"retry_after_seconds": seconds},
            )
        except ValueError as exc:
            response = error_response(request_id, INVALID_ARGUMENT, str(exc))
        except Exception as exc:
            logger.error("Unhandled daemon RPC error", exc_info=(type(exc), exc, exc.__traceback__))
            response = error_response(request_id, "TELEGRAM_ERROR", f"Telegram 操作失败：{type(exc).__name__}")
        finally:
            if counted:
                self.active_requests = max(0, self.active_requests - 1)
            self.last_activity = time.monotonic()

        try:
            return encode_frame(response)
        except TelegramBridgeError as exc:
            return encode_frame(error_response(request_id, exc.code, exc.message, exc.details))

    async def dispatch(self, request: dict[str, Any]) -> Any:
        method = str(request["method"])
        params = dict(request.get("params") or {})
        client_kind = str(request["client"].get("kind"))

        # Pure local RPCs remain usable while Telegram export owns the operation queue.
        if method == "system.hello":
            return {
                "protocol": PROTOCOL,
                "daemon_app_version": __version__,
                "capabilities": [
                    "status",
                    "chats.list",
                    "messages.search",
                    "messages.get",
                    "forward",
                    "send",
                    "avatar.get",
                    "auth.gui",
                    "export.jobs",
                    "gui.lease",
                ],
                **self.status_snapshot(),
            }
        if method == "system.status":
            return self.status_snapshot()
        if method == "client.attach":
            if client_kind != "gui":
                raise TelegramBridgeError(INVALID_ARGUMENT, "只有 GUI 使用长期 client lease。")
            token = secrets.token_urlsafe(24)
            self.gui_leases[token] = time.monotonic() + GUI_LEASE_SECONDS
            executable = params.get("executable")
            if isinstance(executable, str) and executable:
                self.gui_executable = executable
            return {"lease_token": token, "expires_in_seconds": GUI_LEASE_SECONDS}
        if method == "client.heartbeat":
            token = str(params.get("lease_token") or "")
            if token not in self.gui_leases:
                raise TelegramBridgeError(INVALID_ARGUMENT, "GUI lease 已失效，请重新 attach。")
            self.gui_leases[token] = time.monotonic() + GUI_LEASE_SECONDS
            return {"expires_in_seconds": GUI_LEASE_SECONDS}
        if method == "client.detach":
            self.gui_leases.pop(str(params.get("lease_token") or ""), None)
            return {"detached": True}
        if method == "system.shutdown":
            self._require_gui(request)
            return await self.request_shutdown(after_export=bool(params.get("after_export", True)))
        if method == "export.jobs.list":
            return self.exports.list_jobs()
        if method in {"export.job.status", "export.job.result"}:
            job_id = str(params.get("job_id") or "")
            try:
                return self.exports.get_job(job_id)
            except KeyError as exc:
                raise TelegramBridgeError(CHAT_NOT_FOUND, f"找不到 export job：{job_id}") from exc

        # Login/session methods are GUI-only and serialized with all Telegram work.
        if method == "auth.configure_api":
            self._require_gui(request)
            credentials = ApiCredentials(
                api_id=int(params.get("api_id", 0)),
                api_hash=str(params.get("api_hash") or ""),
            )

            async def configure_api():
                save_credentials(credentials)
                await self._close_service()
                service, authorized = await self._ensure_service(require_authorized=False)
                return {"authorized": authorized, "proxy": service.proxy.safe_label if service.proxy else "direct"}

            return await self.operations.run_write(configure_api, dry_run=False)

        if method == "auth.status":
            self._require_gui(request)

            async def auth_status():
                if load_saved_credentials() is None:
                    return {"configured": False, "authorized": False}
                service, authorized = await self._ensure_service(require_authorized=False)
                return {
                    "configured": True,
                    "authorized": authorized,
                    "proxy": service.proxy.safe_label if service.proxy else "direct",
                }

            return await self.operations.run_read(auth_status)

        if method == "auth.send_code":
            self._require_gui(request)
            phone = str(params.get("phone") or "").strip()
            if not phone:
                raise TelegramBridgeError(INVALID_ARGUMENT, "手机号不能为空。")

            async def send_code():
                service, _ = await self._ensure_service(require_authorized=False)
                await service.send_code(phone)
                return {"sent": True}

            return await self.operations.run_write(send_code, dry_run=False)

        if method == "auth.sign_in_code":
            self._require_gui(request)
            phone = str(params.get("phone") or "").strip()
            code = str(params.get("code") or "").strip()
            if not phone or not code:
                raise TelegramBridgeError(INVALID_ARGUMENT, "手机号和验证码不能为空。")

            async def sign_code():
                service, _ = await self._ensure_service(require_authorized=False)
                complete = await service.sign_in_code(phone, code)
                self.authorized = bool(complete)
                return {"complete": complete, "needs_password": not complete}

            return await self.operations.run_write(sign_code, dry_run=False)

        if method == "auth.sign_in_password":
            self._require_gui(request)
            password = str(params.get("password") or "")
            if not password:
                raise TelegramBridgeError(INVALID_ARGUMENT, "2FA 密码不能为空。")

            async def sign_password():
                service, _ = await self._ensure_service(require_authorized=False)
                await service.sign_in_password(password)
                self.authorized = True
                return {"complete": True}

            return await self.operations.run_write(sign_password, dry_run=False)

        if method == "auth.reset_session":
            self._require_gui(request)

            async def reset_session():
                await self._close_service()
                removed = 0
                for path in session_files():
                    try:
                        if path.exists():
                            path.unlink()
                            removed += 1
                    except OSError:
                        logger.warning("Failed to remove Telegram session file %s", path.name, exc_info=True)
                        raise
                return {"removed_files": removed}

            return await self.operations.run_write(reset_session, dry_run=False)

        if method == "telegram.status":
            async def status():
                if load_saved_credentials() is None:
                    return {
                        "authorized": False,
                        "account": None,
                        "session": SAFE_SESSION_LABEL,
                        "proxy": "unknown",
                        "hint": "请先打开 TG Exporter 完成 Telegram 登录",
                    }
                service, authorized = await self._ensure_service(require_authorized=False)
                account = None
                if authorized:
                    account_info = await service.account_info()
                    account = {
                        "user_id": account_info.user_id,
                        "display_name": account_info.display_name,
                        "username": account_info.username,
                    }
                return {
                    "authorized": authorized,
                    "account": account,
                    "session": SAFE_SESSION_LABEL,
                    "proxy": service.proxy.safe_label if service.proxy else "direct",
                    "hint": None if authorized else "请先打开 TG Exporter 完成 Telegram 登录",
                }

            return await self.operations.run_read(status)

        if method == "chats.catalogue":
            async def catalogue():
                service = await self._authorized_service()
                return [group_to_dict(group) for group in await service.list_groups()]

            return await self.operations.run_read(catalogue)

        if method == "chats.list":
            limit = int(params.get("limit", 100))
            if limit <= 0:
                raise TelegramBridgeError(INVALID_ARGUMENT, "limit 必须大于 0。")

            async def chats_list():
                service = await self._authorized_service()
                groups = await service.list_groups()
                folder = params.get("folder")
                if folder:
                    key = str(folder).casefold()
                    known = {ref.title.casefold() for group in groups for ref in group.folders}
                    if key not in known:
                        raise TelegramBridgeError(CHAT_NOT_FOUND, f"找不到 Telegram 分组「{folder}」。")
                    groups = [g for g in groups if any(ref.title.casefold() == key for ref in g.folders)]
                search = params.get("search")
                if search:
                    needle = str(search).casefold()
                    groups = [
                        g for g in groups
                        if needle in g.title.casefold() or (g.username and needle in g.username.casefold())
                    ]
                return [_chat_dict(group) for group in groups[:limit]]

            return await self.operations.run_read(chats_list)

        if method == "messages.search":
            async def search_messages():
                service = await self._authorized_service()
                return await service.search_messages(
                    params.get("chat", ""),
                    contains=params.get("contains"),
                    since=_parse_iso(params.get("since")),
                    until=_parse_iso(params.get("until")),
                    limit=int(params.get("limit", 100)),
                    case_sensitive=bool(params.get("case_sensitive", False)),
                )

            return await self.operations.run_read(search_messages)

        if method == "messages.get":
            async def get_messages():
                service = await self._authorized_service()
                return await service.get_messages(params.get("chat", ""), params.get("ids", []))

            return await self.operations.run_read(get_messages)

        if method == "avatar.get":
            group_payload = params.get("group")
            if not isinstance(group_payload, dict):
                raise TelegramBridgeError(INVALID_ARGUMENT, "avatar.get 缺少 group。")
            group = group_from_dict(group_payload)

            async def avatar():
                service = await self._authorized_service()
                data = await service.group_avatar_bytes(group)
                return {"data_b64": base64.b64encode(data).decode("ascii") if data else None}

            return await self.operations.run_read(avatar)

        if method == "forward":
            ids = [int(value) for value in params.get("ids", [])]
            allow_large = bool(params.get("allow_large_batch", False))
            limit = LARGE_FORWARD_LIMIT if allow_large else DEFAULT_FORWARD_LIMIT
            if len(ids) > limit:
                raise TelegramBridgeError(
                    INVALID_ARGUMENT,
                    f"单次 forward 最多 {limit} 条。"
                    + ("" if allow_large else "如确有需要，请显式加入 --allow-large-batch。"),
                    {"requested_count": len(ids), "limit": limit},
                )
            dry_run = bool(params.get("dry_run", False))

            async def forward():
                service = await self._authorized_service()
                try:
                    return await service.forward_messages(
                        params.get("source_chat", ""),
                        params.get("destination_chat", ""),
                        ids,
                        dry_run=dry_run,
                    )
                except (TelegramBridgeError, FloodWaitError):
                    raise
                except Exception as exc:
                    raise TelegramBridgeError(WRITE_FAILED, f"Telegram 转发失败：{type(exc).__name__}") from exc

            return await self.operations.run_write(forward, dry_run=dry_run)

        if method == "send":
            dry_run = bool(params.get("dry_run", False))
            text = str(params.get("text") or "")

            async def send():
                service = await self._authorized_service()
                try:
                    return await service.send_text_message(
                        params.get("destination_chat", ""),
                        text,
                        dry_run=dry_run,
                    )
                except (TelegramBridgeError, FloodWaitError):
                    raise
                except Exception as exc:
                    raise TelegramBridgeError(WRITE_FAILED, f"Telegram 发送失败：{type(exc).__name__}") from exc

            return await self.operations.run_write(send, dry_run=dry_run)

        if method == "export.batch.start":
            self._require_gui(request)
            return await self.exports.start_batch(params)

        raise TelegramBridgeError(INVALID_ARGUMENT, f"未知 IPC method：{method}")
