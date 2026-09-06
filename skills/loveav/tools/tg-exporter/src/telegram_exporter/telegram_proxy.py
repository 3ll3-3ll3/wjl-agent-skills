from __future__ import annotations

import asyncio
import base64
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .ipc_client import DaemonIPCClient
from .models import AccountInfo, ForwardResult, GroupExportPlan, GroupInfo, SendResult, TelegramMessageInfo
from .rpc_models import (
    account_from_dict,
    forward_from_dict,
    group_from_dict,
    group_to_dict,
    message_from_dict,
    plan_to_dict,
    send_from_dict,
)
from .telegram_service import ApiCredentials


class DaemonTelegramProxy:
    """Client-side facade. It never opens TelegramClient or telegram.session."""

    def __init__(self, client_kind: str):
        self.client_kind = client_kind
        self.ipc = DaemonIPCClient(client_kind)
        self._lease_token: str | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None

    async def attach_gui(self, executable: str | None = None) -> None:
        if self.client_kind != "gui" or self._lease_token:
            return
        result = await self.ipc.request(
            "client.attach",
            {"executable": executable or (sys.executable if getattr(sys, "frozen", False) else None)},
        )
        self._lease_token = str(result["lease_token"])
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop(), name="tg-gui-heartbeat")

    async def _heartbeat_loop(self) -> None:
        try:
            while self._lease_token:
                await asyncio.sleep(15)
                token = self._lease_token
                if not token:
                    break
                try:
                    await self.ipc.request("client.heartbeat", {"lease_token": token})
                except Exception:
                    # Next normal GUI operation will ensure/restart daemon. Do
                    # not crash the Qt event loop because a heartbeat failed.
                    return
        except asyncio.CancelledError:
            raise

    async def configure_api(self, credentials: ApiCredentials) -> bool:
        result = await self.ipc.request(
            "auth.configure_api",
            {"api_id": credentials.api_id, "api_hash": credentials.api_hash},
            side_effect_after_send=True,
            retry_read_once=False,
        )
        return bool(result.get("authorized", False))

    async def auth_status(self) -> dict:
        return await self.ipc.request("auth.status")

    async def connect(self) -> bool:
        if self.client_kind == "gui":
            result = await self.auth_status()
            return bool(result.get("authorized", False))
        result = await self.ipc.request("telegram.status")
        return bool(result.get("authorized", False))

    async def send_code(self, phone: str) -> None:
        await self.ipc.request(
            "auth.send_code",
            {"phone": phone},
            side_effect_after_send=True,
            retry_read_once=False,
        )

    async def sign_in_code(self, phone: str, code: str) -> bool:
        result = await self.ipc.request(
            "auth.sign_in_code",
            {"phone": phone, "code": code},
            side_effect_after_send=True,
            retry_read_once=False,
        )
        return bool(result.get("complete", False))

    async def sign_in_password(self, password: str) -> None:
        await self.ipc.request(
            "auth.sign_in_password",
            {"password": password},
            side_effect_after_send=True,
            retry_read_once=False,
        )

    async def reset_session(self) -> int:
        result = await self.ipc.request(
            "auth.reset_session",
            side_effect_after_send=True,
            retry_read_once=False,
        )
        return int(result.get("removed_files", 0))

    async def account_info(self) -> AccountInfo:
        result = await self.ipc.request("telegram.status")
        account = result.get("account")
        if not isinstance(account, dict):
            return AccountInfo(user_id=0, display_name=None, username=None)
        return account_from_dict(account)

    async def status(self) -> dict:
        return await self.ipc.request("telegram.status")

    async def daemon_status(self) -> dict:
        return await self.ipc.request("system.status")

    async def list_groups(self) -> list[GroupInfo]:
        result = await self.ipc.request("chats.catalogue")
        return [group_from_dict(dict(item)) for item in result or []]

    async def search_messages(
        self,
        chat: str | int,
        *,
        contains: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 100,
        case_sensitive: bool = False,
    ) -> list[TelegramMessageInfo]:
        result = await self.ipc.request(
            "messages.search",
            {
                "chat": chat,
                "contains": contains,
                "since": since.isoformat() if since else None,
                "until": until.isoformat() if until else None,
                "limit": limit,
                "case_sensitive": case_sensitive,
            },
        )
        return [message_from_dict(dict(item)) for item in result or []]

    async def get_messages(self, chat: str | int, ids: Iterable[int]) -> list[TelegramMessageInfo]:
        result = await self.ipc.request("messages.get", {"chat": chat, "ids": [int(value) for value in ids]})
        return [message_from_dict(dict(item)) for item in result or []]

    async def forward_messages(
        self,
        source_chat: str | int,
        destination_chat: str | int,
        ids: Iterable[int],
        *,
        dry_run: bool = False,
        allow_large_batch: bool = False,
    ) -> ForwardResult:
        result = await self.ipc.request(
            "forward",
            {
                "source_chat": source_chat,
                "destination_chat": destination_chat,
                "ids": [int(value) for value in ids],
                "dry_run": dry_run,
                "allow_large_batch": allow_large_batch,
            },
            side_effect_after_send=not dry_run,
            retry_read_once=dry_run,
        )
        return forward_from_dict(dict(result))

    async def send_text_message(self, destination_chat: str | int, text: str, *, dry_run: bool = False) -> SendResult:
        result = await self.ipc.request(
            "send",
            {"destination_chat": destination_chat, "text": text, "dry_run": dry_run},
            side_effect_after_send=not dry_run,
            retry_read_once=dry_run,
        )
        return send_from_dict(dict(result))

    async def group_avatar_bytes(self, group: GroupInfo) -> bytes | None:
        result = await self.ipc.request("avatar.get", {"group": group_to_dict(group)})
        encoded = result.get("data_b64") if isinstance(result, dict) else None
        return base64.b64decode(encoded) if encoded else None

    async def start_export_batch(
        self,
        plans: list[tuple[GroupExportPlan, bool]],
        output_root: Path,
        *,
        export_moment: datetime,
    ) -> dict:
        return await self.ipc.request(
            "export.batch.start",
            {
                "plans": [plan_to_dict(plan, mark_read_after_export=mark_read) for plan, mark_read in plans],
                "output_root": str(output_root),
                "export_moment": export_moment.isoformat(),
            },
            side_effect_after_send=True,
            retry_read_once=False,
        )

    async def list_export_jobs(self) -> list[dict]:
        result = await self.ipc.request("export.jobs.list")
        return [dict(item) for item in result or []]

    async def export_job_status(self, job_id: str) -> dict:
        return dict(await self.ipc.request("export.job.status", {"job_id": job_id}))

    async def request_daemon_shutdown(self, *, after_export: bool = True) -> dict:
        return dict(
            await self.ipc.request(
                "system.shutdown",
                {"after_export": after_export},
                side_effect_after_send=True,
                retry_read_once=False,
            )
        )

    async def close(self) -> None:
        heartbeat = self._heartbeat_task
        self._heartbeat_task = None
        if heartbeat is not None:
            heartbeat.cancel()
            try:
                await heartbeat
            except asyncio.CancelledError:
                pass
        token = self._lease_token
        self._lease_token = None
        if token:
            try:
                await self.ipc.request("client.detach", {"lease_token": token})
            except Exception:
                pass
