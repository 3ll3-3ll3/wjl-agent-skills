#!/usr/bin/env python3
"""为 LoveAV 第七功能生成通知关键词去重计划。

脚本只读取已经冻结的未读消息 JSON/JSONL，不连接 Telegram，不发送消息，
不标记已读，也不把完整消息正文写入输出。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import OrderedDict
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
KEYWORD_LABEL_RE = re.compile(
    r"(?:回复|发送|提取|搜索)?\s*(?:关键词|口令|代码|提取码)\s*[:：=]\s*#?([^\s，。；;、（）()【】\[\]<>]{1,100})",
    re.IGNORECASE,
)
UPDATE_HASHTAG_RE = re.compile(
    r"(?:资源更新|新增资源|更新通知)[^\n\r#]{0,80}#([^\s，。；;、（）()【】\[\]<>]{1,100})",
    re.IGNORECASE,
)
HASHTAG_RE = re.compile(r"(?<![\w#])#([^\s，。；;、（）()【】\[\]<>]{1,100})")
TRAILING_PUNCTUATION = "，。；;、：:！!？?）)]}〉》」』\"'"


class PlanError(ValueError):
    """输入不满足第七功能计划契约。"""


def load_json_or_jsonl(path: Path) -> Any:
    text = path.read_text(encoding="utf-8-sig")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        rows: list[Any] = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise PlanError(f"{path} 第 {line_number} 行不是有效 JSON。") from exc
        if not rows:
            raise PlanError(f"{path} 不包含有效 JSON。")
        return rows


def message_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        if payload.get("ok") is False:
            raise PlanError("tgctl 返回失败，不能生成兑换计划。")
        data = payload.get("data", payload)
        if isinstance(data, list):
            rows = data
        elif isinstance(data, dict) and isinstance(data.get("items"), list):
            rows = data["items"]
        elif isinstance(payload.get("items"), list):
            rows = payload["items"]
        else:
            raise PlanError("找不到消息数组；需要数组、data 数组或 data.items 数组。")
    else:
        raise PlanError("输入顶层必须是 JSON 数组或对象。")

    if not all(isinstance(row, dict) for row in rows):
        raise PlanError("消息数组中存在非对象记录。")
    return rows


def message_text(row: dict[str, Any]) -> str:
    parts = [row.get("text"), row.get("caption")]
    return "\n".join(value for value in parts if isinstance(value, str) and value.strip())


def clean_keyword(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).strip()
    if value.startswith("#"):
        value = value[1:].strip()
    return value.rstrip(TRAILING_PUNCTUATION).strip()


def keyword_key(value: str) -> str:
    value = clean_keyword(value)
    value = " ".join(value.split())
    return value.casefold()


def extract_keywords(text: str) -> list[str]:
    candidates: list[str] = []
    for pattern in (KEYWORD_LABEL_RE, UPDATE_HASHTAG_RE):
        candidates.extend(match.group(1) for match in pattern.finditer(text))

    if not candidates:
        hashtags = [match.group(1) for match in HASHTAG_RE.finditer(text)]
        if len(hashtags) == 1:
            candidates.extend(hashtags)

    unique: OrderedDict[str, str] = OrderedDict()
    for candidate in candidates:
        cleaned = clean_keyword(candidate)
        key = keyword_key(cleaned)
        if key and key not in unique:
            unique[key] = cleaned
    return list(unique.values())


def parse_source_argument(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("--source 必须使用 稳定键=文件路径。")
    source_key, raw_path = value.split("=", 1)
    source_key = source_key.strip()
    if not source_key or not raw_path.strip():
        raise argparse.ArgumentTypeError("--source 的稳定键和文件路径都不能为空。")
    return source_key, Path(raw_path.strip())


def build_plan(sources: list[tuple[str, list[dict[str, Any]]]]) -> dict[str, Any]:
    jobs: OrderedDict[str, dict[str, Any]] = OrderedDict()
    review: list[dict[str, Any]] = []
    seen_messages: set[tuple[str, str]] = set()
    total_messages = 0
    duplicate_messages = 0
    total_keyword_occurrences = 0

    for source_key, rows in sources:
        for row in rows:
            total_messages += 1
            message_id = row.get("message_id", row.get("id"))
            chat_id = row.get("chat_id", row.get("source_chat_id"))
            if message_id is None:
                review.append({
                    "source_key": source_key,
                    "chat_id": chat_id,
                    "message_id": None,
                    "reason": "missing_message_id",
                })
                continue

            identity = (str(chat_id), str(message_id))
            if identity in seen_messages:
                duplicate_messages += 1
                continue
            seen_messages.add(identity)

            keywords = extract_keywords(message_text(row))
            if not keywords:
                review.append({
                    "source_key": source_key,
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "date": row.get("date"),
                    "reason": "no_unambiguous_keyword",
                })
                continue

            source_ref = {
                "source_key": source_key,
                "chat_id": chat_id,
                "message_id": message_id,
                "date": row.get("date"),
            }
            for keyword in keywords:
                total_keyword_occurrences += 1
                key = keyword_key(keyword)
                job = jobs.setdefault(
                    key,
                    {
                        "keyword_key": key,
                        "keyword": keyword,
                        "send_text": f"#{keyword}",
                        "source_messages": [],
                    },
                )
                if source_ref not in job["source_messages"]:
                    job["source_messages"].append(source_ref)

    unique_jobs = list(jobs.values())
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "pikpak_notification_redeem_plan",
        "summary": {
            "source_count": len(sources),
            "input_messages": total_messages,
            "duplicate_message_rows": duplicate_messages,
            "keyword_occurrences": total_keyword_occurrences,
            "unique_keywords": len(unique_jobs),
            "deduplicated_keyword_occurrences": total_keyword_occurrences - len(unique_jobs),
            "review_messages": len(review),
        },
        "jobs": unique_jobs,
        "review": review,
        "ack_policy": {
            "mode": "per_source_frozen_range_all_success_or_safe_contiguous_prefix",
            "ack_before_resources_saved": False,
            "snapshot_after_messages_excluded": True,
        },
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成 PikPak 通知关键词去重计划。")
    parser.add_argument(
        "--source",
        action="append",
        required=True,
        type=parse_source_argument,
        metavar="稳定键=文件路径",
        help="已经冻结的未读消息 JSON/JSONL；可重复两次。",
    )
    parser.add_argument("--output", type=Path, help="可选输出 JSON；省略时写到标准输出。")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        source_payloads = [
            (source_key, message_rows(load_json_or_jsonl(path)))
            for source_key, path in args.source
        ]
        plan = build_plan(source_payloads)
    except (OSError, PlanError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

    rendered = json.dumps(plan, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
