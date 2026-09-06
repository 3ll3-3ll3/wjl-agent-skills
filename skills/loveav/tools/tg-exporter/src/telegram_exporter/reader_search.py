from __future__ import annotations

import encodings.idna as _stdlib_idna
import re
import time
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

from telethon.tl.custom.message import Message

from .bridge_errors import INVALID_ARGUMENT, TelegramBridgeError
from .reader_models import DialogInfo, MessageInfoV3, Page
from .reader_service import MAX_PAGE_LIMIT, PersonalAccountReader, _dialog_rank

CANDIDATE_SCAN_CAP = 5000
MAX_REGEX_PATTERN_LENGTH = 512
_URL_RE = re.compile(r"(?i)(?:https?://|tg://|www\.)[^\s<>\]\[(){}\"']+")
_DOMAIN_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def _validate_limit(limit: int) -> int:
    value = int(limit)
    if value <= 0:
        raise TelegramBridgeError(INVALID_ARGUMENT, "limit 必须大于 0。")
    if value > MAX_PAGE_LIMIT:
        raise TelegramBridgeError(
            INVALID_ARGUMENT,
            f"reader 单页最多 {MAX_PAGE_LIMIT} 条。",
            {"requested_limit": value, "max_limit": MAX_PAGE_LIMIT},
        )
    return value


def _compile_regex(value: str | None, *, case_sensitive: bool) -> re.Pattern[str] | None:
    if value is None:
        return None
    pattern = str(value)
    if not pattern:
        raise TelegramBridgeError(INVALID_ARGUMENT, "regex 不能为空。")
    if len(pattern) > MAX_REGEX_PATTERN_LENGTH:
        raise TelegramBridgeError(
            INVALID_ARGUMENT,
            f"regex 最长 {MAX_REGEX_PATTERN_LENGTH} 个字符。",
            {"max_length": MAX_REGEX_PATTERN_LENGTH},
        )
    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        return re.compile(pattern, flags)
    except re.error as exc:
        details: dict[str, Any] = {}
        position = getattr(exc, "pos", None)
        if isinstance(position, int):
            details["position"] = position
        raise TelegramBridgeError(
            INVALID_ARGUMENT,
            "regex 表达式无效。",
            details or None,
        ) from exc


def _idna_hostname(hostname: str) -> str:
    """Convert one hostname to canonical ASCII without codec lookup/network data.

    Importing ``encodings.idna`` statically is deliberate: PyInstaller can see
    and freeze this stdlib module, unlike ``text.encode('idna')`` which performs
    a runtime codec lookup that was missing from the v0.3.0 tgctl bundle.
    """

    raw = hostname.strip().rstrip(".")
    if not raw:
        raise TelegramBridgeError(INVALID_ARGUMENT, "url-domain 不能为空。")
    if len(raw) > 253:
        raise TelegramBridgeError(INVALID_ARGUMENT, "url-domain 过长。")

    labels: list[str] = []
    for label in raw.split("."):
        if not label:
            raise TelegramBridgeError(INVALID_ARGUMENT, "url-domain 包含空域名段。")
        try:
            ascii_label = _stdlib_idna.ToASCII(label).decode("ascii").casefold()
        except (UnicodeError, UnicodeDecodeError) as exc:
            raise TelegramBridgeError(INVALID_ARGUMENT, "url-domain 包含无法编码的域名字符。") from exc
        if not _DOMAIN_LABEL_RE.fullmatch(ascii_label):
            raise TelegramBridgeError(INVALID_ARGUMENT, "url-domain 包含非法域名段。")
        labels.append(ascii_label)
    canonical = ".".join(labels)
    if len(canonical) > 253:
        raise TelegramBridgeError(INVALID_ARGUMENT, "url-domain 过长。")
    return canonical


def _normalize_domain(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise TelegramBridgeError(INVALID_ARGUMENT, "url-domain 不能为空。")
    if any(ch.isspace() for ch in raw):
        raise TelegramBridgeError(INVALID_ARGUMENT, "url-domain 不能包含空白字符。")

    # Accept either a bare hostname or a complete URL. Parsing is entirely
    # local; no PSL/public-suffix database and no network access are involved.
    candidate = raw if "://" in raw else f"//{raw}"
    try:
        parsed = urlsplit(candidate)
    except ValueError as exc:
        raise TelegramBridgeError(INVALID_ARGUMENT, "无法解析 url-domain。") from exc

    if "://" in raw and not parsed.scheme:
        raise TelegramBridgeError(INVALID_ARGUMENT, "完整 URL 缺少 scheme。")
    if parsed.username is not None or parsed.password is not None:
        raise TelegramBridgeError(INVALID_ARGUMENT, "url-domain 不接受带认证信息的 URL。")
    try:
        port = parsed.port
    except ValueError as exc:
        raise TelegramBridgeError(INVALID_ARGUMENT, "url-domain 包含非法端口。") from exc
    _ = port  # A valid explicit port is ignored for hostname matching.

    hostname = parsed.hostname
    if not hostname:
        raise TelegramBridgeError(INVALID_ARGUMENT, "无法从 url-domain 中取得 hostname。")
    if ":" in hostname:
        raise TelegramBridgeError(INVALID_ARGUMENT, "url-domain 目前只接受 DNS hostname，不接受 IPv6 literal。")
    return _idna_hostname(hostname)


def _url_hostname(value: str) -> str | None:
    raw = value.strip().rstrip(".,;:!?)]}")
    if not raw:
        return None
    candidate = raw if "://" in raw else f"http://{raw}"
    try:
        hostname = urlsplit(candidate).hostname
    except ValueError:
        return None
    if not hostname or ":" in hostname:
        return None
    try:
        return _idna_hostname(hostname)
    except TelegramBridgeError:
        return None


def domain_matches(hostname: str | None, wanted: str) -> bool:
    if not hostname:
        return False
    return hostname == wanted or hostname.endswith(f".{wanted}")


def domain_filter_smoke_test() -> bool:
    """Offline packaged regression used by CI against the final tgctl.exe."""

    cases = {
        "mypikpak.com": "mypikpak.com",
        " www.mypikpak.com ": "www.mypikpak.com",
        "MYPiKPAK.CoM": "mypikpak.com",
        "https://mypikpak.com/path?q=1": "mypikpak.com",
        "https://cdn.mypikpak.com/a": "cdn.mypikpak.com",
    }
    for raw, expected in cases.items():
        if _normalize_domain(raw) != expected:
            return False
    if not domain_matches(_url_hostname("https://cdn.mypikpak.com/x"), "mypikpak.com"):
        return False
    if domain_matches(_url_hostname("https://mypikpak.com.evil.com/x"), "mypikpak.com"):
        return False
    try:
        _normalize_domain("not a domain")
    except TelegramBridgeError as exc:
        return exc.code == INVALID_ARGUMENT
    return False


def _extract_urls(message: Any) -> list[str]:
    urls: list[str] = []
    for entity in getattr(message, "entities", None) or ():
        direct = getattr(entity, "url", None)
        if isinstance(direct, str) and direct:
            urls.append(direct)

    extractor = getattr(message, "get_entities_text", None)
    if callable(extractor):
        try:
            for entity, text in extractor() or ():
                name = type(entity).__name__
                if "Url" not in name:
                    continue
                direct = getattr(entity, "url", None)
                value = direct if isinstance(direct, str) and direct else text
                if isinstance(value, str) and value:
                    urls.append(value)
        except Exception:
            # Entity extraction is an optional precision path; safe text parsing
            # below still handles explicit http(s)/www links.
            pass

    text = getattr(message, "message", None) or ""
    urls.extend(match.group(0) for match in _URL_RE.finditer(text))
    return list(dict.fromkeys(urls))


def _message_type(item: MessageInfoV3) -> str:
    if item.service_action:
        return "service"
    if item.poll:
        return "poll"
    if item.media:
        return item.media.media_type
    return "text"


def _role_matches(item: MessageInfoV3, role: str | None) -> bool:
    if role is None:
        return True
    sender = item.sender
    if sender.role_basis != "current_snapshot":
        return False
    if role == "owner":
        return sender.is_creator is True
    if role == "admin":
        return sender.is_admin is True
    if role == "member":
        return (
            sender.sender_type == "user"
            and sender.is_creator is False
            and sender.is_admin is False
        )
    return False


def _message_matches(
    item: MessageInfoV3,
    source_message: Any,
    *,
    contains: str | None,
    regex_pattern: re.Pattern[str] | None,
    case_sensitive: bool,
    sender_id: int | None,
    sender_role: str | None,
    message_type: str | None,
    topic_id: int | None,
    has_link: str,
    url_domain: str | None,
) -> bool:
    content = item.caption if item.caption is not None else (item.text or "")
    if contains:
        needle = contains if case_sensitive else contains.casefold()
        haystack = content if case_sensitive else content.casefold()
        if needle not in haystack:
            return False
    if regex_pattern is not None and regex_pattern.search(content) is None:
        return False
    if sender_id is not None and item.sender.sender_id != sender_id:
        return False
    if not _role_matches(item, sender_role):
        return False
    if message_type and _message_type(item) != message_type:
        return False
    if topic_id is not None and item.forum_topic_id != topic_id:
        return False

    urls: list[str] | None = None
    if has_link != "all" or url_domain:
        urls = _extract_urls(source_message)
    if has_link == "yes" and not urls:
        return False
    if has_link == "no" and urls:
        return False
    if url_domain:
        if not any(domain_matches(_url_hostname(url), url_domain) for url in (urls or [])):
            return False
    return True


async def _current_role_snapshot(reader: PersonalAccountReader, row: DialogInfo) -> tuple[dict[int, Any], bool]:
    if row.dialog_type not in {"group", "supergroup", "channel"}:
        return {}, False
    try:
        _, current_entity = await reader.resolve_dialog(row.chat_id)
    except TelegramBridgeError:
        return {}, False
    return await reader._admin_snapshot(row, current_entity)


async def _scan_source(
    reader: PersonalAccountReader,
    logical_row: DialogInfo,
    *,
    source_chat_id: int,
    before_message_id: int,
    result_limit: int,
    scan_budget: int,
    contains: str | None,
    regex_pattern: re.Pattern[str] | None,
    case_sensitive: bool,
    sender_id: int | None,
    sender_role: str | None,
    since: datetime | None,
    until: datetime | None,
    message_type: str | None,
    topic_id: int | None,
    has_link: str,
    url_domain: str | None,
) -> tuple[list[MessageInfoV3], int, int, bool, int]:
    try:
        entity = await reader.client.get_entity("me" if logical_row.dialog_type == "saved" else source_chat_id)
    except Exception as exc:
        raise reader.cursor.stale() from exc

    role_snapshot, role_available = await _current_role_snapshot(reader, logical_row)
    sender_entity = None
    if sender_id is not None:
        try:
            sender_entity = await reader.client.get_entity(sender_id)
        except Exception:
            # A sender filter for an entity no longer resolvable simply cannot
            # match; it must not become a broad unfiltered scan.
            return [], 0, before_message_id, True, 0

    kwargs: dict[str, Any] = {"limit": min(scan_budget, CANDIDATE_SCAN_CAP)}
    if before_message_id:
        kwargs["offset_id"] = before_message_id
    if contains:
        kwargs["search"] = contains
    if sender_entity is not None:
        kwargs["from_user"] = sender_entity
    if until is not None:
        kwargs["offset_date"] = until
    if topic_id is not None:
        kwargs["reply_to"] = int(topic_id)

    matches: list[MessageInfoV3] = []
    scanned = 0
    last_id = before_message_id
    exhausted = True
    local_filter_ns = 0

    async for message in reader.client.iter_messages(entity, **kwargs):
        if not isinstance(message, Message):
            continue
        date = getattr(message, "date", None)
        if date is None:
            continue
        if until is not None and date >= until:
            continue
        if since is not None and date < since:
            exhausted = True
            break
        scanned += 1
        last_id = int(getattr(message, "id", 0) or 0)
        item = await reader._message_info_v3(logical_row, source_chat_id, message, role_snapshot, role_available)
        started = time.perf_counter_ns()
        matched = _message_matches(
            item,
            message,
            contains=contains,
            regex_pattern=regex_pattern,
            case_sensitive=case_sensitive,
            sender_id=sender_id,
            sender_role=sender_role,
            message_type=message_type,
            topic_id=topic_id,
            has_link=has_link,
            url_domain=url_domain,
        )
        local_filter_ns += time.perf_counter_ns() - started
        if matched:
            matches.append(item)
            if len(matches) >= result_limit:
                exhausted = False
                break
        if scanned >= scan_budget:
            exhausted = False
            break
    else:
        exhausted = True

    return matches, scanned, last_id, exhausted, int(local_filter_ns / 1_000_000)


async def search_messages_page(
    reader: PersonalAccountReader,
    *,
    chat: str | int | None,
    contains: str | None = None,
    regex: str | None = None,
    sender_id: int | None = None,
    sender_role: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    message_type: str | None = None,
    topic_id: int | None = None,
    has_link: str = "all",
    url_domain: str | None = None,
    cursor: str | None = None,
    limit: int = 100,
    case_sensitive: bool = False,
) -> Page:
    limit = _validate_limit(limit)
    regex_pattern = _compile_regex(regex, case_sensitive=case_sensitive)
    if sender_role not in {None, "owner", "admin", "member"}:
        raise TelegramBridgeError(INVALID_ARGUMENT, "sender-role 只能是 owner/admin/member。")
    if has_link not in {"yes", "no", "all"}:
        raise TelegramBridgeError(INVALID_ARGUMENT, "has-link 只能是 yes/no/all。")
    if since and until and since >= until:
        raise TelegramBridgeError(INVALID_ARGUMENT, "since 必须早于 until。")
    normalized_domain = _normalize_domain(url_domain) if url_domain else None
    if chat is None and not any((contains, regex, sender_id, sender_role, message_type, topic_id, normalized_domain, has_link != "all", since, until)):
        raise TelegramBridgeError(
            INVALID_ARGUMENT,
            "全局搜索至少需要一个筛选条件；如需完整历史，请按会话使用 messages history。",
        )

    logical_row: DialogInfo | None = None
    if chat is not None:
        logical_row, _ = await reader.resolve_dialog(chat)
        if logical_row.migrated_to_chat_id is not None:
            try:
                logical_row, _ = await reader.resolve_dialog(logical_row.migrated_to_chat_id)
            except TelegramBridgeError:
                pass

    query = {
        "chat_id": logical_row.chat_id if logical_row else None,
        "contains": contains,
        "regex": regex,
        "sender_id": sender_id,
        "sender_role": sender_role,
        "since": since.isoformat() if since else None,
        "until": until.isoformat() if until else None,
        "message_type": message_type,
        "topic_id": topic_id,
        "has_link": has_link,
        "url_domain": normalized_domain,
        "case_sensitive": bool(case_sensitive),
    }
    position = reader.cursor.decode(cursor, "messages.search", query) or {}

    network_started = time.perf_counter()
    total_scanned = 0
    total_local_ms = 0
    matches: list[MessageInfoV3] = []
    next_position: dict[str, Any] | None = None
    has_more = False

    if logical_row is not None:
        segment = str(position.get("segment") or "current")
        before_id = int(position.get("before_message_id", 0) or 0)
        legacy_id = logical_row.migrated_from_chat_id
        if segment not in {"current", "legacy"}:
            raise TelegramBridgeError(INVALID_ARGUMENT, "search cursor segment 无效。")
        if segment == "legacy" and legacy_id is None:
            raise reader.cursor.stale("search cursor 指向 legacy segment，但迁移关系已不可用。")
        while len(matches) < limit and total_scanned < CANDIDATE_SCAN_CAP:
            source_id = logical_row.chat_id if segment == "current" else int(legacy_id or 0)
            rows, scanned, last_id, exhausted, local_ms = await _scan_source(
                reader,
                logical_row,
                source_chat_id=source_id,
                before_message_id=before_id,
                result_limit=limit - len(matches),
                scan_budget=CANDIDATE_SCAN_CAP - total_scanned,
                contains=contains,
                regex_pattern=regex_pattern,
                case_sensitive=case_sensitive,
                sender_id=sender_id,
                sender_role=sender_role,
                since=since,
                until=until,
                message_type=message_type,
                topic_id=topic_id,
                has_link=has_link,
                url_domain=normalized_domain,
            )
            matches.extend(rows)
            total_scanned += scanned
            total_local_ms += local_ms
            if len(matches) >= limit or total_scanned >= CANDIDATE_SCAN_CAP:
                has_more = not exhausted or (segment == "current" and legacy_id is not None)
                next_position = {"segment": segment, "before_message_id": last_id}
                break
            if exhausted and segment == "current" and legacy_id is not None and topic_id is None:
                segment = "legacy"
                before_id = 0
                continue
            if exhausted:
                break
            before_id = last_id
        else:
            if total_scanned >= CANDIDATE_SCAN_CAP:
                has_more = True
                next_position = {"segment": segment, "before_message_id": before_id}
    else:
        catalogue, _ = await reader._dialog_catalogue()
        # Legacy migrated rows are skipped here; their current logical row scans
        # both segments itself.
        catalogue = [row for row in catalogue if row.migrated_to_chat_id is None]
        catalogue.sort(key=lambda row: (_dialog_rank(row.dialog_type), row.chat_id))
        start_rank = int(position.get("dialog_rank", -1))
        start_chat_id = int(position.get("chat_id", -(2**63)))
        start_before = int(position.get("before_message_id", 0) or 0)
        start_segment = str(position.get("segment") or "current")
        if start_segment not in {"current", "legacy"}:
            raise TelegramBridgeError(INVALID_ARGUMENT, "search cursor segment 无效。")
        started_same = False

        for row in catalogue:
            key = (_dialog_rank(row.dialog_type), row.chat_id)
            if key < (start_rank, start_chat_id):
                continue
            same_cursor_row = key == (start_rank, start_chat_id)
            if same_cursor_row:
                before_id = start_before
                segment = start_segment
                started_same = True
            elif not started_same and (start_rank, start_chat_id) != (-1, -(2**63)):
                if key <= (start_rank, start_chat_id):
                    continue
                before_id = 0
                segment = "current"
            else:
                before_id = 0
                segment = "current"
            started_same = True

            legacy_id = row.migrated_from_chat_id
            if segment == "legacy" and legacy_id is None:
                raise reader.cursor.stale("search cursor 指向 legacy segment，但迁移关系已不可用。")
            while len(matches) < limit and total_scanned < CANDIDATE_SCAN_CAP:
                source_id = row.chat_id if segment == "current" else int(legacy_id or 0)
                rows, scanned, last_id, exhausted, local_ms = await _scan_source(
                    reader,
                    row,
                    source_chat_id=source_id,
                    before_message_id=before_id,
                    result_limit=limit - len(matches),
                    scan_budget=CANDIDATE_SCAN_CAP - total_scanned,
                    contains=contains,
                    regex_pattern=regex_pattern,
                    case_sensitive=case_sensitive,
                    sender_id=sender_id,
                    sender_role=sender_role,
                    since=since,
                    until=until,
                    message_type=message_type,
                    topic_id=topic_id,
                    has_link=has_link,
                    url_domain=normalized_domain,
                )
                matches.extend(rows)
                total_scanned += scanned
                total_local_ms += local_ms
                if len(matches) >= limit or total_scanned >= CANDIDATE_SCAN_CAP:
                    has_more = True
                    next_position = {
                        "dialog_rank": _dialog_rank(row.dialog_type),
                        "chat_id": row.chat_id,
                        "segment": segment,
                        "before_message_id": last_id,
                    }
                    break
                if exhausted and segment == "current" and legacy_id is not None and topic_id is None:
                    segment = "legacy"
                    before_id = 0
                    continue
                break
            if has_more:
                break
            # Fully exhausted this dialog; next cursor is only needed if another
            # dialog exists. We do not expose a cursor for a fully exhausted account.
            before_id = 0
        else:
            has_more = False

    next_cursor = reader.cursor.encode("messages.search", query, next_position) if has_more and next_position else None
    network_ms = int((time.perf_counter() - network_started) * 1000)
    return Page(
        items=matches,
        next_cursor=next_cursor,
        has_more=has_more,
        timing={"network_ms": network_ms, "local_filter_ms": total_local_ms, "serialization_ms": 0},
        scanned_count=total_scanned,
        matched_count=len(matches),
    )
