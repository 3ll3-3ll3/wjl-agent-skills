from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any

from .bridge_errors import CURSOR_STALE, INVALID_CURSOR, TelegramBridgeError
from .ipc_identity import load_or_create_identity

CURSOR_VERSION = 1


def query_fingerprint(method: str, query: dict[str, Any]) -> str:
    payload = json.dumps(
        {"method": method, "query": query},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:24]


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode((value + padding).encode("ascii"))
    except Exception as exc:
        raise TelegramBridgeError(INVALID_CURSOR, "cursor 不是有效的 base64url。") from exc


@dataclass(frozen=True, slots=True)
class CursorCodec:
    secret: bytes

    @classmethod
    def from_local_identity(cls) -> "CursorCodec":
        return cls(load_or_create_identity().auth_secret)

    def encode(self, method: str, query: dict[str, Any], position: dict[str, Any]) -> str:
        payload = {
            "v": CURSOR_VERSION,
            "m": method,
            "q": query_fingerprint(method, query),
            "p": position,
        }
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        signature = hmac.new(self.secret, body, hashlib.sha256).digest()
        return f"{_b64encode(body)}.{_b64encode(signature)}"

    def decode(self, token: str | None, method: str, query: dict[str, Any]) -> dict[str, Any] | None:
        if not token:
            return None
        try:
            body_part, sig_part = token.split(".", 1)
        except ValueError as exc:
            raise TelegramBridgeError(INVALID_CURSOR, "cursor 格式无效。") from exc
        body = _b64decode(body_part)
        signature = _b64decode(sig_part)
        expected = hmac.new(self.secret, body, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            raise TelegramBridgeError(INVALID_CURSOR, "cursor 校验失败或已被修改。")
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TelegramBridgeError(INVALID_CURSOR, "cursor payload 无效。") from exc
        if not isinstance(payload, dict) or payload.get("v") != CURSOR_VERSION:
            raise TelegramBridgeError(INVALID_CURSOR, "cursor 版本不兼容。")
        if payload.get("m") != method or payload.get("q") != query_fingerprint(method, query):
            raise TelegramBridgeError(INVALID_CURSOR, "cursor 不属于当前查询。")
        position = payload.get("p")
        if not isinstance(position, dict):
            raise TelegramBridgeError(INVALID_CURSOR, "cursor position 无效。")
        return position

    @staticmethod
    def stale(message: str = "cursor 指向的 Telegram 实体已无法恢复。") -> TelegramBridgeError:
        return TelegramBridgeError(CURSOR_STALE, message)
