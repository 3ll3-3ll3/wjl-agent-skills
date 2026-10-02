#!/usr/bin/env python3
"""确定性提取指定 Telegram 来源中的 PikPak 链接消息。

脚本只消费已经导出的结构化消息，不连接 Telegram，不修改消息状态。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from pikpak_resources import PASSWORD_ANYWHERE_RE, URL_RE, canonical_resources


SCHEMA_VERSION = 3
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


def _load_source(config_path: Path, source_key: str) -> tuple[int, str]:
    payload = _load_json_or_jsonl(config_path)
    if not isinstance(payload, dict):
        raise InputError("私人来源配置必须是 JSON 对象。")
    sources = payload.get("sources")
    source = sources.get(source_key) if isinstance(sources, dict) else None
    if not isinstance(source, dict):
        raise InputError(f"私人来源配置中没有 sources.{source_key}。")
    value = source.get("chat_id")
    try:
        chat_id = int(value)
    except (TypeError, ValueError) as exc:
        raise InputError(f"sources.{source_key}.chat_id 不是有效整数。") from exc
    if chat_id >= 0:
        raise InputError("chat_id 应为 Telegram 标记后的负数群组 ID。")
    title = str(source.get("title") or source_key).strip() or source_key
    return chat_id, title


def _canonical_pikpak_resources(message: dict[str, Any]) -> list[dict[str, str | None]]:
    return [
        {"url": row["url"], "password": row["password"], "copy_text": row["copy_text"]}
        for row in canonical_resources(message)
    ]


def _message_content(message: dict[str, Any], resources: list[dict[str, str | None]]) -> tuple[str, str]:
    """返回原消息文字和可复制的完整文字。

    `message_text` 保留 Telegram 返回的 text/caption；`message_copy_text` 还会把
    富文本 entity 中存在、但可见文字没有展开的资源链接追加进来。
    """

    parts: list[str] = []
    for key in ("text", "caption"):
        value = message.get(key)
        if not isinstance(value, str):
            continue
        normalized = value.strip()
        if normalized and normalized not in parts:
            parts.append(normalized)
    message_text = "\n\n".join(parts)

    appended: list[str] = []
    folded_text = message_text.casefold()
    for resource in resources:
        url = str(resource["url"])
        if url.casefold() not in folded_text:
            appended.append(str(resource["copy_text"]))
    message_copy_text = "\n".join(part for part in (message_text, *appended) if part)
    return message_text, message_copy_text


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


def _identity_context(message: dict[str, Any], chat_id: int) -> tuple[str, list[str]]:
    """保留发送者上下文，但绝不再用它决定资源是否进入主结果。"""

    sender = _sender(message)
    verified, evidence = _is_verified_moderator(sender, chat_id)
    if verified:
        return "verified_moderator", evidence

    if sender.get("sender_id") is not None:
        return "known_sender", ["telegram_known_sender"]

    unknown_reason = sender.get("unknown_reason")
    has_reply = message.get("reply_to_message_id") is not None
    has_photo = _is_photo(message)

    if unknown_reason == "forwarded_message_without_actual_sender":
        return "forward_origin_only", ["forwarded_message_without_actual_sender"]

    if unknown_reason == "telegram_sender_not_provided":
        if has_reply and has_photo:
            return "sender_not_provided", [
                "telegram_omitted_sender",
                "reply_to_message_present",
                "photo_present",
            ]
        if has_reply or has_photo:
            partial = "reply_to_message_present" if has_reply else "photo_present"
            return "sender_not_provided", ["telegram_omitted_sender", partial]
        return "sender_not_provided", ["telegram_omitted_sender"]

    return "sender_evidence_unavailable", [str(unknown_reason or "sender_evidence_unavailable")]


def _password_status(message: dict[str, Any], resources: list[dict[str, str | None]]) -> str:
    bound = sum(1 for resource in resources if resource.get("password"))
    if bound == len(resources):
        return "bound"
    candidates: set[str] = set()
    for key in ("text", "caption"):
        value = message.get(key)
        if not isinstance(value, str):
            continue
        for match in PASSWORD_ANYWHERE_RE.finditer(URL_RE.sub(" ", value)):
            candidates.add(match.group(1).casefold())
    if bound or len(candidates) > 1 or (len(resources) > 1 and candidates):
        return "ambiguous"
    return "not_provided"


def classify_messages(rows: list[dict[str, Any]], chat_id: int, source_name: str = "Svip") -> dict[str, Any]:
    groups = {
        "main": [],
        "review": [],
        "excluded": [],
    }
    counts = {
        "accepted_pikpak_resource": 0,
        "password_ambiguous": 0,
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

        resources = _canonical_pikpak_resources(message)
        if not resources:
            counts["excluded_no_pikpak_url"] += 1
            continue

        identity_context, identity_evidence = _identity_context(message, chat_id)
        classification = "accepted_pikpak_resource"
        counts[classification] += 1
        password_status = _password_status(message, resources)
        if password_status == "ambiguous":
            counts["password_ambiguous"] += 1
        message_text, message_copy_text = _message_content(message, resources)
        record = {
            "message_id": message_id,
            "date": message.get("date"),
            "message_text": message_text,
            "message_copy_text": message_copy_text,
            "has_photo": _is_photo(message),
            "pikpak_urls": [resource["url"] for resource in resources],
            "pikpak_resources": resources,
            "classification": classification,
            "evidence": ["valid_pikpak_url_in_configured_svip_source"],
            "identity_context": identity_context,
            "identity_evidence": identity_evidence,
            "password_status": password_status,
            "source_name": source_name,
            "input_index": index,
        }
        groups["main"].append(record)

    return {
        "schema_version": SCHEMA_VERSION,
        "source": {"name": source_name, "chat_id": str(chat_id)},
        "policy": {
            "selection": "配置的 PikPak 消息来源中，所有合法 PikPak 链接默认进入主结果",
            "identity": "发送者身份只作上下文，不参与筛选",
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
    parser = argparse.ArgumentParser(description="提取指定来源的 PikPak 链接消息")
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
        chat_id, source_name = _load_source(args.config, args.source)
        result = classify_messages(rows, chat_id, source_name)
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
