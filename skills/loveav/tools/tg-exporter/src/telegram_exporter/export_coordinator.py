from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable

from .exporter import export_group
from .models import ExportMode
from .operation_coordinator import OperationCoordinator
from .paths import daemon_job_state_path, state_path
from .read_state import mark_unread_snapshot_read
from .rpc_models import plan_from_dict
from .storage import LocalState, read_json, write_json_atomic
from .telegram_service import TelegramService
from .unread_snapshot import capture_current_unread_snapshot

logger = logging.getLogger("telegram_exporter.export_coordinator")

ServiceProvider = Callable[[], Awaitable[TelegramService]]


class ExportCoordinator:
    """Owns background GUI export jobs inside the daemon process.

    Only small metadata crosses IPC. Telegram message bodies remain inside the
    daemon/exporter path and are written directly to the user's final JSON.
    """

    def __init__(self, operations: OperationCoordinator, service_provider: ServiceProvider):
        self.operations = operations
        self.service_provider = service_provider
        self.jobs: dict[str, dict[str, Any]] = {}
        self.tasks: dict[str, asyncio.Task[None]] = {}
        self.exit_after_finish = False
        self._load_safe_metadata()

    def _load_safe_metadata(self) -> None:
        payload = read_json(daemon_job_state_path(), {})
        rows = payload.get("jobs", []) if isinstance(payload, dict) else []
        if not isinstance(rows, list):
            return
        for raw in rows[-10:]:
            if not isinstance(raw, dict) or not raw.get("job_id"):
                continue
            row = dict(raw)
            if row.get("state") in {"queued", "running"}:
                row["state"] = "interrupted"
                row["finished_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
                row["error"] = "daemon 上次退出时任务尚未完成；未伪报成功。"
            self.jobs[str(row["job_id"])] = row
        self._persist()

    def _safe_row(self, job: dict[str, Any]) -> dict[str, Any]:
        # Explicit allowlist: never persist GroupExportPlan or message text.
        keys = (
            "job_id",
            "state",
            "created_at",
            "started_at",
            "finished_at",
            "output_root",
            "total_groups",
            "completed_groups",
            "current_chat_id",
            "current_title",
            "current_message_count",
            "total_messages",
            "success_count",
            "failure_count",
            "marked_read_count",
            "read_failure_count",
            "results",
            "failures",
            "read_failures",
            "error",
        )
        return {key: job.get(key) for key in keys if key in job}

    def _persist(self) -> None:
        recent = sorted(
            (self._safe_row(job) for job in self.jobs.values()),
            key=lambda item: str(item.get("created_at", "")),
        )[-10:]
        write_json_atomic(daemon_job_state_path(), {"version": 1, "jobs": recent})

    @property
    def active_job(self) -> dict[str, Any] | None:
        for job in self.jobs.values():
            if job.get("state") in {"queued", "running"}:
                return job
        return None

    @property
    def has_active_job(self) -> bool:
        return self.active_job is not None

    def list_jobs(self) -> list[dict[str, Any]]:
        rows = [self._safe_row(job) for job in self.jobs.values()]
        rows.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
        return rows[:10]

    def get_job(self, job_id: str) -> dict[str, Any]:
        job = self.jobs.get(job_id)
        if job is None:
            raise KeyError(job_id)
        return self._safe_row(job)

    async def start_batch(self, params: dict[str, Any]) -> dict[str, Any]:
        raw_plans = params.get("plans")
        if not isinstance(raw_plans, list) or not raw_plans:
            raise ValueError("plans 必须至少包含一个导出计划。")

        parsed = [plan_from_dict(dict(item)) for item in raw_plans]
        output_root = Path(str(params.get("output_root") or ""))
        if not str(output_root):
            raise ValueError("output_root 不能为空。")
        raw_moment = params.get("export_moment")
        export_moment = datetime.fromisoformat(str(raw_moment)) if raw_moment else datetime.now().astimezone()

        await self.operations.reserve_export()
        job_id = uuid.uuid4().hex
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        job: dict[str, Any] = {
            "job_id": job_id,
            "state": "queued",
            "created_at": now,
            "output_root": str(output_root),
            "total_groups": len(parsed),
            "completed_groups": 0,
            "current_chat_id": None,
            "current_title": None,
            "current_message_count": 0,
            "total_messages": 0,
            "success_count": 0,
            "failure_count": 0,
            "marked_read_count": 0,
            "read_failure_count": 0,
            "results": [],
            "failures": [],
            "read_failures": [],
        }
        self.jobs[job_id] = job
        self._persist()
        try:
            task = asyncio.create_task(
                self._run_job(job, parsed, output_root, export_moment),
                name=f"tg-export-{job_id[:8]}",
            )
            self.tasks[job_id] = task
        except Exception:
            self.jobs.pop(job_id, None)
            await self.operations.cancel_export_reservation()
            raise
        return self._safe_row(job)

    async def _run_job(self, job: dict[str, Any], parsed, output_root: Path, export_moment: datetime) -> None:
        async def execute() -> None:
            service = await self.service_provider()
            state = LocalState(state_path())
            job["state"] = "running"
            job["started_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
            self._persist()

            for index, (plan, mark_read_after_export) in enumerate(parsed, start=1):
                job["current_chat_id"] = plan.group.chat_id
                job["current_title"] = plan.group.title
                job["current_message_count"] = 0
                self._persist()

                def progress(done: int, _total: int | None) -> None:
                    job["current_message_count"] = int(done)

                execution_plan = plan
                try:
                    # "Current unread" is defined at the moment this specific
                    # group actually starts executing, not when the catalogue
                    # was loaded or when the whole batch was submitted.  Export
                    # and optional read acknowledgement must share this exact
                    # frozen copy so messages arriving afterwards stay outside
                    # this run and remain unacknowledged by it.
                    if plan.mode is ExportMode.UNREAD:
                        snapshot_group = await capture_current_unread_snapshot(service.client, plan.group)
                        execution_plan = replace(plan, group=snapshot_group)

                    result = await export_group(
                        service.client,
                        execution_plan,
                        output_root,
                        progress=progress,
                        export_moment=export_moment,
                    )
                    if result.latest_message_id:
                        state.mark_success(
                            result.chat_id,
                            result.latest_message_id,
                            datetime.now().astimezone().isoformat(timespec="seconds"),
                        )

                    read_ack = "skipped"
                    if mark_read_after_export:
                        try:
                            acknowledged = await mark_unread_snapshot_read(service.client, execution_plan.group)
                            if acknowledged is not None:
                                read_ack = "success"
                                job["marked_read_count"] += 1
                            else:
                                read_ack = "nothing_to_ack"
                        except Exception as exc:
                            logger.error(
                                "Read acknowledgement failed after daemon export for chat_id=%s",
                                execution_plan.group.chat_id,
                                exc_info=(type(exc), exc, exc.__traceback__),
                            )
                            read_ack = "failed"
                            job["read_failure_count"] += 1
                            job["read_failures"].append(
                                {
                                    "chat_id": execution_plan.group.chat_id,
                                    "title": execution_plan.group.title,
                                    "error": type(exc).__name__,
                                }
                            )

                    job["results"].append(
                        {
                            "chat_id": result.chat_id,
                            "title": result.title,
                            "message_count": result.message_count,
                            "latest_message_id": result.latest_message_id,
                            "result_path": str(result.result_path),
                            "read_ack": read_ack,
                        }
                    )
                    job["success_count"] += 1
                    job["total_messages"] += result.message_count
                except Exception as exc:
                    logger.error(
                        "Daemon export failed for chat_id=%s",
                        plan.group.chat_id,
                        exc_info=(type(exc), exc, exc.__traceback__),
                    )
                    job["failure_count"] += 1
                    job["failures"].append(
                        {"chat_id": plan.group.chat_id, "title": plan.group.title, "error": type(exc).__name__}
                    )

                job["completed_groups"] = index
                self._persist()

            job["state"] = "completed" if not job["failure_count"] else "completed_with_failures"
            job["finished_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
            job["current_chat_id"] = None
            job["current_title"] = None
            job["current_message_count"] = 0
            self._persist()

        try:
            await self.operations.run_reserved_export(execute)
        except Exception as exc:
            logger.error("Daemon export job crashed", exc_info=(type(exc), exc, exc.__traceback__))
            job["state"] = "failed"
            job["error"] = type(exc).__name__
            job["finished_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
            self._persist()
        finally:
            self.tasks.pop(str(job["job_id"]), None)
