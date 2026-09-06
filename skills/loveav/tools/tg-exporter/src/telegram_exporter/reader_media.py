from __future__ import annotations

import hashlib
import json
import logging
import mimetypes
import os
import re
import time
from pathlib import Path
from typing import Any

from .bridge_errors import (
    DOWNLOAD_CONFIRMATION_REQUIRED,
    DOWNLOAD_LIMIT_EXCEEDED,
    INVALID_ARGUMENT,
    INVALID_CURSOR,
    MESSAGE_NOT_FOUND,
    UNSUPPORTED_MESSAGE,
    TelegramBridgeError,
)
from .reader_service import PersonalAccountReader, _media_metadata

logger = logging.getLogger("telegram_exporter.reader_media")

NORMAL_FILE_LIMIT = 20
NORMAL_BYTE_LIMIT = 500 * 1024 * 1024
LARGE_FILE_LIMIT = 200
LARGE_BYTE_LIMIT = 5 * 1024 * 1024 * 1024
CONFIRMATION_TTL_SECONDS = 10 * 60
_INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def _safe_filename(name: str | None, *, chat_id: int, message_id: int, mime_type: str | None) -> str:
    raw = Path(str(name or "")).name.strip()
    if not raw:
        suffix = mimetypes.guess_extension(str(mime_type or ""), strict=False) or ""
        raw = f"telegram_{abs(int(chat_id))}_{int(message_id)}{suffix}"
    cleaned = _INVALID_FILENAME.sub("_", raw).rstrip(" .") or f"telegram_{abs(int(chat_id))}_{int(message_id)}"
    stem = Path(cleaned).stem.upper()
    if stem in _WINDOWS_RESERVED:
        cleaned = f"_{cleaned}"
    # Keep Windows path components manageable without trying to normalize the
    # user's output directory itself.
    if len(cleaned) > 180:
        suffix = Path(cleaned).suffix[:20]
        stem_text = Path(cleaned).stem[: max(1, 180 - len(suffix))]
        cleaned = stem_text + suffix
    return cleaned


def _available_path(directory: Path, filename: str) -> Path:
    candidate = directory / filename
    if not candidate.exists() and not candidate.with_name(candidate.name + ".part").exists():
        return candidate
    path = Path(filename)
    stem = path.stem or "telegram"
    suffix = path.suffix
    for index in range(2, 10000):
        candidate = directory / f"{stem}_{index}{suffix}"
        if not candidate.exists() and not candidate.with_name(candidate.name + ".part").exists():
            return candidate
    raise TelegramBridgeError(INVALID_ARGUMENT, "目标目录中同名文件过多，无法生成安全文件名。")


def _plan_hash(entries: list[dict[str, Any]]) -> str:
    payload = json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


async def media_download(
    reader: PersonalAccountReader,
    chat: str | int,
    ids: list[int],
    output: str,
    *,
    confirm: str | None = None,
    allow_large_download: bool = False,
) -> dict[str, Any]:
    requested = list(dict.fromkeys(int(value) for value in ids))
    if not requested:
        raise TelegramBridgeError(INVALID_ARGUMENT, "至少需要一个 message_id。")
    if len(requested) > LARGE_FILE_LIMIT:
        raise TelegramBridgeError(
            DOWNLOAD_LIMIT_EXCEEDED,
            f"单次媒体计划最多 {LARGE_FILE_LIMIT} 条消息。",
            {"requested_count": len(requested), "hard_file_limit": LARGE_FILE_LIMIT},
        )
    output_text = str(output or "").strip()
    if not output_text:
        raise TelegramBridgeError(INVALID_ARGUMENT, "media download 必须显式指定 --output 目录。")
    output_dir = Path(output_text).expanduser().resolve(strict=False)

    row, entity = await reader.resolve_dialog(chat)
    messages = await reader.client.get_messages(entity, ids=requested)
    by_id = {
        int(getattr(message, "id", 0) or 0): message
        for message in (messages or ())
        if message is not None and int(getattr(message, "id", 0) or 0) > 0
    }
    missing = [message_id for message_id in requested if message_id not in by_id]
    if missing:
        raise TelegramBridgeError(
            MESSAGE_NOT_FOUND,
            "部分消息不存在或当前账号无权访问。",
            {"missing_ids": missing},
        )

    entries: list[dict[str, Any]] = []
    download_messages: list[Any] = []
    known_bytes = 0
    unknown_size_count = 0
    for message_id in requested:
        message = by_id[message_id]
        metadata = _media_metadata(message)
        if metadata is None or metadata.media_type in {"webpage", "none"}:
            raise TelegramBridgeError(
                UNSUPPORTED_MESSAGE,
                "所选消息包含当前版本不可下载的媒体类型。",
                {"message_id": message_id, "media_type": metadata.media_type if metadata else None},
            )
        size = int(metadata.size) if isinstance(metadata.size, int) and metadata.size >= 0 else None
        if size is None:
            unknown_size_count += 1
        else:
            known_bytes += size
        filename = _safe_filename(
            metadata.filename,
            chat_id=row.chat_id,
            message_id=message_id,
            mime_type=metadata.mime_type,
        )
        entries.append(
            {
                "message_id": message_id,
                "media_type": metadata.media_type,
                "filename": filename,
                "mime_type": metadata.mime_type,
                "size": size,
            }
        )
        download_messages.append(message)

    file_limit = LARGE_FILE_LIMIT if allow_large_download else NORMAL_FILE_LIMIT
    byte_limit = LARGE_BYTE_LIMIT if allow_large_download else NORMAL_BYTE_LIMIT
    if len(entries) > file_limit or known_bytes > byte_limit:
        raise TelegramBridgeError(
            DOWNLOAD_LIMIT_EXCEEDED,
            "媒体下载计划超过当前允许范围。"
            + ("" if allow_large_download else "如确有需要，请显式加入 --allow-large-download。"),
            {
                "file_count": len(entries),
                "known_bytes": known_bytes,
                "unknown_size_count": unknown_size_count,
                "file_limit": file_limit,
                "byte_limit": byte_limit,
            },
        )

    query = {
        "chat_id": row.chat_id,
        "ids": requested,
        "output": str(output_dir),
        "allow_large_download": bool(allow_large_download),
    }
    plan_digest = _plan_hash(entries)
    if not confirm:
        token = reader.cursor.encode(
            "media.download",
            query,
            {
                "issued_at": int(time.time()),
                "plan_digest": plan_digest,
                "file_count": len(entries),
                "known_bytes": known_bytes,
                "unknown_size_count": unknown_size_count,
            },
        )
        raise TelegramBridgeError(
            DOWNLOAD_CONFIRMATION_REQUIRED,
            "媒体尚未下载。请核对数量和预计大小后，使用返回的 confirmation_token 再次执行。",
            {
                "file_count": len(entries),
                "estimated_bytes": known_bytes,
                "unknown_size_count": unknown_size_count,
                "confirmation_token": token,
                "allow_large_download": bool(allow_large_download),
                "files": entries,
            },
        )

    position = reader.cursor.decode(confirm, "media.download", query)
    if not position:
        raise TelegramBridgeError(INVALID_CURSOR, "media confirmation token 无效。")
    issued_at = int(position.get("issued_at", 0) or 0)
    if issued_at <= 0 or time.time() - issued_at > CONFIRMATION_TTL_SECONDS:
        raise TelegramBridgeError(INVALID_CURSOR, "media confirmation token 已过期，请重新生成下载计划。")
    if position.get("plan_digest") != plan_digest:
        raise TelegramBridgeError(INVALID_CURSOR, "媒体状态已变化，请重新生成下载计划。")

    output_dir.mkdir(parents=True, exist_ok=True)
    downloaded: list[dict[str, Any]] = []
    actual_total = 0
    for entry, message in zip(entries, download_messages, strict=True):
        final_path = _available_path(output_dir, str(entry["filename"]))
        part_path = final_path.with_name(final_path.name + ".part")
        try:
            if part_path.exists():
                part_path.unlink()
            result = await reader.client.download_media(message, file=str(part_path))
            if result is None or not part_path.exists():
                raise OSError("Telegram media download returned no file")
            actual_size = int(part_path.stat().st_size)
            actual_total += actual_size
            if actual_total > byte_limit:
                part_path.unlink(missing_ok=True)
                raise TelegramBridgeError(
                    DOWNLOAD_LIMIT_EXCEEDED,
                    "媒体实际下载大小超过当前 hard byte limit，已停止后续下载。",
                    {
                        "downloaded_count": len(downloaded),
                        "actual_bytes_before_rejected_file": actual_total - actual_size,
                        "byte_limit": byte_limit,
                    },
                )
            os.replace(part_path, final_path)
            downloaded.append(
                {
                    "message_id": int(entry["message_id"]),
                    "media_type": entry["media_type"],
                    "path": str(final_path),
                    "bytes": actual_size,
                }
            )
        except BaseException:
            try:
                part_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    logger.info(
        "Explicit Telegram media download completed chat_id=%s count=%s bytes=%s",
        row.chat_id,
        len(downloaded),
        actual_total,
    )
    return {
        "chat_id": row.chat_id,
        "downloaded_count": len(downloaded),
        "actual_bytes": actual_total,
        "output": str(output_dir),
        "files": downloaded,
    }
