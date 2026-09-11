from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from typing import Any

from telethon.errors import FloodWaitError, RPCError

from .bridge_errors import (
    ALBUM_INCOMPLETE,
    CONTENT_PROTECTED,
    INVALID_ARGUMENT,
    MESSAGE_NOT_FOUND,
    SERVICE_MESSAGE,
    UNSUPPORTED_MESSAGE,
    WRITE_FAILED,
    WRITE_OUTCOME_UNKNOWN,
    TelegramBridgeError,
)
from .models import ForwardAlbum, ForwardFailure, ForwardResult, ForwardedMessage

logger = logging.getLogger("telegram_exporter.telegram_service")

ALBUM_SCAN_INITIAL_RADIUS = 16
ALBUM_SCAN_MAX_RADIUS = 128
TELEGRAM_FORWARD_BATCH_LIMIT = 100


def _media_name(message: Any) -> str | None:
    media = getattr(message, "media", None)
    return type(media).__name__ if media is not None else None


def forwardable_message_kind(message: Any) -> str | None:
    """Return the supported native-forward kind without reading/downloading media."""
    if message is None or getattr(message, "action", None) is not None:
        return None
    media_name = _media_name(message)
    if media_name == "MessageMediaPhoto":
        return "photo"
    if media_name in {None, "MessageMediaEmpty", "MessageMediaWebPage"} and bool(
        getattr(message, "message", None) or ""
    ):
        return "text"
    return None


def _failure(message_id: int, code: str, reason: str, grouped_id: int | None = None) -> ForwardFailure:
    return ForwardFailure(
        message_id=int(message_id),
        code=code,
        reason=reason,
        grouped_id=int(grouped_id) if grouped_id is not None else None,
    )


def _classify_failure(message: Any) -> tuple[str, str] | None:
    if message is None:
        return MESSAGE_NOT_FOUND, "消息不存在或当前账号无权访问。"
    if bool(getattr(message, "noforwards", False)):
        return CONTENT_PROTECTED, "该消息受 Telegram protected content 限制。"
    if getattr(message, "action", None) is not None:
        return SERVICE_MESSAGE, "service message 不支持转发。"
    if forwardable_message_kind(message) is None:
        return UNSUPPORTED_MESSAGE, "当前 forward 仅支持文字/网页预览与 Telegram 原生照片。"
    return None


async def _fetch_by_ids(client: Any, source_entity: Any, ids: Sequence[int]) -> dict[int, Any]:
    if not ids:
        return {}
    rows = await client.get_messages(source_entity, ids=list(ids))
    if rows is None:
        return {}
    if not isinstance(rows, (list, tuple)):
        rows = [rows]
    return {
        int(getattr(row, "id", 0) or 0): row
        for row in rows
        if row is not None and int(getattr(row, "id", 0) or 0) > 0
    }


async def _discover_album(client: Any, source_entity: Any, anchor: Any) -> tuple[list[Any], bool]:
    grouped_id = getattr(anchor, "grouped_id", None)
    if grouped_id is None:
        return [anchor], True
    grouped_id = int(grouped_id)
    anchor_id = int(getattr(anchor, "id", 0) or 0)
    radius = ALBUM_SCAN_INITIAL_RADIUS
    while True:
        lower = max(1, anchor_id - radius)
        upper = anchor_id + radius
        by_id = await _fetch_by_ids(client, source_entity, range(lower, upper + 1))
        album = sorted(
            (row for row in by_id.values() if getattr(row, "grouped_id", None) == grouped_id),
            key=lambda row: int(getattr(row, "id", 0) or 0),
        )
        if not album:
            return [anchor], False
        first_id = int(getattr(album[0], "id", 0) or 0)
        last_id = int(getattr(album[-1], "id", 0) or 0)
        touches_boundary = first_id <= lower or last_id >= upper
        if not touches_boundary:
            return album, True
        if radius >= ALBUM_SCAN_MAX_RADIUS:
            return album, False
        radius = min(ALBUM_SCAN_MAX_RADIUS, radius * 2)


def _normalize_forward_result(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [item for item in value if item is not None]
    return [value]


def _chunk_units(units: Sequence[tuple[int | None, tuple[int, ...]]]) -> list[list[int]]:
    chunks: list[list[int]] = []
    current: list[int] = []
    for _grouped_id, ids in units:
        if len(ids) > TELEGRAM_FORWARD_BATCH_LIMIT:
            raise TelegramBridgeError(
                ALBUM_INCOMPLETE,
                "单个相册超过 Telegram forward 批次安全上限，已拒绝拆散相册。",
                {"album_message_count": len(ids), "limit": TELEGRAM_FORWARD_BATCH_LIMIT},
            )
        if current and len(current) + len(ids) > TELEGRAM_FORWARD_BATCH_LIMIT:
            chunks.append(current)
            current = []
        current.extend(ids)
    if current:
        chunks.append(current)
    return chunks


async def forward_messages_native(
    service: Any,
    source_chat: str | int,
    destination_chat: str | int,
    ids: Iterable[int],
    *,
    dry_run: bool = False,
    max_messages: int = 20,
) -> ForwardResult:
    """Plan and execute Telegram-native forwarding without downloading media."""
    requested = tuple(dict.fromkeys(int(value) for value in ids))
    if not requested:
        raise TelegramBridgeError(INVALID_ARGUMENT, "至少需要一个 message_id。")
    if max_messages <= 0:
        raise TelegramBridgeError(INVALID_ARGUMENT, "forward 安全上限必须大于 0。")

    groups = await service.list_groups()
    source = await service.resolve_group(source_chat, groups)
    source_entity = await service.client.get_entity(source.chat_id)

    destination_raw = str(destination_chat).strip()
    if destination_raw.casefold() == "me":
        destination_entity = "me"
        destination_id: int | str = "me"
    else:
        destination = await service.resolve_group(destination_raw, groups)
        destination_entity = await service.client.get_entity(destination.chat_id)
        destination_id = destination.chat_id

    source_protected = bool(getattr(source_entity, "noforwards", False))
    initial_by_id = await _fetch_by_ids(service.client, source_entity, requested)
    failures: list[ForwardFailure] = []

    if source_protected:
        for message_id in requested:
            failures.append(
                _failure(
                    message_id,
                    CONTENT_PROTECTED,
                    "来源会话启用了 Telegram protected content / noforwards。",
                )
            )
        logger.info(
            "Telegram forward plan: requested=%s planned=0 photos=0 albums=0 excluded=%s protected=true",
            len(requested),
            len(failures),
        )
        return ForwardResult(
            source_chat_id=source.chat_id,
            destination_chat_id=destination_id,
            requested_ids=requested,
            successful_ids=(),
            failed_ids=tuple(item.message_id for item in failures),
            dry_run=dry_run,
            requested_count=len(requested),
            forwardable_count=0,
            photo_count=0,
            album_count=0,
            failures=tuple(failures),
        )

    # A unit is either one standalone message or a complete grouped_id album.
    units: list[tuple[int | None, tuple[int, ...]]] = []
    unit_messages: dict[int, Any] = {}
    seen_grouped: set[int] = set()
    seen_single: set[int] = set()
    expanded_ids: list[int] = []

    for requested_id in requested:
        message = initial_by_id.get(requested_id)
        if message is None:
            failures.append(_failure(requested_id, MESSAGE_NOT_FOUND, "消息不存在或当前账号无权访问。"))
            continue

        grouped_id = getattr(message, "grouped_id", None)
        if grouped_id is None:
            if requested_id in seen_single:
                continue
            seen_single.add(requested_id)
            failure = _classify_failure(message)
            if failure is not None:
                failures.append(_failure(requested_id, failure[0], failure[1]))
                continue
            unit_messages[requested_id] = message
            units.append((None, (requested_id,)))
            continue

        grouped_id = int(grouped_id)
        if grouped_id in seen_grouped:
            continue
        seen_grouped.add(grouped_id)
        album_rows, complete = await _discover_album(service.client, source_entity, message)
        album_ids = tuple(int(getattr(row, "id", 0) or 0) for row in album_rows)
        if not complete:
            for message_id in album_ids or (requested_id,):
                failures.append(
                    _failure(
                        message_id,
                        ALBUM_INCOMPLETE,
                        "无法在有界扫描内确认完整相册，已拒绝部分转发。",
                        grouped_id,
                    )
                )
            continue

        album_failure: tuple[str, str] | None = None
        for row in album_rows:
            candidate_failure = _classify_failure(row)
            if candidate_failure is not None:
                album_failure = candidate_failure
                break
            if forwardable_message_kind(row) != "photo":
                album_failure = (UNSUPPORTED_MESSAGE, "grouped_id 单元不是完整照片相册。")
                break
        if album_failure is not None:
            for message_id in album_ids:
                failures.append(_failure(message_id, album_failure[0], album_failure[1], grouped_id))
            continue

        for row in album_rows:
            message_id = int(getattr(row, "id", 0) or 0)
            unit_messages[message_id] = row
            if message_id not in requested and message_id not in expanded_ids:
                expanded_ids.append(message_id)
        units.append((grouped_id, album_ids))

    planned_ids = tuple(message_id for _grouped_id, unit_ids in units for message_id in unit_ids)
    if len(planned_ids) > max_messages:
        raise TelegramBridgeError(
            INVALID_ARGUMENT,
            "补全完整相册后的 forward 数量超过当前批次安全上限。",
            {
                "requested_count": len(requested),
                "planned_count": len(planned_ids),
                "limit": max_messages,
                "hint": "如确有需要，请显式使用 --allow-large-batch。",
            },
        )

    albums = tuple(
        ForwardAlbum(grouped_id=int(grouped_id), message_ids=unit_ids)
        for grouped_id, unit_ids in units
        if grouped_id is not None
    )
    photo_count = sum(1 for message_id in planned_ids if forwardable_message_kind(unit_messages[message_id]) == "photo")
    failed_ids = tuple(dict.fromkeys(item.message_id for item in failures))

    logger.info(
        "Telegram forward plan: requested=%s planned=%s photos=%s albums=%s excluded=%s dry_run=%s",
        len(requested),
        len(planned_ids),
        photo_count,
        len(albums),
        len(failures),
        dry_run,
    )

    if dry_run or not planned_ids:
        return ForwardResult(
            source_chat_id=source.chat_id,
            destination_chat_id=destination_id,
            requested_ids=requested,
            successful_ids=planned_ids,
            failed_ids=failed_ids,
            dry_run=dry_run,
            requested_count=len(requested),
            forwardable_count=len(planned_ids),
            photo_count=photo_count,
            album_count=len(albums),
            planned_ids=planned_ids,
            expanded_ids=tuple(expanded_ids),
            target_message_ids=(),
            failures=tuple(failures),
            albums=albums,
            forwarded=(),
        )

    confirmed_sources: list[int] = []
    target_ids: list[int] = []
    forwarded: list[ForwardedMessage] = []
    grouped_by_source = {
        message_id: grouped_id
        for grouped_id, unit_ids in units
        for message_id in unit_ids
    }

    for chunk in _chunk_units(units):
        try:
            response = await service.client.forward_messages(
                destination_entity,
                chunk,
                from_peer=source_entity,
            )
        except FloodWaitError:
            raise
        except TelegramBridgeError:
            raise
        except RPCError as exc:
            raise TelegramBridgeError(
                WRITE_FAILED,
                f"Telegram 拒绝转发：{type(exc).__name__}",
                {"confirmed_source_ids": confirmed_sources, "confirmed_target_ids": target_ids},
            ) from exc
        except Exception as exc:
            raise TelegramBridgeError(
                WRITE_OUTCOME_UNKNOWN,
                "Telegram forward 请求可能已提交，但未能确认目标侧结果；不得自动重发。",
                {
                    "exception_type": type(exc).__name__,
                    "confirmed_source_ids": confirmed_sources,
                    "confirmed_target_ids": target_ids,
                },
            ) from exc

        target_messages = _normalize_forward_result(response)
        current_target_ids = [int(getattr(item, "id", 0) or 0) for item in target_messages]
        if len(current_target_ids) != len(chunk) or any(message_id <= 0 for message_id in current_target_ids):
            raise TelegramBridgeError(
                WRITE_OUTCOME_UNKNOWN,
                "Telegram 已返回 forward 响应，但目标消息 ID 不完整；不得自动重发。",
                {
                    "expected_count": len(chunk),
                    "returned_count": len(current_target_ids),
                    "confirmed_source_ids": confirmed_sources,
                    "confirmed_target_ids": target_ids,
                },
            )
        for source_id, target_id in zip(chunk, current_target_ids, strict=True):
            confirmed_sources.append(source_id)
            target_ids.append(target_id)
            forwarded.append(
                ForwardedMessage(
                    source_message_id=source_id,
                    target_message_id=target_id,
                    grouped_id=grouped_by_source.get(source_id),
                )
            )

    logger.info(
        "Telegram forward succeeded: count=%s photos=%s albums=%s excluded=%s",
        len(confirmed_sources),
        photo_count,
        len(albums),
        len(failures),
    )
    return ForwardResult(
        source_chat_id=source.chat_id,
        destination_chat_id=destination_id,
        requested_ids=requested,
        successful_ids=tuple(confirmed_sources),
        failed_ids=failed_ids,
        dry_run=False,
        requested_count=len(requested),
        forwardable_count=len(planned_ids),
        photo_count=photo_count,
        album_count=len(albums),
        planned_ids=planned_ids,
        expanded_ids=tuple(expanded_ids),
        target_message_ids=tuple(target_ids),
        failures=tuple(failures),
        albums=albums,
        forwarded=tuple(forwarded),
    )


def forward_plan_smoke_test() -> bool:
    class MessageMediaPhoto:
        pass

    class Fake:
        action = None
        media = MessageMediaPhoto()
        message = ""

    return forwardable_message_kind(Fake()) == "photo"
