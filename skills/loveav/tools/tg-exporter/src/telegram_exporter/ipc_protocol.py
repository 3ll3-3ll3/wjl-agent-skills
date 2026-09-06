from __future__ import annotations

import json
import uuid
from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any

from .bridge_errors import IPC_PROTOCOL_ERROR, IPC_RESPONSE_TOO_LARGE, TelegramBridgeError

PROTOCOL = "tgipc/1"
MAX_FRAME_BYTES = 8 * 1024 * 1024


def jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if is_dataclass(value):
        return jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(item) for item in value]
    return value


def encode_frame(payload: dict[str, Any]) -> bytes:
    try:
        data = json.dumps(jsonable(payload), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TelegramBridgeError(IPC_PROTOCOL_ERROR, "IPC payload 无法序列化为 JSON。") from exc
    if len(data) > MAX_FRAME_BYTES:
        raise TelegramBridgeError(
            IPC_RESPONSE_TOO_LARGE,
            "IPC 数据超过 8 MiB 限制，请缩小查询范围或 limit。",
            {"bytes": len(data), "limit": MAX_FRAME_BYTES},
        )
    return data


def decode_frame(data: bytes) -> dict[str, Any]:
    if len(data) > MAX_FRAME_BYTES:
        raise TelegramBridgeError(
            IPC_RESPONSE_TOO_LARGE,
            "IPC 数据超过 8 MiB 限制。",
            {"bytes": len(data), "limit": MAX_FRAME_BYTES},
        )
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TelegramBridgeError(IPC_PROTOCOL_ERROR, "IPC 请求不是有效 UTF-8 JSON。") from exc
    if not isinstance(payload, dict):
        raise TelegramBridgeError(IPC_PROTOCOL_ERROR, "IPC 顶层必须是 JSON object。")
    return payload


def make_request(*, client_kind: str, app_version: str, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "protocol": PROTOCOL,
        "request_id": uuid.uuid4().hex,
        "client": {"kind": client_kind, "app_version": app_version},
        "method": method,
        "params": params or {},
    }


def validate_request(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("protocol") != PROTOCOL:
        raise TelegramBridgeError(
            IPC_PROTOCOL_ERROR,
            "IPC protocol 版本不兼容。",
            {"expected": PROTOCOL, "received": payload.get("protocol")},
        )
    request_id = payload.get("request_id")
    method = payload.get("method")
    client = payload.get("client")
    params = payload.get("params", {})
    if not isinstance(request_id, str) or not request_id or len(request_id) > 128:
        raise TelegramBridgeError(IPC_PROTOCOL_ERROR, "IPC request_id 无效。")
    if not isinstance(method, str) or not method or len(method) > 128:
        raise TelegramBridgeError(IPC_PROTOCOL_ERROR, "IPC method 无效。")
    if not isinstance(client, dict) or client.get("kind") not in {"gui", "tgctl", "daemon-test"}:
        raise TelegramBridgeError(IPC_PROTOCOL_ERROR, "IPC client.kind 无效。")
    if not isinstance(params, dict):
        raise TelegramBridgeError(IPC_PROTOCOL_ERROR, "IPC params 必须是 JSON object。")
    return payload


def success_response(request_id: str, result: Any) -> dict[str, Any]:
    return {
        "protocol": PROTOCOL,
        "request_id": request_id,
        "ok": True,
        "result": jsonable(result),
    }


def error_response(request_id: str, code: str, message: str, details: Any = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        error["details"] = jsonable(details)
    return {
        "protocol": PROTOCOL,
        "request_id": request_id,
        "ok": False,
        "error": error,
    }
