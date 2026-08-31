#!/usr/bin/env python3
"""确定性分类 Svip 中的官方 PikPak 资源回复。

脚本只消费已经导出的结构化消息，不连接 Telegram，不修改消息状态。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit


SCHEMA_VERSION = 1
TARGET_DOMAIN = "mypikpak.com"
URL_RE = re.compile(
    r"(?:https?://|www\.)[^\s<>\"'，。；：！？【】（）《》「」『』]+",
    re.IGNORECASE,
)


class InputError(ValueError):
    """输入或私人配置不满足契约。"""


def _load_json_or_jsonl(path: Path) -> Any:
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
                raise InputError(f"第 {line_number} 行不是有效 JSON。") from exc
        if not rows:
            raise InputError("输入文件为空或不包含有效 JSON。")
        return rows


def _message_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        if payload.get("ok") is False:
            raise InputError("tgctl 返回失败，不能把错误响应当作消息处理。")
        data = payload.get("data", payload)
        if isinstance(data, list):
            rows = data
        elif isinstance(data, dict) and isinstance(data.get("items"), list):
            rows = data["items"]
        elif isinstance(payload.get("items"), list):
            rows = payload["items"]
        else:
            raise InputError("找不到消息数组；需要数组、data 数组或 data.items 数组。")
    else:
        raise InputError("输入顶层必须是 JSON 数组或对象。")

    if not all(isinstance(row, dict) for row in rows):
        raise InputError("消息数组中存在非对象记录。")
    return rows


def _load_chat_id(config_path: Path, source_name: str) -> int:
    payload = _load_json_or_jsonl(config_path)
    if not isinstance(payload, dict):
        raise InputError("私人来源配置必须是 JSON 对象。")
    sources = payload.get("sources")
    source = sources.get(source_name) if isinstance(sources, dict) else None
    if not isinstance(source, dict):
        raise InputError(f"私人来源配置中没有 sources.{source_name}。")
    value = source.get("chat_id")
    try:
        chat_id = int(value)
    except (TypeError, ValueError) as exc:
        raise InputError(f"sources.{source_name}.chat_id 不是有效整数。") from exc
    if chat_id >= 0:
        raise InputError("Svip chat_id 应为 Telegram 标记后的负数群组 ID。")
    return chat_id


def _iter_urls(message: dict[str, Any]) -> Iterable[str]:
    for key in ("text", "caption"):
        value = message.get(key)
        if not isinstance(value, str):
            continue
        for match in URL_RE.finditer(value):
            yield match.group(0).rstrip(".,;:!?)]}，。；：！？】）》」』")

    entities = message.get("entities")
    if isinstance(entities, list):
        for entity in entities:
            if not isinstance(entity, dict):
                continue
            value = entity.get("url")
            if isinstance(value, str) and value:
                yield value


def _canonical_pikpak_urls(message: dict[str, Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in _iter_urls(message):
        candidate = raw if "://" in raw else f"http://{raw}"
        try:
            parsed = urlsplit(candidate)
            hostname = (parsed.hostname or "").encode("idna").decode("ascii").lower().rstrip(".")
        except (UnicodeError, ValueError):
            continue
        if hostname != TARGET_DOMAIN and not hostname.endswith(f".{TARGET_DOMAIN}"):
            continue
        if parsed.scheme.lower() not in {"http", "https"}:
            continue
        normalized = raw.rstrip(".,;:!?)]}")
        key = normalized.casefold()
        if key not in seen:
            result.append(normalized)
            seen.add(key)
    return result


def _is_photo(message: dict[str, Any]) -> bool:
    media = message.get("media")
    return isinstance(media, dict) and media.get("media_type") == "photo"


def _sender(message: dict[str, Any]) -> dict[str, Any]:
    value = message.get("sender")
    return value if isinstance(value, dict) else {}


def _is_verified_moderator(sender: dict[str, Any], chat_id: int) -> tuple[bool, list[str]]:
    evidence: list[str] = []
    if sender.get("is_creator") is True:
        evidence.append("telegram_verified_current_owner")
    if sender.get("is_admin") is True:
        evidence.append("telegram_verified_current_admin")
    if sender.get("anonymous_admin") is True:
        evidence.append("telegram_verified_anonymous_admin")
    try:
        posted_as_current_chat = int(sender.get("posted_as_chat_id")) == chat_id
    except (TypeError, ValueError):
        posted_as_current_chat = False
    if posted_as_current_chat:
        evidence.append("telegram_verified_current_chat_send_as")
    return bool(evidence), evidence


def _classify(message: dict[str, Any], chat_id: int) -> tuple[str, list[str]]:
    sender = _sender(message)
    verified, evidence = _is_verified_moderator(sender, chat_id)
    if verified:
        return "verified_moderator", evidence

    if sender.get("sender_id") is not None:
        return "excluded_known_member", ["telegram_known_non_moderator_sender"]

    unknown_reason = sender.get("unknown_reason")
    has_reply = message.get("reply_to_message_id") is not None
    has_photo = _is_photo(message)

    if unknown_reason == "forwarded_message_without_actual_sender":
        return "needs_review", ["forwarded_message_without_actual_sender"]

    if unknown_reason == "telegram_sender_not_provided":
        if has_reply and has_photo:
            return "trusted_official_reply", [
                "telegram_omitted_sender",
                "reply_to_message_present",
                "photo_present",
            ]
        if has_reply or has_photo:
            partial = "reply_to_message_present" if has_reply else "photo_present"
            return "needs_review", ["telegram_omitted_sender", partial]
        return "excluded_insufficient_evidence", ["telegram_omitted_sender"]

    return "needs_review", [str(unknown_reason or "sender_evidence_unavailable")]


def classify_messages(rows: list[dict[str, Any]], chat_id: int) -> dict[str, Any]:
    groups = {
        "main": [],
        "review": [],
        "excluded": [],
    }
    counts = {
        "verified_moderator": 0,
        "trusted_official_reply": 0,
        "needs_review": 0,
        "excluded_known_member": 0,
        "excluded_insufficient_evidence": 0,
        "excluded_wrong_source": 0,
        "excluded_no_pikpak_url": 0,
        "invalid": 0,
    }

    for index, message in enumerate(rows):
        message_id = message.get("message_id")
        try:
            actual_chat_id = int(message.get("chat_id"))
        except (TypeError, ValueError):
            counts["invalid"] += 1
            continue
        if actual_chat_id != chat_id:
            counts["excluded_wrong_source"] += 1
            continue

        urls = _canonical_pikpak_urls(message)
        if not urls:
            counts["excluded_no_pikpak_url"] += 1
            continue

        classification, evidence = _classify(message, chat_id)
        counts[classification] += 1
        record = {
            "message_id": message_id,
            "date": message.get("date"),
            "pikpak_urls": urls,
            "classification": classification,
            "evidence": evidence,
            "input_index": index,
        }
        if classification in {"verified_moderator", "trusted_official_reply"}:
            groups["main"].append(record)
        elif classification == "needs_review":
            groups["review"].append(record)
        else:
            groups["excluded"].append(record)

    return {
        "schema_version": SCHEMA_VERSION,
        "source": {"name": "svip", "chat_id": str(chat_id)},
        "policy": {
            "verified_identity": "Telegram 可验证的群主、管理员、匿名管理员或本群身份",
            "business_inference": "发送者被 Telegram 省略，同时具备回复关系和图片",
        },
        "summary": {
            "input_messages": len(rows),
            "pikpak_candidates": len(groups["main"]) + len(groups["review"]) + len(groups["excluded"]),
            "main": len(groups["main"]),
            "review": len(groups["review"]),
            "excluded": len(groups["excluded"]),
            "counts": counts,
        },
        "results": groups,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="分类 Svip 官方 PikPak 资源回复")
    parser.add_argument("input", type=Path, nargs="+", help="一个或多个 tgctl JSON/JSONL 文件")
    parser.add_argument("--config", type=Path, required=True, help="私人 Telegram 来源配置 JSON")
    parser.add_argument("--source", default="svip", help="配置中的来源名，默认 svip")
    parser.add_argument("--output", type=Path, help="可选输出文件；省略时仅写 stdout")
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        rows: list[dict[str, Any]] = []
        for input_path in args.input:
            rows.extend(_message_rows(_load_json_or_jsonl(input_path)))
        chat_id = _load_chat_id(args.config, args.source)
        result = classify_messages(rows, chat_id)
    except (OSError, InputError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

    text = json.dumps({"ok": True, "data": result}, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(
            json.dumps(
                {
                    "ok": True,
                    "output": str(args.output.resolve()),
                    "summary": result["summary"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
