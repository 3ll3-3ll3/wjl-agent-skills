#!/usr/bin/env python3
"""把 LoveAV 的 Svip 分类结果转换为 Raindrop 兼容 CSV。"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo


FOLDER = "Svip PikPak链接消息"
RAINDROP_COLUMNS = ["folder", "url", "title", "note", "tags", "created"]
PASSWORD_RE = re.compile(
    r"(?:密码|提取码|访问码|口令|pwd|password)\s*[:：=]?\s*([A-Za-z0-9_-]{1,64})",
    re.IGNORECASE,
)
URL_RE = re.compile(r"https?://[^\s<>\"'`]+", re.IGNORECASE)


class ExportError(ValueError):
    """输入不满足 Svip Raindrop 导出契约。"""


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _main_records(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise ExportError("分类结果顶层必须是 JSON 对象。")
    if payload.get("ok") is False:
        raise ExportError("分类结果标记为失败，不能导出。")
    data = payload.get("data", payload)
    if not isinstance(data, dict):
        raise ExportError("分类结果缺少 data 对象。")
    results = data.get("results")
    main = results.get("main") if isinstance(results, dict) else None
    if not isinstance(main, list) or not all(isinstance(row, dict) for row in main):
        raise ExportError("分类结果缺少 results.main 数组。")
    return main


def _url_key(value: str) -> str:
    try:
        parsed = urlsplit(value.strip())
        port = parsed.port
    except ValueError as exc:
        raise ExportError(f"无效 PikPak URL：{value}") from exc
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ExportError(f"PikPak URL 不是 http/https：{value}")
    if host != "mypikpak.com" and not host.endswith(".mypikpak.com"):
        raise ExportError(f"PikPak URL 域名不受支持：{value}")
    netloc = host
    if port and not (
        parsed.scheme.lower() == "http" and port == 80
    ) and not (parsed.scheme.lower() == "https" and port == 443):
        netloc = f"{host}:{port}"
    path = parsed.path.rstrip("/") or "/"
    # URL 的 scheme/hostname 不区分大小写，但路径和 query 可能区分大小写；
    # 只规范化前两者，避免把两个不同分享地址错误合并。
    return urlunsplit((parsed.scheme.lower(), netloc, path, parsed.query, ""))


def _formula_safe(value: Any) -> str:
    text = str(value or "")
    stripped = text.lstrip()
    if stripped.startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def _meaningful_title(record: dict[str, Any], message_id: Any, date: str) -> str:
    text = str(record.get("message_text") or record.get("message_copy_text") or "")
    for raw_line in text.splitlines():
        line = URL_RE.sub(" ", raw_line)
        line = PASSWORD_RE.sub(" ", line)
        line = re.sub(r"\s+", " ", line).strip(" -—|｜：:")
        if len(line) >= 2:
            return line[:80]
    day = date[:10] if date else "未知日期"
    return f"Svip PikPak｜{day}｜消息 {message_id}"


def _note(record: dict[str, Any], resource: dict[str, Any]) -> str:
    message = str(record.get("message_copy_text") or record.get("message_text") or "").strip()
    password = str(resource.get("password") or "").strip()
    password_text = password if password else (
        "待确认" if record.get("password_status") == "ambiguous" else "无"
    )
    return "\n".join(
        [
            "【原消息】",
            message or "（原消息没有可见文字）",
            "",
            "【当前资源】",
            str(resource.get("url") or ""),
            f"密码：{password_text}",
            "",
            "【来源】",
            "群组：Svip",
            f"消息 ID：{record.get('message_id', '')}",
            f"消息时间：{record.get('date', '')}",
            "",
            "【判定】",
            "已识别为 Svip PikPak 链接；发送者身份不参与筛选",
        ]
    )


def _row(record: dict[str, Any], resource: dict[str, Any], index: int, total: int, folder: str) -> dict[str, str]:
    date = str(record.get("date") or "")
    title = _meaningful_title(record, record.get("message_id", ""), date)
    if total > 1:
        title = f"{title}｜{index}/{total}"
    tags = ["Svip", "PikPak"]
    if resource.get("password"):
        tags.append("有密码")
    elif record.get("password_status") == "ambiguous":
        tags.append("密码待确认")
    return {
        "folder": _formula_safe(folder),
        "url": str(resource.get("url") or ""),
        "title": _formula_safe(title),
        "note": _formula_safe(_note(record, resource)),
        "tags": _formula_safe(", ".join(tags)),
        "created": _formula_safe(date),
    }


def _load_raindrop_library(path: Path | None, folder: str) -> dict[str, dict[str, str]]:
    if path is None:
        return {}
    rows: dict[str, dict[str, str]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "url" not in {name.casefold() for name in reader.fieldnames}:
            raise ExportError("Raindrop 参考 CSV 缺少 url 列。")
        for raw in reader:
            normalized = {str(key).casefold(): str(value or "") for key, value in raw.items()}
            row_folder = normalized.get("folder", "").replace("\\", "/").strip(" /")
            if row_folder and row_folder != folder.replace("\\", "/").strip(" /"):
                continue
            value = normalized.get("url", "").strip()
            if not value:
                continue
            try:
                rows[_url_key(value)] = normalized
            except ExportError:
                continue
    return rows


def _password_from_note(note: str) -> str:
    match = PASSWORD_RE.search(note or "")
    return match.group(1) if match else ""


def _write_csv(path: Path, rows: list[dict[str, str]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def _default_data_root() -> Path:
    configured = os.environ.get("LOVEAV_DATA_DIR")
    if configured:
        return Path(configured)
    preferred = Path(r"E:\Desktop\codex项目\LoveAV-Data")
    return preferred if preferred.exists() else Path.cwd() / "LoveAV-Data"


def export(payload: Any, library: dict[str, dict[str, str]], folder: str) -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, int]]:
    candidates: OrderedDict[str, dict[str, Any]] = OrderedDict()
    review: list[dict[str, str]] = []
    batch_duplicates = 0
    password_conflicts = 0

    for record in _main_records(payload):
        resources = record.get("pikpak_resources")
        if not isinstance(resources, list):
            raise ExportError("主结果缺少 pikpak_resources 数组。")
        total = len(resources)
        for index, resource in enumerate(resources, start=1):
            if not isinstance(resource, dict):
                raise ExportError("pikpak_resources 中存在非对象记录。")
            key = _url_key(str(resource.get("url") or ""))
            current = {"record": record, "resource": resource, "index": index, "total": total}
            previous = candidates.get(key)
            if previous is None:
                candidates[key] = current
                continue
            batch_duplicates += 1
            old_password = str(previous["resource"].get("password") or "")
            new_password = str(resource.get("password") or "")
            if old_password and new_password and old_password.casefold() != new_password.casefold():
                password_conflicts += 1
                row = _row(record, resource, index, total, folder)
                row["review_reason"] = "同一批次相同 URL 出现不同密码"
                review.append(row)
            elif new_password and not old_password:
                candidates[key] = current

    output: list[dict[str, str]] = []
    historical = 0
    password_updates = 0
    for key, candidate in candidates.items():
        record = candidate["record"]
        resource = candidate["resource"]
        row = _row(record, resource, candidate["index"], candidate["total"], folder)
        existing = library.get(key)
        if existing is None:
            output.append(row)
            continue
        historical += 1
        old_password = _password_from_note(existing.get("note", ""))
        new_password = str(resource.get("password") or "")
        if new_password and not old_password:
            password_updates += 1
            row["review_reason"] = "Raindrop 已有 URL，待补充密码"
            review.append(row)
        elif new_password and old_password.casefold() != new_password.casefold():
            password_conflicts += 1
            row["review_reason"] = "Raindrop 已有 URL 的密码与本次不同"
            review.append(row)

    summary = {
        "candidate_urls": len(candidates),
        "new": len(output),
        "historical": historical,
        "batch_duplicates": batch_duplicates,
        "password_updates": password_updates,
        "password_conflicts": password_conflicts,
        "review": len(review),
    }
    return output, review, summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="生成 Svip PikPak 的 Raindrop 导入 CSV")
    parser.add_argument("input", type=Path, help="filter_svip_resource_replies.py 输出的 JSON")
    parser.add_argument("--raindrop-library", type=Path, help="可选的 Raindrop 官方导出 CSV，用于查重")
    parser.add_argument("--folder", default=FOLDER, help=f"Raindrop 收藏夹，默认 {FOLDER}")
    parser.add_argument("--output", type=Path, help="新增链接导入 CSV")
    parser.add_argument("--review-output", type=Path, help="密码补全或冲突复核 CSV")
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
        root = _default_data_root() / "svip"
        output = args.output or root / "outputs" / date / f"{date}_svip_pikpak_raindrop_import.csv"
        review_output = args.review_output or root / "update-review" / f"{date}_svip_pikpak_raindrop_update_review.csv"
        library = _load_raindrop_library(args.raindrop_library, args.folder)
        rows, review_rows, summary = export(_read_json(args.input), library, args.folder)
        _write_csv(output, rows, RAINDROP_COLUMNS)
        _write_csv(review_output, review_rows, [*RAINDROP_COLUMNS, "review_reason"])
    except (OSError, json.JSONDecodeError, ExportError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

    print(
        json.dumps(
            {
                "ok": True,
                "folder": args.folder,
                "output": str(output.resolve()),
                "review_output": str(review_output.resolve()),
                "library_used": str(args.raindrop_library.resolve()) if args.raindrop_library else None,
                "summary": summary,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
