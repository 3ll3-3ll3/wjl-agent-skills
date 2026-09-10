#!/usr/bin/env python3
"""把指定 Telegram 资源频道整理为本地主库和 Raindrop 导入 CSV。"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import sys
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from pikpak_resources import canonical_resources, resource_title


SCHEMA = "loveav.pikpak-channel-library.v2"
RAINDROP_COLUMNS = ["folder", "url", "title", "note", "tags", "created"]
LIBRARY_COLUMNS = [
    "url",
    "title",
    "note",
    "password",
    "password_status",
    "password_tag",
    "tags",
    "created",
    "last_posted_at",
    "edit_date",
    "message_id",
    "message_url",
    "source_message_ids",
]
HASHTAG_RE = re.compile(r"(?<!\S)#([^\s#]+)", re.UNICODE)
PIKPAK_VISIBLE_RE = re.compile(r"(?i)(?:https?://|www\.)[^\s<>\"'`]+")


class ArchiveError(ValueError):
    """输入或归档状态不满足确定性契约。"""


def _data_root() -> Path:
    configured = os.environ.get("LOVEAV_DATA_DIR")
    if configured:
        return Path(configured)
    preferred = Path(r"E:\Desktop\codex项目\LoveAV-Data")
    return preferred if preferred.exists() else Path.cwd() / "LoveAV-Data"


def _body(message: dict[str, Any]) -> str:
    parts = []
    for key in ("text", "caption"):
        value = message.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
    return "\n\n".join(parts)


def _reply_with_parent_context(parent: dict[str, Any], reply: dict[str, Any]) -> dict[str, Any]:
    """把评论中的资源链接与频道帖标题/说明组合成一条可归档记录。"""
    combined = dict(reply)
    parent_body = _body(parent)
    reply_body = _body(reply)
    combined["text"] = "\n\n".join(value for value in (parent_body, reply_body) if value)
    combined["caption"] = None
    combined["entities"] = [
        *list(parent.get("entities") or []),
        *list(reply.get("entities") or []),
    ]
    combined["discussion_parent_message_id"] = int(parent.get("message_id") or parent.get("id") or 0)
    combined["discussion_parent_message_url"] = _message_url(
        parent.get("source_chat_id", parent.get("chat_id")),
        parent.get("message_id") or parent.get("id"),
    )
    return combined


def _hashtags(text: str) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for match in HASHTAG_RE.finditer(text):
        tag = match.group(1).rstrip(".,;:!?，。；：！？、】）》」』").strip()
        key = tag.casefold()
        if tag and key not in seen:
            seen.add(key)
            result.append(tag)
    return result


def _message_url(chat_id: Any, message_id: Any) -> str:
    value = str(chat_id or "")
    if value.startswith("-100") and str(message_id).isdigit():
        return f"https://t.me/c/{value[4:]}/{message_id}"
    return ""


def _is_hidden(resource: dict[str, Any], body: str) -> bool:
    visible = {match.group(0).rstrip(".,;:!?)]}，。；：！？】）》」』") for match in PIKPAK_VISIBLE_RE.finditer(body)}
    return str(resource.get("url") or "") not in visible


def _source(message: dict[str, Any], resource: dict[str, Any], title: str) -> dict[str, Any]:
    body = _body(message)
    return {
        "message_id": int(message.get("message_id") or message.get("id") or 0),
        "message_url": _message_url(message.get("source_chat_id", message.get("chat_id")), message.get("message_id")),
        "created": str(message.get("date") or ""),
        "edit_date": str(message.get("edit_date") or ""),
        "title": title,
        "full_message": body,
        "password": str(resource.get("password") or ""),
        "tags": _hashtags(body),
        "hidden_link": _is_hidden(resource, body),
    }


def _date_key(source: dict[str, Any]) -> tuple[str, int]:
    return str(source.get("created") or ""), int(source.get("message_id") or 0)


def build_library(payload: Any, *, folder: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        raise ArchiveError("TG Exporter 输入不是成功的结构化结果。")
    if payload.get("complete") is not True:
        raise ArchiveError("TG Exporter 输入未标记为完整。")
    if payload.get("source_exhausted") is not True:
        raise ArchiveError("历史尚未读取到底，拒绝生成伪完整主库。")
    items = payload.get("items")
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        raise ArchiveError("TG Exporter 输入缺少 items 数组。")

    grouped: OrderedDict[str, dict[str, Any]] = OrderedDict()
    resource_messages = 0
    hidden_links = 0
    multi_link_messages = 0
    password_links = 0
    media_skipped = 0

    for message in items:
        resources = canonical_resources(message)
        if not resources:
            continue
        resource_messages += 1
        if len(resources) > 1:
            multi_link_messages += 1
        body = _body(message)
        fallback = f"PikPak 资源｜消息 {message.get('message_id', '')}"
        base_title = resource_title(message, fallback)
        for index, resource in enumerate(resources, start=1):
            canonical = str(resource.get("canonical_url") or "")
            if not canonical:
                continue
            title = base_title if len(resources) == 1 else f"{base_title}｜{index}/{len(resources)}"
            source = _source(message, resource, title)
            hidden_links += int(bool(source["hidden_link"]))
            password_links += int(bool(source["password"]))
            key = canonical.casefold()
            entry = grouped.setdefault(
                key,
                {
                    "schema": SCHEMA,
                    "folder": folder,
                    "canonical_url": canonical,
                    "url": str(resource.get("url") or canonical),
                    "sources": [],
                },
            )
            entry["sources"].append(source)
        if message.get("media") is not None:
            media_skipped += 1

    records: list[dict[str, Any]] = []
    duplicate_url_groups = 0
    password_conflicts = 0
    for entry in grouped.values():
        sources = sorted(entry.pop("sources"), key=_date_key)
        if len(sources) > 1:
            duplicate_url_groups += 1
        latest = sources[-1]
        passwords = list(dict.fromkeys(source["password"] for source in sources if source["password"]))
        if len(passwords) > 1:
            password_conflicts += 1
        password_status = "conflict" if len(passwords) > 1 else ("provided" if passwords else "not_provided")
        password_tag = "#有密码" if passwords else "#无密码"
        tags: list[str] = [password_tag.removeprefix("#")]
        seen_tags: set[str] = set()
        seen_tags.add(tags[0].casefold())
        for source in sources:
            for tag in source["tags"]:
                if tag.casefold() not in seen_tags:
                    seen_tags.add(tag.casefold())
                    tags.append(tag)
        record = {
            **entry,
            "title": latest["title"],
            "note": latest["full_message"],
            "password": passwords[0] if len(passwords) == 1 else "",
            "password_status": password_status,
            "password_tag": password_tag,
            "passwords": passwords,
            "tags": tags,
            "created": sources[0]["created"],
            "last_posted_at": latest["created"],
            "edit_date": latest["edit_date"],
            "message_id": latest["message_id"],
            "message_url": latest["message_url"],
            "source_message_ids": [source["message_id"] for source in sources],
            "source_messages": sources,
        }
        records.append(record)

    records.sort(key=lambda row: (str(row["created"]), int(row["message_id"])))
    message_ids = [int(item.get("message_id") or item.get("id") or 0) for item in items]
    summary = {
        "input_messages": len(items),
        "resource_messages": resource_messages,
        "unique_resources": len(records),
        "duplicate_url_groups": duplicate_url_groups,
        "multi_link_messages": multi_link_messages,
        "hidden_pikpak_links": hidden_links,
        "resources_with_password": password_links,
        "password_conflicts": password_conflicts,
        "media_ignored": media_skipped,
        "newest_message_id": max(message_ids, default=0),
        "oldest_message_id": min(message_ids, default=0),
        "comment_threads_scanned": int(payload.get("comment_threads_scanned", 0) or 0),
        "comment_messages": int(payload.get("comment_messages", 0) or 0),
    }
    return records, summary


def _formula_safe(value: Any) -> str:
    text = str(value or "")
    if text.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def _library_row(record: dict[str, Any]) -> dict[str, str]:
    return {
        "url": record["url"],
        "title": _formula_safe(record["title"]),
        "note": _formula_safe(record["note"]),
        "password": _formula_safe(record["password"]),
        "password_status": record["password_status"],
        "password_tag": record["password_tag"],
        "tags": _formula_safe(", ".join(record["tags"])),
        "created": record["created"],
        "last_posted_at": record["last_posted_at"],
        "edit_date": record["edit_date"],
        "message_id": str(record["message_id"]),
        "message_url": record["message_url"],
        "source_message_ids": "|".join(str(value) for value in record["source_message_ids"]),
    }


def _remove_current_url_once(message: str, record: dict[str, Any]) -> str:
    """只移除当前书签 URL 的第一次出现，其余正文保持原顺序。"""
    result = message
    candidates = list(
        dict.fromkeys(
            value
            for value in (str(record.get("url") or ""), str(record.get("canonical_url") or ""))
            if value
        )
    )
    for candidate in candidates:
        index = result.find(candidate)
        if index >= 0:
            result = result[:index] + result[index + len(candidate) :]
            break
    return result.strip()


def _raindrop_note(record: dict[str, Any]) -> str:
    remainder = _remove_current_url_once(str(record["note"]), record)
    sources = "、".join(str(value) for value in record["source_message_ids"])
    lines = [str(record["url"]), str(record["password_tag"])]
    if record["password_status"] == "provided":
        lines.append(f"密码：{record['password']}")
    elif record["password_status"] == "conflict":
        lines.append("密码：存在冲突，见本地主库")
    if remainder:
        lines.extend(["", remainder])
    lines.extend(["", "【Telegram 来源】", f"原消息：{record['message_url']}", f"消息 ID：{sources}"])
    return "\n".join(lines)


def _raindrop_row(record: dict[str, Any]) -> dict[str, str]:
    tags = ["层楼VIP", "PikPak", *record["tags"]]
    if record["password_status"] == "conflict":
        tags.append("密码冲突")
    return {
        "folder": _formula_safe(record["folder"]),
        "url": record["url"],
        "title": _formula_safe(record["title"]),
        "note": _formula_safe(_raindrop_note(record)),
        "tags": _formula_safe(", ".join(dict.fromkeys(tags))),
        "created": record["created"],
    }


def _json_bytes(value: Any, *, jsonl: bool = False) -> bytes:
    if jsonl:
        text = "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in value)
    else:
        text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    return text.encode("utf-8")


def _csv_bytes(rows: list[dict[str, str]], columns: list[str]) -> bytes:
    import io

    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
    return b"\xef\xbb\xbf" + buffer.getvalue().encode("utf-8")


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.is_file():
        return records
    for line_number, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not raw.strip():
            continue
        value = json.loads(raw)
        if not isinstance(value, dict) or not value.get("canonical_url"):
            raise ArchiveError(f"旧主库第 {line_number} 行缺少 canonical_url。")
        records.append(value)
    return records


def _record_map(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        key = str(record.get("canonical_url") or "").casefold()
        if not key:
            raise ArchiveError("主库记录缺少 canonical_url。")
        if key in result:
            raise ArchiveError(f"主库存在重复 canonical_url：{record.get('canonical_url')}")
        result[key] = record
    return result


def _same_record(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return json.dumps(left, ensure_ascii=False, sort_keys=True, separators=(",", ":")) == json.dumps(
        right, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def _compare_records(
    previous: list[dict[str, Any]], current: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], int]:
    before = _record_map(previous)
    after = _record_map(current)
    added = [after[key] for key in after.keys() - before.keys()]
    removed = [before[key] for key in before.keys() - after.keys()]
    updated = [
        {"canonical_url": after[key]["canonical_url"], "before": before[key], "after": after[key]}
        for key in after.keys() & before.keys()
        if not _same_record(before[key], after[key])
    ]
    conflicts = [record for record in current if record.get("password_status") == "conflict"]
    unchanged = len(after.keys() & before.keys()) - len(updated)
    order = lambda row: str(row.get("created") or row.get("after", {}).get("created") or "")
    return sorted(added, key=order), sorted(updated, key=order), sorted(removed, key=order), conflicts, unchanged


def _new_run_dir(parent: Path, now: datetime) -> Path:
    base = parent / now.strftime("%Y-%m-%d") / now.strftime("%H%M%S")
    candidate = base
    suffix = 2
    while candidate.exists():
        candidate = base.with_name(f"{base.name}-{suffix}")
        suffix += 1
    candidate.mkdir(parents=True, exist_ok=False)
    return candidate


def _snapshot_current(root: Path, now: datetime, *, legacy: bool) -> Path:
    suffix = "-legacy-layout" if legacy else ""
    snapshot = root / "snapshots" / f"{now.strftime('%Y-%m-%d_%H%M%S')}{suffix}"
    counter = 2
    while snapshot.exists():
        snapshot = root / "snapshots" / f"{now.strftime('%Y-%m-%d_%H%M%S')}{suffix}-{counter}"
        counter += 1
    snapshot.mkdir(parents=True, exist_ok=False)
    sources = (
        [
            root / "library" / "resource-library.jsonl",
            root / "library" / "resource-library.csv",
            root / "raindrop" / "raindrop-full.csv",
            root / "manifest.json",
            root / "state" / "checkpoint.json",
        ]
        if legacy
        else [
            root / "current" / "resource-library.jsonl",
            root / "current" / "resource-library.csv",
            root / "current" / "raindrop-full.csv",
            root / "current" / "manifest.json",
            root / "state" / "checkpoint.json",
        ]
    )
    for path in sources:
        if path.is_file():
            shutil.copy2(path, snapshot / path.name)
    return snapshot


def _retire_legacy_layout(root: Path, snapshot: Path) -> None:
    legacy = snapshot / "original-layout"
    legacy.mkdir(parents=True, exist_ok=True)
    for name in ("library", "raindrop", "backups"):
        path = root / name
        if path.exists():
            shutil.move(str(path), str(legacy / name))
    manifest = root / "manifest.json"
    if manifest.exists():
        shutil.move(str(manifest), str(legacy / manifest.name))


def write_archive(records: list[dict[str, Any]], summary: dict[str, Any], root: Path) -> dict[str, Any]:
    current_dir = root / "current"
    state_dir = root / "state"
    jsonl_path = current_dir / "resource-library.jsonl"
    csv_path = current_dir / "resource-library.csv"
    raindrop_path = current_dir / "raindrop-full.csv"
    manifest_path = current_dir / "manifest.json"
    state_path = state_dir / "checkpoint.json"

    legacy_jsonl = root / "library" / "resource-library.jsonl"
    previous_path = jsonl_path if jsonl_path.is_file() else legacy_jsonl
    legacy_migration = previous_path == legacy_jsonl and legacy_jsonl.is_file()
    previous = _read_jsonl(previous_path)
    added, updated, removed, conflicts, unchanged = _compare_records(previous, records)
    changed = bool(added or updated or removed)

    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    completed_at = now.isoformat()
    snapshot: Path | None = None
    if previous and (changed or legacy_migration):
        snapshot = _snapshot_current(root, now, legacy=legacy_migration)

    update_dir = _new_run_dir(root / "updates", now)
    update_blobs = {
        update_dir / "added-resources.jsonl": _json_bytes(added, jsonl=True),
        update_dir / "updated-resources.jsonl": _json_bytes(updated, jsonl=True),
        update_dir / "removed-resources.jsonl": _json_bytes(removed, jsonl=True),
        update_dir / "conflicts.jsonl": _json_bytes(conflicts, jsonl=True),
        update_dir / "raindrop-added.csv": _csv_bytes([_raindrop_row(record) for record in added], RAINDROP_COLUMNS),
    }
    for path, data in update_blobs.items():
        _atomic_write(path, data)

    current_blobs = {
        jsonl_path: _json_bytes(records, jsonl=True),
        csv_path: _csv_bytes([_library_row(record) for record in records], LIBRARY_COLUMNS),
        raindrop_path: _csv_bytes([_raindrop_row(record) for record in records], RAINDROP_COLUMNS),
    }
    for path, data in current_blobs.items():
        _atomic_write(path, data)

    delta = {
        "previous_resources": len(previous),
        "current_resources": len(records),
        "added": len(added),
        "updated": len(updated),
        "removed": len(removed),
        "unchanged": unchanged,
        "conflicts": len(conflicts),
    }
    checkpoint = {
        "schema": SCHEMA,
        "completed_at": completed_at,
        "newest_message_id": summary["newest_message_id"],
        "oldest_message_id": summary["oldest_message_id"],
        "strategy": "full_rescan_with_incremental_outputs",
        "last_update_dir": str(update_dir.resolve()),
    }
    _atomic_write(state_path, _json_bytes(checkpoint))
    hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in [*current_blobs, state_path]}
    manifest = {
        "schema": SCHEMA,
        "completed_at": completed_at,
        "summary": summary,
        "delta": delta,
        "files": {path.name: str(path.resolve()) for path in [*current_blobs, state_path]},
        "sha256": hashes,
        "snapshot": str(snapshot.resolve()) if snapshot else None,
        "update_dir": str(update_dir.resolve()),
        "legacy_layout_migrated": legacy_migration,
        "raindrop_direction": "local_to_raindrop_only",
        "images_downloaded": False,
        "telegram_state_changed": False,
    }
    _atomic_write(manifest_path, _json_bytes(manifest))
    _atomic_write(update_dir / "report.json", _json_bytes(manifest))
    if legacy_migration and snapshot is not None:
        _retire_legacy_layout(root, snapshot)
    return manifest


def _read_payload(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _source_from_config(path: Path, key: str) -> tuple[str, str | None, bool]:
    payload = _read_payload(path)
    source = payload.get("sources", {}).get(key) if isinstance(payload, dict) else None
    if not isinstance(source, dict) or not source.get("chat_id"):
        raise ArchiveError(f"私人来源配置缺少 sources.{key}.chat_id。")
    return (
        str(source["chat_id"]),
        str(source.get("title") or "") or None,
        bool(source.get("include_comments", False)),
    )


def _fetch_live(
    chat: str,
    total_limit: int,
    *,
    include_comments: bool = False,
    tgctl: str | Path | None = None,
) -> dict[str, Any]:
    from tg_exporter_adapter import AdapterError, collect_pages, health_check, locate_tgctl, require_capabilities

    located = locate_tgctl(tgctl)
    health = health_check(located)
    if not health.get("authorized"):
        raise ArchiveError("Telegram 尚未登录。")
    history = collect_pages(located, mode="history", query={"chat": chat}, total_limit=total_limit)
    if not include_comments:
        return history

    try:
        require_capabilities(health, {"messages.replies"})
        parents = list(history.get("items") or [])
        combined = list(parents)
        comment_messages = 0
        comment_parents = [parent for parent in parents if int(parent.get("reply_count") or 0) > 0]
        for parent in comment_parents:
            parent_id = int(parent.get("message_id") or parent.get("id") or 0)
            if parent_id <= 0:
                continue
            replies = collect_pages(
                located,
                mode="replies",
                query={"chat": chat, "message_id": parent_id},
                total_limit=total_limit,
            )
            if replies.get("source_exhausted") is not True:
                raise ArchiveError(f"消息 {parent_id} 的评论尚未读取到底。")
            rows = list(replies.get("items") or [])
            comment_messages += len(rows)
            combined.extend(_reply_with_parent_context(parent, reply) for reply in rows)
    except AdapterError as exc:
        raise ArchiveError(f"评论读取失败：{exc.code}：{exc.message}") from exc
    history["items"] = combined
    history["count"] = len(combined)
    history["comment_threads_scanned"] = len(comment_parents)
    history["comment_messages"] = comment_messages
    history["comments_complete"] = True
    return history


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="生成 PikPak 资源频道本地主库与 Raindrop CSV")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path, help="TG Exporter 完整 history JSON")
    source.add_argument("--live", action="store_true", help="通过本机 tgctl 只读抓取完整历史")
    parser.add_argument("--chat", help="live 模式的 Telegram 稳定 chat_id")
    parser.add_argument("--source-key", default="cenglou_pikpak_vip", help="私人来源配置键")
    parser.add_argument("--config", type=Path, default=_data_root() / "config" / "telegram-sources.json")
    parser.add_argument("--folder", default="层楼PikPak资源社", help="Raindrop 收藏夹")
    parser.add_argument("--output-root", type=Path, default=_data_root() / "pikpak" / "cenglou-vip")
    parser.add_argument("--total-limit", type=int, default=500000, help="live 模式安全上限")
    parser.add_argument("--tgctl", help="显式指定支持评论读取的 tgctl")
    parser.add_argument(
        "--include-comments",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="同时读取每条频道帖的评论/回复；默认采用私人来源配置",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        expected_title = None
        include_comments = bool(args.include_comments)
        if args.live:
            chat = args.chat
            if not chat:
                chat, expected_title, configured_comments = _source_from_config(args.config, args.source_key)
                if args.include_comments is None:
                    include_comments = configured_comments
            payload = _fetch_live(
                chat,
                args.total_limit,
                include_comments=include_comments,
                tgctl=args.tgctl,
            )
        else:
            payload = _read_payload(args.input)
        records, summary = build_library(payload, folder=args.folder)
        manifest = write_archive(records, summary, args.output_root)
        result = {
            "ok": True,
            "expected_title": expected_title,
            "output_root": str(args.output_root.resolve()),
            "summary": summary,
            "files": manifest["files"],
            "sha256": manifest["sha256"],
            "delta": manifest["delta"],
            "snapshot": manifest["snapshot"],
            "update_dir": manifest["update_dir"],
            "legacy_layout_migrated": manifest["legacy_layout_migrated"],
            "comments_included": include_comments,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, json.JSONDecodeError, ArchiveError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
