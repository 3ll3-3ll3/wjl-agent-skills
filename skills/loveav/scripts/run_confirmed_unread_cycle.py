#!/usr/bin/env python3
"""处理已确认的 LoveAV Telegram 未读批次；Twitter/Whos.tv 不在其中，海角默认静默。"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit
from zoneinfo import ZoneInfo

import archive_pikpak_channel as channel_archive
import export_svip_raindrop_csv as pikpak_export
import filter_svip_resource_replies as pikpak_filter
import generate_missav_browser_script as missav_generator
import tg_exporter_adapter as adapter


MARK_READ_CONFIRMATION = "MARK_READ_AFTER_PROCESSING"
BADNEWS_RE = re.compile(r"https?://(?:www\.)?bad\.news/t/(\d+)(?:[/?#][^\s\"'<>]*)?", re.I)
HAIJIAO_RE = re.compile(
    r"https?://(?:www\.)?haijiaolove\.xyz/(hjjd|hjmz|hjyc|hjfn|hjsz|hjrq|hjhj)/(\d+)\.html(?:[/?#][^\s\"'<>]*)?",
    re.I,
)
URL_RE = re.compile(r"https?://[^\s\"'<>)]*", re.I)
FC2_RE = re.compile(r"(?:^|[^A-Za-z0-9])FC2(?:[ \t_-]*PPV)?[ \t_-]*(\d{4,10})(?=$|[^A-Za-z0-9])", re.I)
SEPARATED_RE = re.compile(r"(?:^|[^A-Za-z0-9])([A-Za-z]{2,8})[ \t_-]+(\d{2,5})(?=$|[^A-Za-z0-9])")
COMPACT_RE = re.compile(r"(?:^|[^A-Za-z0-9])([A-Z]{2,8})(\d{2,5})(?=$|[^A-Za-z0-9])")
TRUSTED_AV_HOSTS = {
    "missav.ai", "missav.ws", "123av.com", "avbase.net", "javdb.com", "javbus.com",
    "javlibrary.com", "supjav.com", "njav.tv", "jable.tv", "jav.guru",
}
NOISE_PREFIXES = {
    "MESSAGE", "MESSAGES", "USERPIC", "MEDIA", "VIDEO", "PHOTO", "AVATAR", "PAGINATION",
    "DETAILS", "STATUS", "TITLE", "BODY", "CLASS", "STYLE", "DATE", "HTML", "BUTTON",
    "INPUT", "IMAGE", "THUMB", "THUMBNAIL", "AV", "TOP", "BEST", "FUCK", "MOODYZ",
    "TAMEIKE", "ALL", "PDF", "TELEGRAM", "LOGO", "JOHREN", "IEOR", "PROBABILITY",
    "STATISTICS", "PYTHON", "OFFICE", "GITHUB", "SERIES", "WEIXIN", "RESULT", "RELATED",
    "THREAD", "XIUREN", "WXSYNC", "JAVA", "LARGE", "RJ", "NO", "PRO", "YOUPORN", "TV",
    "VIP", "HTTP", "HTTPS", "APP", "BOT",
}


class CycleError(ValueError):
    pass


def _data_root() -> Path:
    configured = os.environ.get("LOVEAV_DATA_DIR")
    if configured:
        return Path(configured)
    preferred = Path(r"E:\Desktop\codex项目\LoveAV-Data")
    return preferred if preferred.exists() else Path.cwd() / "LoveAV-Data"


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise CycleError(f"JSON 顶层必须是 object：{path}")
    return value


def _atomic_text(path: Path, text: str, *, bom: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(text, encoding="utf-8-sig" if bom else "utf-8", newline="\n")
    temporary.replace(path)


def _message_text(message: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("text", "caption"):
        value = message.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
    for entity in message.get("entities") or []:
        if isinstance(entity, dict):
            value = entity.get("url")
            if isinstance(value, str) and value.strip():
                parts.append(value.strip())
    for button in message.get("buttons") or []:
        if isinstance(button, dict):
            value = button.get("url")
            if isinstance(value, str) and value.strip():
                parts.append(value.strip())
    return "\n".join(parts)


def _normal_code(prefix: str, digits: str) -> str | None:
    prefix = prefix.upper()
    if prefix in NOISE_PREFIXES:
        return None
    values = missav_generator.normalize_codes([f"{prefix}-{digits}"])
    return values[0] if values else None


def _trusted_url_codes(value: str) -> list[str]:
    try:
        parsed = urlsplit(value.rstrip(".,;!?，。；！？"))
    except ValueError:
        return []
    host = (parsed.hostname or "").casefold().removeprefix("www.")
    if not any(host == domain or host.endswith(f".{domain}") for domain in TRUSTED_AV_HOSTS):
        return []
    path = unquote(parsed.path)
    values: list[str] = []
    for match in re.finditer(r"(?:^|[^a-z0-9])fc2(?:[\s_-]*ppv)?[\s_-]*(\d{4,10})(?=$|[^0-9])", path, re.I):
        values.append(f"FC2-PPV-{match.group(1)}")
    for match in re.finditer(r"(?:^|[^a-z])([a-z]{2,8})[\s_-]+(\d{2,5})(?=$|[^0-9])", path, re.I):
        code = _normal_code(match.group(1), match.group(2))
        if code:
            values.append(code)
    return values


def extract_missav_codes(messages: list[dict[str, Any]]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for message in messages:
        text = _message_text(message)
        candidates: list[str] = []
        for match in URL_RE.finditer(text):
            candidates.extend(_trusted_url_codes(match.group(0)))
        visible = URL_RE.sub(" ", text)
        visible = re.sub(r"@\s*[A-Za-z][A-Za-z0-9_]{1,31}", " ", visible)
        visible = re.sub(r"\b\d{1,5}\s*[×x]\s*\d{1,5}\b", " ", visible, flags=re.I)
        for match in FC2_RE.finditer(visible):
            candidates.append(f"FC2-PPV-{match.group(1)}")
        for match in SEPARATED_RE.finditer(visible):
            code = _normal_code(match.group(1), match.group(2))
            if code:
                candidates.append(code)
        for match in COMPACT_RE.finditer(visible):
            code = _normal_code(match.group(1), match.group(2))
            if code:
                candidates.append(code)
        for code in missav_generator.normalize_codes(candidates):
            key = code.replace("-", "").casefold()
            if key not in seen:
                seen.add(key)
                output.append(code)
    return output


def _library_keys(path: Path) -> set[str]:
    keys: set[str] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            value = str(row.get("loveav_canonical_code") or row.get("title") or "").strip()
            for code in missav_generator.normalize_codes([value]):
                keys.add(code.replace("-", "").casefold())
    return keys


def _write_missav_script(codes: list[str], library: Path, output: Path) -> dict[str, Any]:
    reference_blacklist_path = missav_generator.resolve_blacklist_path(
        library, None, missav_generator.REFERENCE_BLACKLIST_FILE
    )
    export_blacklist_path = missav_generator.resolve_blacklist_path(
        library, None, missav_generator.EXPORT_BLACKLIST_FILE
    )
    reference_blacklist = missav_generator.split_lines(reference_blacklist_path)
    export_blacklist = missav_generator.split_lines(export_blacklist_path)
    reference_tags, stats = missav_generator.extract_reference_tags(library, reference_blacklist)
    template = missav_generator.DEFAULT_TEMPLATE.read_text(encoding="utf-8-sig")
    script = missav_generator.apply_workspace_launcher(
        missav_generator.apply_runtime_optimization(
            missav_generator.inject_script(template, codes, reference_tags, export_blacklist)
        )
    )
    _atomic_text(output, script)
    return {
        "output": str(output.resolve()),
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "codes_injected": len(codes),
        **stats,
    }


def _source_lookup(config: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    sources = config.get("sources")
    if not isinstance(sources, dict):
        raise CycleError("telegram-sources.json 缺少 sources。")
    by_id = {str(value.get("chat_id")): {**value, "source_key": key} for key, value in sources.items() if isinstance(value, dict)}
    return sources, {chat_id: value["source_key"] for chat_id, value in by_id.items()}


def _category_sources(
    settings: dict[str, Any], config: dict[str, Any], category: str, *, include_keys: tuple[str, ...] = ()
) -> list[dict[str, Any]]:
    sources, by_id = _source_lookup(config)
    category_map = settings.get("group_export_categories") or {}
    ids = [str(chat_id) for chat_id, value in category_map.items() if value == category]
    for key in include_keys:
        source = sources.get(key)
        if isinstance(source, dict) and str(source.get("chat_id")) not in ids:
            ids.append(str(source.get("chat_id")))
    result: list[dict[str, Any]] = []
    for chat_id in ids:
        key = by_id.get(chat_id)
        if not key:
            raise CycleError(f"分类 {category} 的群 {chat_id} 尚未写入私人稳定来源配置。")
        result.append({**sources[key], "source_key": key})
    return result


def _collect(located: adapter.LocatedTgctl, source: dict[str, Any]) -> dict[str, Any]:
    return adapter.collect_unread_snapshot(located, chat=str(source["chat_id"]), page_size=500, timeout=180.0)


def _ack(located: adapter.LocatedTgctl, snapshot: dict[str, Any]) -> dict[str, Any]:
    if int(snapshot.get("unread_count", 0)) == 0:
        return {"confirmed": True, "reason": "zero_unread", "max_id": int(snapshot.get("upper", 0))}
    value = adapter.mark_unread_snapshot_read(
        located,
        chat=str(snapshot["chat"]),
        snapshot_token=str(snapshot["snapshot_token"]),
        max_id=int(snapshot["upper"]),
        confirmation=adapter.REDEEM_CONFIRMATION,
        timeout=60.0,
    )
    return {"confirmed": True, **value}


def _extract_links(messages: list[dict[str, Any]], kind: str) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    pattern = BADNEWS_RE if kind == "badnews" else HAIJIAO_RE
    for message in messages:
        for match in pattern.finditer(_message_text(message)):
            if kind == "badnews":
                value = f"https://bad.news/t/{match.group(1)}"
            else:
                value = f"https://www.haijiaolove.xyz/{match.group(1).casefold()}/{match.group(2)}.html"
            if value not in seen:
                seen.add(value)
                output.append(value)
    return output


def _merge_channel_record(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged_sources: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for source in [*list(existing.get("source_messages") or []), *list(incoming.get("source_messages") or [])]:
        key = str(source.get("message_url") or "") or f"{source.get('message_id')}\0{source.get('created')}"
        merged_sources[key] = source
    sources = sorted(
        merged_sources.values(),
        key=lambda row: (str(row.get("created") or ""), int(row.get("message_id") or 0)),
    )
    latest = sources[-1]
    passwords = list(dict.fromkeys(str(row.get("password") or "") for row in sources if row.get("password")))
    tags: list[str] = ["有密码" if passwords else "无密码"]
    seen_tags = {tags[0].casefold()}
    for source in sources:
        for tag in source.get("tags") or []:
            if str(tag).casefold() not in seen_tags:
                seen_tags.add(str(tag).casefold())
                tags.append(str(tag))
    result = {**existing, **incoming}
    result.update(
        {
            "title": latest.get("title") or incoming.get("title") or existing.get("title"),
            "note": latest.get("full_message") or "",
            "password": passwords[0] if len(passwords) == 1 else "",
            "password_status": "conflict" if len(passwords) > 1 else ("provided" if passwords else "not_provided"),
            "password_tag": "#有密码" if passwords else "#无密码",
            "passwords": passwords,
            "tags": tags,
            "created": sources[0].get("created") or "",
            "last_posted_at": latest.get("created") or "",
            "edit_date": latest.get("edit_date") or "",
            "message_id": latest.get("message_id") or 0,
            "message_url": latest.get("message_url") or "",
            "source_message_ids": [row.get("message_id") for row in sources],
            "source_messages": sources,
        }
    )
    return result


def _incremental_archive(snapshot: dict[str, Any], folder: str, output_root: Path) -> dict[str, Any]:
    payload = {
        "ok": True,
        "complete": True,
        "source_exhausted": True,
        "items": snapshot["items"],
    }
    batch, summary = channel_archive.build_library(payload, folder=folder)
    previous = channel_archive._read_jsonl(output_root / "current" / "resource-library.jsonl")
    records: OrderedDict[str, dict[str, Any]] = OrderedDict(
        (str(row.get("canonical_url") or row.get("url") or "").casefold(), row) for row in previous
    )
    for row in batch:
        key = str(row.get("canonical_url") or row.get("url") or "").casefold()
        records[key] = _merge_channel_record(records[key], row) if key in records else row
    merged = sorted(records.values(), key=lambda row: (str(row.get("created") or ""), int(row.get("message_id") or 0)))
    summary["incremental_unread_messages"] = int(snapshot["count"])
    summary["current_unique_resources"] = len(merged)
    manifest = channel_archive.write_archive(
        merged,
        summary,
        output_root,
        strategy="incremental_unread_merge",
    )
    return {
        "input_messages": snapshot["count"],
        "batch_resources": len(batch),
        "current_resources": len(merged),
        "delta": manifest["delta"],
        "update_dir": manifest["update_dir"],
        "sha256": manifest["sha256"],
    }


def execute(args: argparse.Namespace) -> dict[str, Any]:
    config = _load_json(args.config)
    settings = _load_json(args.settings)
    archive_index = _load_json(args.archive_index)
    located = adapter.locate_tgctl(args.tgctl, args.tools_config)
    health = adapter.health_check(located)
    adapter.require_capabilities(
        health,
        {"messages.current_unread_snapshot", "messages.mark_read_frozen_snapshot"},
    )
    if not health.get("authorized"):
        raise CycleError("Telegram 尚未登录。")

    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    day = now.strftime("%Y-%m-%d")
    stamp = now.strftime("%Y%m%d_%H%M%S")
    result: dict[str, Any] = {
        "ok": True,
        "completed_at": now.isoformat(),
        "twitter_skipped": True,
        "whostv_site_skipped": True,
        "missav": {},
        "badnews": {},
        "haijiao": {"status": "skipped_silent_by_default"},
        "pikpak_messages": {},
        "pikpak_archives": {},
        "errors": [],
    }

    missav_sources = _category_sources(settings, config, "av", include_keys=("missav_manual",))
    missav_snapshots: list[tuple[dict[str, Any], dict[str, Any]]] = []
    all_codes: list[str] = []
    seen_codes: set[str] = set()
    for source in missav_sources:
        try:
            snapshot = _collect(located, source)
            missav_snapshots.append((source, snapshot))
            codes = extract_missav_codes(snapshot["items"])
            for code in codes:
                key = code.replace("-", "").casefold()
                if key not in seen_codes:
                    seen_codes.add(key)
                    all_codes.append(code)
            result["missav"][source["source_key"]] = {
                "title": source.get("title"),
                "lower": snapshot["lower"],
                "upper": snapshot["upper"],
                "unread": snapshot["unread_count"],
                "loaded": snapshot["count"],
                "codes": len(codes),
            }
        except Exception as exc:
            result["errors"].append({"feature": "missav", "source": source["source_key"], "error": str(exc)})

    if not any(row["feature"] == "missav" for row in result["errors"]):
        historical = _library_keys(args.missav_library)
        new_codes = [code for code in all_codes if code.replace("-", "").casefold() not in historical]
        missav_output = args.data_root / "missav" / "results" / f"{day}_unread-cycle" / f"{stamp}_missav-browser-script.js"
        script_report = _write_missav_script(new_codes, args.missav_library, missav_output) if new_codes else None
        result["missav"]["summary"] = {
            "messages": sum(snapshot["count"] for _, snapshot in missav_snapshots),
            "unique_codes": len(all_codes),
            "historical": len(all_codes) - len(new_codes),
            "new_codes": len(new_codes),
            "script": script_report,
        }
        for source, snapshot in missav_snapshots:
            result["missav"][source["source_key"]]["ack"] = _ack(located, snapshot)

    link_features = [("badnews", "badnews")]
    if args.include_haijiao:
        link_features.append(("haijiao", "海角"))
        result["haijiao"] = {}
    for feature, category in link_features:
        sources = _category_sources(settings, config, category)
        if len(sources) != 1:
            result["errors"].append({"feature": feature, "error": f"分类 {category} 必须唯一匹配一个来源。"})
            continue
        source = sources[0]
        try:
            snapshot = _collect(located, source)
            links = _extract_links(snapshot["items"], feature)
            output = args.data_root / feature / "outputs" / day / f"{stamp}_{feature}_links.txt"
            _atomic_text(output, "\n".join(links) + ("\n" if links else ""), bom=True)
            result[feature] = {
                "title": source.get("title"),
                "lower": snapshot["lower"],
                "upper": snapshot["upper"],
                "unread": snapshot["unread_count"],
                "loaded": snapshot["count"],
                "links": len(links),
                "output": str(output.resolve()),
                "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                "ack": _ack(located, snapshot),
            }
        except Exception as exc:
            result["errors"].append({"feature": feature, "source": source["source_key"], "error": str(exc)})

    for source in _category_sources(settings, config, "pikpak消息"):
        try:
            snapshot = _collect(located, source)
            source_name = str(source.get("title") or source["source_key"])
            classified = pikpak_filter.classify_messages(snapshot["items"], int(source["chat_id"]), source_name)
            folder = str(source.get("raindrop_folder") or source_name)
            rows, review_rows, summary = pikpak_export.export({"ok": True, "data": classified}, {}, folder)
            root = args.data_root / "pikpak-messages" / source["source_key"] / "outputs" / day
            output = root / f"{stamp}_raindrop-import.csv"
            review_output = root / f"{stamp}_review.csv"
            pikpak_export._write_csv(output, rows, pikpak_export.RAINDROP_COLUMNS)
            pikpak_export._write_csv(review_output, review_rows, [*pikpak_export.RAINDROP_COLUMNS, "review_reason"])
            result["pikpak_messages"][source["source_key"]] = {
                "title": source_name,
                "lower": snapshot["lower"],
                "upper": snapshot["upper"],
                "unread": snapshot["unread_count"],
                "loaded": snapshot["count"],
                "classification": classified["summary"],
                "export": summary,
                "output": str(output.resolve()),
                "review_output": str(review_output.resolve()),
                "ack": _ack(located, snapshot),
            }
        except Exception as exc:
            result["errors"].append({"feature": "pikpak_messages", "source": source["source_key"], "error": str(exc)})

    indexed = archive_index.get("sources")
    if not isinstance(indexed, list):
        raise CycleError("pikpak-archive-sources.json 缺少 sources 数组。")
    config_sources = config["sources"]
    for entry in indexed:
        if not isinstance(entry, dict) or entry.get("enabled") is False:
            continue
        key = str(entry.get("source_key") or "")
        source = config_sources.get(key)
        if not isinstance(source, dict):
            result["errors"].append({"feature": "pikpak_archive", "source": key, "error": "私人来源缺失。"})
            continue
        try:
            snapshot = _collect(located, {**source, "source_key": key})
            archive_result: dict[str, Any]
            if snapshot["count"]:
                archive_result = _incremental_archive(
                    snapshot,
                    str(entry.get("raindrop_folder") or source.get("title") or key),
                    args.data_root / "pikpak" / str(entry["output_slug"]),
                )
            else:
                archive_result = {"input_messages": 0, "delta": {"added": 0, "updated": 0, "removed": 0}}
            result["pikpak_archives"][key] = {
                "title": source.get("title"),
                "lower": snapshot["lower"],
                "upper": snapshot["upper"],
                "unread": snapshot["unread_count"],
                "loaded": snapshot["count"],
                **archive_result,
                "ack": _ack(located, snapshot),
            }
        except Exception as exc:
            result["errors"].append({"feature": "pikpak_archive", "source": key, "error": str(exc)})

    result["ok"] = not result["errors"]
    return result


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    root = _data_root()
    value.add_argument("--data-root", type=Path, default=root)
    value.add_argument("--config", type=Path, default=root / "config" / "telegram-sources.json")
    value.add_argument("--settings", type=Path, default=Path(os.environ.get("APPDATA", "")) / "TelegramMultiChatExporter" / "settings.json")
    value.add_argument("--archive-index", type=Path, default=root / "config" / "pikpak-archive-sources.json")
    value.add_argument("--tools-config", type=Path, default=root / "config" / "tools.json")
    value.add_argument("--tgctl")
    value.add_argument("--missav-library", type=Path, default=root / "missav" / "library" / "missav-library.csv")
    value.add_argument("--include-haijiao", action="store_true", help="用户明确点名海角时才启用；默认静默跳过")
    value.add_argument("--report", type=Path, help="可选脱敏运行报告；默认写入私人数据目录 reports/unread-cycles")
    value.add_argument("--confirm-mark-read", required=True)
    return value


def main() -> int:
    args = parser().parse_args()
    if args.confirm_mark_read != MARK_READ_CONFIRMATION:
        print(json.dumps({"ok": False, "error": "缺少精确已读确认词。"}, ensure_ascii=False))
        return 2
    try:
        result = execute(args)
    except (OSError, ValueError, json.JSONDecodeError, adapter.AdapterError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    report_path = args.report
    if report_path is None:
        stamp = datetime.fromisoformat(result["completed_at"]).strftime("%Y%m%d_%H%M%S")
        report_path = args.data_root / "reports" / "unread-cycles" / f"{stamp}.json"
    result["report"] = str(report_path.resolve())
    _atomic_text(report_path, json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
