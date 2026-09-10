#!/usr/bin/env python3
"""把频道评论中的 Bot 深链批量兑换成 PikPak 资源，并交给功能 8 建库。"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import archive_pikpak_channel as archive
import pikpak_resources
import tg_exporter_adapter as adapter


CONFIRMATION = "RUN_PIKPAK_CHANNEL_REDEEM"


class RedeemError(ValueError):
    pass


def _load_source(config: Path, key: str) -> dict[str, Any]:
    payload = json.loads(config.read_text(encoding="utf-8-sig"))
    source = payload.get("sources", {}).get(key) if isinstance(payload, dict) else None
    if not isinstance(source, dict) or not source.get("chat_id"):
        raise RedeemError(f"私人来源配置缺少 sources.{key}。")
    bot = str(source.get("resource_bot_username") or "").strip().lstrip("@").casefold()
    if not bot:
        raise RedeemError(f"私人来源配置缺少 sources.{key}.resource_bot_username。")
    return {**source, "resource_bot_username": bot}


def _start_link(button: Any, expected_bot: str) -> tuple[str, str] | None:
    if not isinstance(button, dict):
        return None
    value = button.get("url")
    if not isinstance(value, str) or not value:
        return None
    parsed = urlsplit(value)
    if (parsed.hostname or "").casefold().rstrip(".") not in {"t.me", "telegram.me"}:
        return None
    bot = parsed.path.strip("/").split("/", 1)[0].casefold()
    if bot != expected_bot:
        return None
    values = parse_qs(parsed.query, keep_blank_values=False).get("start") or []
    payload = str(values[0]).strip() if values else ""
    if not payload or len(payload) > 512:
        return None
    return bot, payload


def build_plan(items: list[dict[str, Any]], expected_bot: str) -> dict[str, Any]:
    parents = {
        int(item.get("message_id") or item.get("id") or 0): item
        for item in items
        if not item.get("discussion_parent_message_id")
    }
    jobs: dict[tuple[str, str], dict[str, Any]] = {}
    parents_with_start: set[int] = set()
    for item in items:
        parent_id = int(item.get("discussion_parent_message_id") or 0)
        if parent_id <= 0 or parent_id not in parents:
            continue
        for button in item.get("buttons") or []:
            parsed = _start_link(button, expected_bot)
            if parsed is None:
                continue
            parents_with_start.add(parent_id)
            job = jobs.setdefault(parsed, {"bot": parsed[0], "payload": parsed[1], "parent_ids": []})
            if parent_id not in job["parent_ids"]:
                job["parent_ids"].append(parent_id)
    ordered = sorted(jobs.values(), key=lambda row: min(row["parent_ids"]))
    return {
        "parents": parents,
        "jobs": ordered,
        "summary": {
            "channel_posts": len(parents),
            "posts_with_start_link": len(parents_with_start),
            "posts_without_start_link": len(parents) - len(parents_with_start),
            "unique_start_jobs": len(ordered),
        },
    }


def _job_key(job: dict[str, Any]) -> str:
    raw = f"{job['bot']}\0{job['payload']}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _load_progress(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"schema": "loveav.pikpak-channel-redeem-progress.v1", "completed": {}}
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict) or not isinstance(value.get("completed"), dict):
        raise RedeemError("兑换检查点格式无效。")
    return value


def _save_progress(path: Path, progress: dict[str, Any]) -> None:
    archive._atomic_write(path, archive._json_bytes(progress))


def execute(args: argparse.Namespace) -> dict[str, Any]:
    source = _load_source(args.config, args.source_key)
    chat = str(source["chat_id"])
    expected_bot = str(source["resource_bot_username"])
    history = archive._fetch_live(
        chat,
        args.total_limit,
        include_comments=True,
        tgctl=args.tgctl,
    )
    plan = build_plan(list(history.get("items") or []), expected_bot)
    dry_run = args.confirm != CONFIRMATION
    result: dict[str, Any] = {
        "ok": True,
        "dry_run": dry_run,
        **plan["summary"],
        "comment_messages": int(history.get("comment_messages", 0) or 0),
        "expected_bot": f"@{expected_bot}",
        "confirmation_required": CONFIRMATION if dry_run else None,
    }
    if dry_run:
        return result
    if not plan["jobs"]:
        raise RedeemError("没有发现可兑换的 Bot start 深链。")

    located = adapter.locate_tgctl(args.tgctl)
    health = adapter.health_check(located)
    adapter.require_capabilities(health, {"send.capture", "messages.replies"})
    progress_path = args.output_root / "state" / "redeem-progress.json"
    progress = _load_progress(progress_path)
    completed = progress["completed"]
    failures: list[dict[str, Any]] = []
    reused = 0

    for index, job in enumerate(plan["jobs"], start=1):
        key = _job_key(job)
        if key in completed:
            reused += 1
            continue
        try:
            capture = adapter.send_and_capture(
                located,
                destination_chat=f"@{job['bot']}",
                text=f"/start {job['payload']}",
                confirmation=adapter.REDEEM_CONFIRMATION,
                first_reply_timeout=args.first_reply_timeout,
                settle_seconds=args.settle_seconds,
                url_domain=pikpak_resources.TARGET_DOMAIN,
                timeout=max(args.timeout, args.first_reply_timeout + args.settle_seconds + 10),
            )
            captured = capture.get("captured")
            if not isinstance(captured, list) or not any(pikpak_resources.canonical_resources(row) for row in captured):
                failures.append({"job": index, "status": "no_pikpak_reply"})
                # 这通常意味着 Bot 改了返回链路、进入限流，或将资源放到第二个频道。
                # 不得在未理解失败原因时继续向整批 Bot 发送命令。
                break
            completed[key] = {
                "parent_ids": job["parent_ids"],
                "captured": captured,
                "sent_message_id": capture.get("sent_message_id"),
            }
            progress["updated_at"] = time.time()
            _save_progress(progress_path, progress)
            time.sleep(max(0.0, args.pause_seconds))
        except adapter.AdapterError as exc:
            failures.append({"job": index, "status": exc.code})
            if exc.code in {"WRITE_OUTCOME_UNKNOWN", "FLOOD_WAIT"}:
                break

    result.update({"completed_jobs": len(completed), "reused_jobs": reused, "failures": failures})
    expected_keys = {_job_key(job) for job in plan["jobs"]}
    if failures or not expected_keys.issubset(completed):
        result["ok"] = False
        result["archive_updated"] = False
        return result

    derived: list[dict[str, Any]] = []
    for job in plan["jobs"]:
        stored = completed[_job_key(job)]
        for parent_id in stored["parent_ids"]:
            parent = plan["parents"].get(int(parent_id))
            if parent is None:
                continue
            for captured in stored["captured"]:
                if pikpak_resources.canonical_resources(captured):
                    derived.append(archive._reply_with_parent_context(parent, captured))
    payload = {
        "ok": True,
        "complete": True,
        "source_exhausted": True,
        "items": derived,
        "comment_threads_scanned": history.get("comment_threads_scanned", 0),
        "comment_messages": history.get("comment_messages", 0),
    }
    records, summary = archive.build_library(payload, folder=args.folder)
    manifest = archive.write_archive(records, summary, args.output_root)
    result.update(
        {
            "archive_updated": True,
            "summary": summary,
            "delta": manifest["delta"],
            "files": manifest["files"],
            "sha256": manifest["sha256"],
            "update_dir": manifest["update_dir"],
        }
    )
    return result


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description="兑换频道评论中的 Bot 深链并更新功能 8 主库")
    value.add_argument("--source-key", required=True)
    value.add_argument("--config", type=Path, default=archive._data_root() / "config" / "telegram-sources.json")
    value.add_argument("--tgctl")
    value.add_argument("--folder", required=True)
    value.add_argument("--output-root", type=Path, required=True)
    value.add_argument("--total-limit", type=int, default=500000)
    value.add_argument("--first-reply-timeout", type=float, default=8.0)
    value.add_argument("--settle-seconds", type=float, default=2.0)
    value.add_argument("--pause-seconds", type=float, default=65.0)
    value.add_argument("--timeout", type=float, default=120.0)
    value.add_argument("--confirm")
    return value


def main() -> int:
    try:
        print(json.dumps(execute(parser().parse_args()), ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, json.JSONDecodeError, adapter.AdapterError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
