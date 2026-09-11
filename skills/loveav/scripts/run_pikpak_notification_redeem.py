#!/usr/bin/env python3
"""LoveAV 第七功能：冻结未读、兑换 PikPak 资源、收藏并安全确认已读。"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import pikpak_resources
import plan_pikpak_notification_redeem as planner
import tg_exporter_adapter as adapter


SCHEMA_VERSION = 1
SOURCE_KEYS = ("pikpak_notice_updates", "pikpak_notice_share")
EXTRACTION_KEY = "pikpak_extraction_group"
COLLECTION_KEY = "pikpak_collection_group"


class RedeemError(RuntimeError):
    pass


def load_private_sources(path: Path) -> dict[str, dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RedeemError("无法读取私人 Telegram 来源配置。") from exc
    sources = payload.get("sources") if isinstance(payload, dict) else None
    if not isinstance(sources, dict):
        raise RedeemError("私人配置缺少 sources object。")

    required = (*SOURCE_KEYS, EXTRACTION_KEY, COLLECTION_KEY)
    result: dict[str, dict[str, Any]] = {}
    seen_chat_ids: set[int] = set()
    for key in required:
        row = sources.get(key)
        if not isinstance(row, dict):
            raise RedeemError(f"私人配置缺少 sources.{key}。")
        try:
            chat_id = int(row.get("chat_id"))
        except (TypeError, ValueError) as exc:
            raise RedeemError(f"sources.{key}.chat_id 不是有效整数。") from exc
        if chat_id >= 0:
            raise RedeemError(f"sources.{key}.chat_id 必须是 Telegram 标记后的负数群组 ID。")
        if chat_id in seen_chat_ids:
            raise RedeemError("第七功能的两个来源、提取群和收藏群必须是四个不同会话。")
        seen_chat_ids.add(chat_id)
        result[key] = {**row, "chat_id": chat_id}
    return result


def _capture_resources(captured: list[dict[str, Any]], keyword: str) -> tuple[list[dict[str, Any]], str | None]:
    by_url: dict[str, dict[str, Any]] = {}
    passwords: dict[str, set[str]] = defaultdict(set)
    for message in captured:
        for resource in pikpak_resources.canonical_resources(message):
            canonical = str(resource["canonical_url"])
            password = str(resource.get("password") or "").strip()
            if password:
                passwords[canonical].add(password.casefold())
            current = by_url.get(canonical)
            if current is None or (password and not current.get("password")):
                by_url[canonical] = {
                    **resource,
                    "title": pikpak_resources.resource_title(message, keyword),
                }

    conflict_urls = sorted(url for url, values in passwords.items() if len(values) > 1)
    if conflict_urls:
        return [], "password_conflict"
    return list(by_url.values()), None


def _collection_has_url(
    located: adapter.LocatedTgctl,
    collection_chat: str,
    canonical_url: str,
    *,
    timeout: float,
    runner: adapter.Runner,
) -> bool:
    path = urlsplit(canonical_url).path
    needle = path if len(path) >= 6 else canonical_url
    result = adapter.collect_pages(
        located,
        mode="search",
        query={"chat": collection_chat, "contains": needle},
        total_limit=100,
        page_size=100,
        timeout=timeout,
        runner=runner,
    )
    for message in result["items"]:
        for resource in pikpak_resources.canonical_resources(message):
            if str(resource["canonical_url"]).casefold() == canonical_url.casefold():
                return True
    return False


def _message_success_map(
    sources: dict[str, dict[str, Any]],
    plan: dict[str, Any],
    job_success: dict[str, bool],
) -> dict[str, dict[int, bool]]:
    required: dict[tuple[str, int], list[str]] = defaultdict(list)
    for job in plan["jobs"]:
        for ref in job["source_messages"]:
            required[(str(ref["source_key"]), int(ref["message_id"]))].append(str(job["keyword_key"]))
    review = {
        (str(row["source_key"]), int(row["message_id"]))
        for row in plan["review"]
        if row.get("message_id") is not None
    }

    result: dict[str, dict[int, bool]] = {}
    for source_key, snapshot in sources.items():
        status: dict[int, bool] = {}
        for row in snapshot["items"]:
            raw_id = row.get("message_id", row.get("id"))
            if raw_id is None:
                continue
            message_id = int(raw_id)
            keys = required.get((source_key, message_id), [])
            status[message_id] = bool(keys) and (source_key, message_id) not in review and all(
                job_success.get(key, False) for key in keys
            )
        result[source_key] = status
    return result


def _safe_ack_max(snapshot: dict[str, Any], status: dict[int, bool], *, allow_prefix: bool) -> int | None:
    lower = int(snapshot["lower"])
    upper = int(snapshot["upper"])
    loaded_count = int(snapshot.get("count", len(status)) or 0)
    reported_unread = int(snapshot.get("unread_count", loaded_count) or 0)
    if upper <= lower or not status:
        return None
    # Telegram 未读数与本轮实际可见消息数不一致时，范围内可能存在
    # 无法处理的隐藏/不可用项；连续前缀也不足以证明安全，故一律不 ack。
    if loaded_count != reported_unread or len(status) != loaded_count:
        return None
    if all(status.values()):
        return upper
    if not allow_prefix:
        return None
    acknowledged: int | None = None
    for message_id in sorted(status):
        if not status[message_id]:
            break
        acknowledged = message_id
    return acknowledged if acknowledged is not None and acknowledged > lower else None


def execute(
    *,
    located: adapter.LocatedTgctl,
    private_sources: dict[str, dict[str, Any]],
    confirmation: str | None,
    page_size: int = adapter.MAX_PAGE_SIZE,
    first_reply_timeout: float = 8.0,
    settle_seconds: float = 2.0,
    timeout: float = 120.0,
    allow_prefix_ack: bool = False,
    runner: adapter.Runner = adapter._default_runner,
) -> dict[str, Any]:
    real_run = confirmation == adapter.REDEEM_CONFIRMATION
    health = adapter.health_check(located, runner=runner, timeout=min(timeout, 30.0))
    if not health["compatible"] or not health["authorized"]:
        raise RedeemError("TG Exporter 未兼容或 Telegram 尚未登录。")
    adapter.require_capabilities(health, adapter.REDEEM_CAPABILITIES)
    if health["export_active"]:
        raise RedeemError("当前有手动导出任务，第七功能不能开始。")

    snapshots: dict[str, dict[str, Any]] = {}
    for source_key in SOURCE_KEYS:
        snapshots[source_key] = adapter.collect_unread_snapshot(
            located,
            chat=str(private_sources[source_key]["chat_id"]),
            page_size=page_size,
            timeout=timeout,
            runner=runner,
        )

    plan = planner.build_plan([(key, snapshots[key]["items"]) for key in SOURCE_KEYS])
    job_results: list[dict[str, Any]] = []
    job_success: dict[str, bool] = {}
    batch_urls: set[str] = set()
    extraction_chat = str(private_sources[EXTRACTION_KEY]["chat_id"])
    collection_chat = str(private_sources[COLLECTION_KEY]["chat_id"])
    fatal_error: dict[str, Any] | None = None

    for job in plan["jobs"]:
        key = str(job["keyword_key"])
        if not real_run:
            job_results.append({"keyword_key": key, "status": "planned", "resource_count": None})
            job_success[key] = False
            continue
        try:
            capture = adapter.send_and_capture(
                located,
                destination_chat=extraction_chat,
                text=str(job["send_text"]),
                confirmation=confirmation,
                first_reply_timeout=first_reply_timeout,
                settle_seconds=settle_seconds,
                url_domain=pikpak_resources.TARGET_DOMAIN,
                timeout=max(timeout, first_reply_timeout + settle_seconds + 10),
                runner=runner,
            )
            captured = capture.get("captured")
            if not isinstance(captured, list):
                raise RedeemError("send-capture 没有返回 captured 数组。")
            resources, conflict = _capture_resources(captured, str(job["keyword"]))
            if conflict or not resources:
                status = conflict or ("timeout" if capture.get("timed_out") else "no_pikpak_url")
                job_results.append({"keyword_key": key, "status": status, "resource_count": 0})
                job_success[key] = False
                continue

            saved = 0
            existing = 0
            for resource in resources:
                canonical = str(resource["canonical_url"])
                if canonical.casefold() in batch_urls or _collection_has_url(
                    located, collection_chat, canonical, timeout=timeout, runner=runner
                ):
                    existing += 1
                    batch_urls.add(canonical.casefold())
                    continue
                password = str(resource.get("password") or "").strip() or "未提供"
                message = f"{resource['title']}\n{resource['url']}\n密码：{password}"
                adapter.send_text(
                    located,
                    destination_chat=collection_chat,
                    text=message,
                    confirmation=confirmation,
                    timeout=timeout,
                    runner=runner,
                )
                batch_urls.add(canonical.casefold())
                saved += 1
            job_success[key] = saved + existing == len(resources)
            job_results.append({
                "keyword_key": key,
                "status": "success" if job_success[key] else "save_failed",
                "resource_count": len(resources),
                "saved": saved,
                "already_present": existing,
            })
        except adapter.AdapterError as exc:
            job_success[key] = False
            job_results.append({"keyword_key": key, "status": exc.code.casefold(), "resource_count": 0})
            if exc.code == "WRITE_OUTCOME_UNKNOWN":
                fatal_error = {"code": exc.code, "message": exc.message}
                break
        except RedeemError as exc:
            job_success[key] = False
            job_results.append({"keyword_key": key, "status": "invalid_response", "resource_count": 0})
            fatal_error = {"code": "INVALID_RESPONSE", "message": str(exc)}
            break

    status_by_source = _message_success_map(snapshots, plan, job_success)
    acknowledgements: dict[str, dict[str, Any]] = {}
    if real_run and fatal_error is None:
        for source_key in SOURCE_KEYS:
            snapshot = snapshots[source_key]
            max_id = _safe_ack_max(snapshot, status_by_source[source_key], allow_prefix=allow_prefix_ack)
            if max_id is None:
                acknowledgements[source_key] = {"confirmed": False, "reason": "incomplete_frozen_range"}
                continue
            acknowledgements[source_key] = adapter.mark_unread_snapshot_read(
                located,
                chat=str(private_sources[source_key]["chat_id"]),
                snapshot_token=str(snapshot["snapshot_token"]),
                max_id=max_id,
                confirmation=confirmation,
                timeout=timeout,
                runner=runner,
            )
    else:
        reason = "dry_run" if not real_run else "fatal_write_outcome_unknown"
        acknowledgements = {key: {"confirmed": False, "reason": reason} for key in SOURCE_KEYS}

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "pikpak_notification_redeem_execution",
        "dry_run": not real_run,
        "sources": {
            key: {
                "lower": snapshots[key]["lower"],
                "upper": snapshots[key]["upper"],
                "unread_count": snapshots[key]["unread_count"],
                "loaded_messages": snapshots[key]["count"],
                "pages": snapshots[key]["pages"],
            }
            for key in SOURCE_KEYS
        },
        "plan_summary": plan["summary"],
        "jobs": job_results,
        "summary": {
            "jobs_total": len(plan["jobs"]),
            "jobs_success": sum(1 for value in job_success.values() if value),
            "jobs_failed": sum(1 for value in job_success.values() if not value),
            "resources_saved": sum(int(row.get("saved", 0)) for row in job_results),
            "resources_already_present": sum(int(row.get("already_present", 0)) for row in job_results),
            "review_messages": len(plan["review"]),
        },
        "acknowledgements": acknowledgements,
        "fatal_error": fatal_error,
    }


def default_config_path() -> Path:
    for root in (Path.cwd(), *Path.cwd().parents):
        candidate = root / "LoveAV-Data" / "config" / "telegram-sources.json"
        if candidate.is_file():
            return candidate
    return Path.cwd() / "LoveAV-Data" / "config" / "telegram-sources.json"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LoveAV 第七功能执行器")
    parser.add_argument("--sources-config", type=Path, default=default_config_path())
    parser.add_argument("--tools-config", type=Path)
    parser.add_argument("--tgctl")
    parser.add_argument("--page-size", type=int, default=adapter.MAX_PAGE_SIZE)
    parser.add_argument("--first-reply-timeout", type=float, default=8.0)
    parser.add_argument("--settle-seconds", type=float, default=2.0)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--allow-contiguous-prefix-ack", action="store_true")
    parser.add_argument("--confirm", help=f"真实执行必须精确输入 {adapter.REDEEM_CONFIRMATION}")
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def _write_atomic(path: Path, payload: dict[str, Any]) -> None:
    path = path.expanduser().resolve(strict=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=path.parent, delete=False) as handle:
        handle.write(rendered)
        temporary = Path(handle.name)
    temporary.replace(path)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        located = adapter.locate_tgctl(args.tgctl, args.tools_config)
        payload = execute(
            located=located,
            private_sources=load_private_sources(args.sources_config),
            confirmation=args.confirm,
            page_size=args.page_size,
            first_reply_timeout=args.first_reply_timeout,
            settle_seconds=args.settle_seconds,
            timeout=args.timeout,
            allow_prefix_ack=args.allow_contiguous_prefix_ack,
        )
        if args.output:
            _write_atomic(args.output, payload)
        print(json.dumps({"ok": True, "data": payload}, ensure_ascii=False, separators=(",", ":")))
        return 0 if payload["fatal_error"] is None else 3
    except (adapter.AdapterError, RedeemError) as exc:
        code = exc.code if isinstance(exc, adapter.AdapterError) else "REDEEM_FAILED"
        print(json.dumps({"ok": False, "error": {"code": code, "message": str(exc)}}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
