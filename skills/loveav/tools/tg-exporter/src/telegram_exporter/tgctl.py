from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any

from telethon.errors import FloodWaitError

from . import __version__
from .bridge_errors import (
    ACCESS_DENIED,
    AMBIGUOUS_CHAT,
    AUTH_GUI_ONLY,
    CHAT_NOT_FOUND,
    CURSOR_STALE,
    DAEMON_UNAVAILABLE,
    DOWNLOAD_CONFIRMATION_REQUIRED,
    DOWNLOAD_LIMIT_EXCEEDED,
    EXPORT_IN_PROGRESS,
    FLOOD_WAIT,
    INVALID_ARGUMENT,
    INVALID_CURSOR,
    MEMBERS_UNAVAILABLE,
    MESSAGE_NOT_FOUND,
    NOT_A_FORUM,
    NOT_AUTHORIZED,
    SESSION_BUSY,
    WRITE_FAILED,
    WRITE_OUTCOME_UNKNOWN,
    TelegramBridgeError,
)
from .logging_setup import setup_logging
from .ipc_protocol import PROTOCOL
from .session_lock import SessionBusyError
from .telegram_proxy import DaemonTelegramProxy

DEFAULT_FORWARD_LIMIT = 20
LARGE_FORWARD_LIMIT = 200
SAFE_SESSION_LABEL = r"%APPDATA%\TelegramMultiChatExporter\telegram.session"
READER_SCHEMA = "tgctl.reader.v1"


class TgctlArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise TelegramBridgeError(INVALID_ARGUMENT, message)


def _configure_console_streams() -> None:
    """Keep packaged CLI JSON UTF-8 on legacy Windows console code pages."""
    stdout_reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(stdout_reconfigure):
        stdout_reconfigure(encoding="utf-8", errors="strict")
    stderr_reconfigure = getattr(sys.stderr, "reconfigure", None)
    if callable(stderr_reconfigure):
        stderr_reconfigure(encoding="utf-8", errors="backslashreplace")


def _add_json_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="stdout 仅输出机器可读 JSON")


def _add_page_output_flags(parser: argparse.ArgumentParser) -> None:
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true", help="stdout 输出单个 JSON page envelope")
    output.add_argument("--jsonl", action="store_true", help="stdout 按 meta/item/end JSONL 输出当前有限页")


def build_parser() -> argparse.ArgumentParser:
    parser = TgctlArgumentParser(prog="tgctl", description="TG Exporter local Telegram CLI bridge")
    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("status")
    _add_json_flag(status)

    version = sub.add_parser("version")
    _add_json_flag(version)

    account = sub.add_parser("account")
    account_sub = account.add_subparsers(dest="account_command", required=True)
    account_get = account_sub.add_parser("get")
    _add_json_flag(account_get)

    dialogs = sub.add_parser("dialogs")
    dialogs_sub = dialogs.add_subparsers(dest="dialogs_command", required=True)
    dialogs_list = dialogs_sub.add_parser("list")
    dialogs_list.add_argument("--type", dest="dialog_type", choices=["group", "supergroup", "channel", "private", "bot", "saved"])
    dialogs_list.add_argument("--folder")
    dialogs_list.add_argument("--archived", choices=["yes", "no", "all"], default="all")
    dialogs_list.add_argument("--search")
    dialogs_list.add_argument("--unread", choices=["yes", "no", "all"], default="all")
    dialogs_list.add_argument("--pinned", choices=["yes", "no", "all"], default="all")
    dialogs_list.add_argument("--cursor")
    dialogs_list.add_argument("--limit", type=int, default=100)
    _add_page_output_flags(dialogs_list)

    chats = sub.add_parser("chats")
    chats_sub = chats.add_subparsers(dest="chats_command", required=True)
    chats_list = chats_sub.add_parser("list")
    chats_list.add_argument("--folder")
    chats_list.add_argument("--search")
    chats_list.add_argument("--limit", type=int, default=100)
    _add_json_flag(chats_list)

    chats_get = chats_sub.add_parser("get")
    chats_get.add_argument("--chat", required=True)
    _add_json_flag(chats_get)

    chats_members = chats_sub.add_parser("members")
    chats_members.add_argument("--chat", required=True)
    chats_members.add_argument("--role", choices=["owner", "admin", "member"])
    chats_members.add_argument("--cursor")
    chats_members.add_argument("--limit", type=int, default=100)
    _add_page_output_flags(chats_members)

    messages = sub.add_parser("messages")
    messages_sub = messages.add_subparsers(dest="messages_command", required=True)

    search = messages_sub.add_parser("search")
    search.add_argument("--chat")
    search.add_argument("--contains")
    search.add_argument("--regex", help="Python regex，本地 bounded filter；默认忽略大小写")
    search.add_argument("--sender-id", type=int)
    search.add_argument("--sender-role", choices=["owner", "admin", "member"])
    search.add_argument("--since")
    search.add_argument("--until")
    search.add_argument("--message-type")
    search.add_argument("--topic", dest="topic_id", type=int)
    search.add_argument("--has-link", choices=["yes", "no", "all"], default="all")
    search.add_argument("--url-domain")
    search.add_argument("--cursor")
    search.add_argument("--limit", type=int, default=100)
    search.add_argument("--case-sensitive", action="store_true")
    search.add_argument("--legacy-schema", action="store_true", help="使用 v0.1.x 单会话简化搜索结果")
    _add_page_output_flags(search)

    history = messages_sub.add_parser("history")
    history.add_argument("--chat", required=True)
    history.add_argument("--cursor")
    history.add_argument("--limit", type=int, default=100)
    history.add_argument("--since")
    history.add_argument("--until")
    _add_page_output_flags(history)

    replies = messages_sub.add_parser("replies")
    replies.add_argument("--chat", required=True)
    replies.add_argument("--message-id", required=True, type=int)
    replies.add_argument("--cursor")
    replies.add_argument("--limit", type=int, default=100)
    replies.add_argument("--since")
    replies.add_argument("--until")
    _add_page_output_flags(replies)

    unread = messages_sub.add_parser("unread")
    unread.add_argument("--chat", required=True)
    unread.add_argument("--cursor")
    unread.add_argument("--limit", type=int, default=500)
    _add_json_flag(unread)

    mark_read = messages_sub.add_parser("mark-read")
    mark_read.add_argument("--chat", required=True)
    mark_read.add_argument("--snapshot-token", required=True)
    mark_read.add_argument("--max-id", type=int, required=True)
    mark_read.add_argument("--confirm", required=True)
    _add_json_flag(mark_read)

    get = messages_sub.add_parser("get")
    get.add_argument("--chat", required=True)
    get.add_argument("--ids", nargs="+", type=int, required=True)
    get.add_argument("--legacy-schema", action="store_true", help="临时保留 v0.1.x 简化消息 schema")
    _add_json_flag(get)

    topics = sub.add_parser("topics")
    topics_sub = topics.add_subparsers(dest="topics_command", required=True)
    topics_list = topics_sub.add_parser("list")
    topics_list.add_argument("--chat", required=True)
    topics_list.add_argument("--cursor")
    topics_list.add_argument("--limit", type=int, default=100)
    _add_page_output_flags(topics_list)

    topics_history = topics_sub.add_parser("history")
    topics_history.add_argument("--chat", required=True)
    topics_history.add_argument("--topic", dest="topic_id", required=True, type=int)
    topics_history.add_argument("--cursor")
    topics_history.add_argument("--limit", type=int, default=100)
    topics_history.add_argument("--since")
    topics_history.add_argument("--until")
    _add_page_output_flags(topics_history)

    media = sub.add_parser("media")
    media_sub = media.add_subparsers(dest="media_command", required=True)
    media_download = media_sub.add_parser("download")
    media_download.add_argument("--chat", required=True)
    media_download.add_argument("--ids", nargs="+", type=int, required=True)
    media_download.add_argument("--output", required=True)
    media_download.add_argument("--confirm")
    media_download.add_argument("--allow-large-download", action="store_true")
    _add_json_flag(media_download)

    forward = sub.add_parser("forward")
    forward.add_argument("--from", dest="source_chat", required=True)
    forward.add_argument("--to", dest="destination_chat", required=True)
    forward.add_argument("--ids", nargs="+", type=int, required=True)
    forward.add_argument("--dry-run", action="store_true")
    forward.add_argument("--allow-large-batch", action="store_true")
    _add_json_flag(forward)

    send = sub.add_parser("send")
    send.add_argument("--to", dest="destination_chat", required=True)
    send.add_argument("--text", required=True)
    send.add_argument("--dry-run", action="store_true")
    _add_json_flag(send)

    send_capture = sub.add_parser("send-capture")
    send_capture.add_argument("--to", dest="destination_chat", required=True)
    send_capture.add_argument("--text", required=True)
    send_capture.add_argument("--first-reply-timeout", type=float, default=8.0)
    send_capture.add_argument("--settle-seconds", type=float, default=2.0)
    send_capture.add_argument("--max-messages", type=int, default=20)
    send_capture.add_argument("--url-domain")
    send_capture.add_argument("--dry-run", action="store_true")
    _add_json_flag(send_capture)
    return parser


def validate_forward_batch(ids: list[int], allow_large_batch: bool) -> None:
    limit = LARGE_FORWARD_LIMIT if allow_large_batch else DEFAULT_FORWARD_LIMIT
    if len(ids) > limit:
        raise TelegramBridgeError(
            INVALID_ARGUMENT,
            f"单次 forward 最多 {limit} 条。"
            + ("" if allow_large_batch else "如确有需要，请显式加入 --allow-large-batch。"),
            {"requested_count": len(ids), "limit": limit},
        )


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise TelegramBridgeError(INVALID_ARGUMENT, f"无法解析时间：{value}") from exc
    if parsed.tzinfo is None:
        local_tz = datetime.now().astimezone().tzinfo
        parsed = parsed.replace(tzinfo=local_tz)
    return parsed


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def success(data: Any) -> dict[str, Any]:
    return {"ok": True, "data": _jsonable(data)}


def failure(code: str, message: str, details: Any = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        error["details"] = _jsonable(details)
    return {"ok": False, "error": error}


def _exit_code(code: str) -> int:
    return {
        INVALID_ARGUMENT: 2,
        NOT_AUTHORIZED: 3,
        AUTH_GUI_ONLY: 3,
        CHAT_NOT_FOUND: 4,
        MESSAGE_NOT_FOUND: 4,
        AMBIGUOUS_CHAT: 5,
        FLOOD_WAIT: 6,
        WRITE_FAILED: 7,
        SESSION_BUSY: 8,
        EXPORT_IN_PROGRESS: 9,
        WRITE_OUTCOME_UNKNOWN: 10,
        DAEMON_UNAVAILABLE: 11,
        INVALID_CURSOR: 12,
        CURSOR_STALE: 12,
        ACCESS_DENIED: 13,
        MEMBERS_UNAVAILABLE: 13,
        NOT_A_FORUM: 14,
        DOWNLOAD_CONFIRMATION_REQUIRED: 15,
        DOWNLOAD_LIMIT_EXCEEDED: 16,
    }.get(code, 1)


def _human_print(payload: dict[str, Any]) -> None:
    if not payload.get("ok"):
        error = payload["error"]
        print(f"ERROR [{error['code']}]: {error['message']}", file=sys.stderr)
        if error.get("details") is not None:
            print(json.dumps(error["details"], ensure_ascii=False, indent=2), file=sys.stderr)
        return
    data = payload.get("data")
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                print("\t".join(str(item.get(key, "")) for key in item.keys()))
            else:
                print(item)
    elif isinstance(data, dict):
        if isinstance(data.get("items"), list):
            for item in data["items"]:
                print(json.dumps(item, ensure_ascii=False))
            if data.get("has_more"):
                print(f"next_cursor: {data.get('next_cursor')}")
        else:
            for key, value in data.items():
                print(f"{key}: {value}")
    else:
        print(data)


def emit(payload: dict[str, Any], json_mode: bool, jsonl_mode: bool = False) -> None:
    if jsonl_mode:
        if not payload.get("ok"):
            print(json.dumps({"type": "error", **payload}, ensure_ascii=False, separators=(",", ":")))
            return
        data = payload.get("data") or {}
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            print(
                json.dumps(
                    {"type": "error", "ok": False, "error": {"code": INVALID_ARGUMENT, "message": "该命令不支持 JSONL page 输出。"}},
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )
            return
        print(json.dumps({"type": "meta", "ok": True, "data": {"schema": READER_SCHEMA}}, ensure_ascii=False, separators=(",", ":")))
        for item in data["items"]:
            print(json.dumps({"type": "item", "data": item}, ensure_ascii=False, separators=(",", ":")))
        end = {
            key: data.get(key)
            for key in ("count", "next_cursor", "has_more", "timing", "scanned_count", "matched_count")
            if key in data
        }
        print(json.dumps({"type": "end", "data": end}, ensure_ascii=False, separators=(",", ":")))
    elif json_mode:
        print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    else:
        _human_print(payload)


def _advanced_search_requested(args: argparse.Namespace) -> bool:
    return any(
        (
            args.regex is not None,
            args.sender_id is not None,
            args.sender_role is not None,
            args.message_type is not None,
            args.topic_id is not None,
            args.has_link != "all",
            args.url_domain is not None,
            args.cursor is not None,
            args.jsonl,
            args.chat is None,
        )
    )


async def run_command(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "version":
        return success(
            {
                "tgctl_version": __version__,
                "reader_schema": READER_SCHEMA,
                "ipc_protocol": PROTOCOL,
            }
        )

    proxy = DaemonTelegramProxy("tgctl")

    if args.command == "status":
        hello = await proxy.ipc.request("system.hello")
        runtime = await proxy.status()
        daemon_version = str(hello.get("daemon_app_version") or "") or None
        daemon_protocol = str(hello.get("protocol") or "") or None
        daemon_reader_schema = str(hello.get("reader_schema") or "") or None
        return success(
            {
                **runtime,
                "tgctl_version": __version__,
                "daemon_version": daemon_version,
                "reader_schema": daemon_reader_schema or READER_SCHEMA,
                "ipc_protocol": daemon_protocol or PROTOCOL,
                "compatible": daemon_protocol == PROTOCOL
                and daemon_reader_schema in {None, READER_SCHEMA},
                "same_version": daemon_version == __version__,
                "capabilities": list(hello.get("capabilities") or []),
            }
        )

    if args.command == "account" and args.account_command == "get":
        return success(await proxy.ipc.request("account.get"))

    if args.command == "dialogs" and args.dialogs_command == "list":
        return success(
            await proxy.ipc.request(
                "dialogs.list",
                {
                    "dialog_type": args.dialog_type,
                    "folder": args.folder,
                    "archived": args.archived,
                    "search": args.search,
                    "unread": args.unread,
                    "pinned": args.pinned,
                    "cursor": args.cursor,
                    "limit": args.limit,
                },
            )
        )

    if args.command == "forward":
        validate_forward_batch(args.ids, args.allow_large_batch)

    if args.command == "chats" and args.chats_command == "list":
        if args.limit <= 0:
            raise TelegramBridgeError(INVALID_ARGUMENT, "limit 必须大于 0。")
        data = await proxy.ipc.request(
            "chats.list",
            {"folder": args.folder, "search": args.search, "limit": args.limit},
        )
        return success(data)

    if args.command == "chats" and args.chats_command == "get":
        return success(await proxy.ipc.request("chats.get", {"chat": args.chat}))

    if args.command == "chats" and args.chats_command == "members":
        return success(
            await proxy.ipc.request(
                "chats.members",
                {"chat": args.chat, "role": args.role, "cursor": args.cursor, "limit": args.limit},
            )
        )

    if args.command == "messages" and args.messages_command == "search":
        since = _parse_iso(args.since)
        until = _parse_iso(args.until)
        if args.legacy_schema:
            if args.chat is None:
                raise TelegramBridgeError(INVALID_ARGUMENT, "legacy search 必须指定 --chat。")
            if _advanced_search_requested(args):
                raise TelegramBridgeError(INVALID_ARGUMENT, "--legacy-schema 不支持第三代高级搜索参数。")
            rows = await proxy.search_messages(
                args.chat,
                contains=args.contains,
                since=since,
                until=until,
                limit=args.limit,
                case_sensitive=args.case_sensitive,
            )
            return success(rows)
        return success(
            await proxy.ipc.request(
                "messages.search",
                {
                    "schema": "v3",
                    "chat": args.chat,
                    "contains": args.contains,
                    "regex": args.regex,
                    "sender_id": args.sender_id,
                    "sender_role": args.sender_role,
                    "since": since.isoformat() if since else None,
                    "until": until.isoformat() if until else None,
                    "message_type": args.message_type,
                    "topic_id": args.topic_id,
                    "has_link": args.has_link,
                    "url_domain": args.url_domain,
                    "cursor": args.cursor,
                    "limit": args.limit,
                    "case_sensitive": args.case_sensitive,
                },
            )
        )

    if args.command == "messages" and args.messages_command == "history":
        since = _parse_iso(args.since)
        until = _parse_iso(args.until)
        return success(
            await proxy.ipc.request(
                "messages.history",
                {
                    "chat": args.chat,
                    "cursor": args.cursor,
                    "limit": args.limit,
                    "since": since.isoformat() if since else None,
                    "until": until.isoformat() if until else None,
                },
            )
        )

    if args.command == "messages" and args.messages_command == "replies":
        since = _parse_iso(args.since)
        until = _parse_iso(args.until)
        return success(
            await proxy.ipc.request(
                "messages.replies",
                {
                    "chat": args.chat,
                    "message_id": args.message_id,
                    "cursor": args.cursor,
                    "limit": args.limit,
                    "since": since.isoformat() if since else None,
                    "until": until.isoformat() if until else None,
                },
            )
        )

    if args.command == "messages" and args.messages_command == "unread":
        return success(
            await proxy.ipc.request(
                "messages.unread",
                {"chat": args.chat, "cursor": args.cursor, "limit": args.limit},
            )
        )

    if args.command == "messages" and args.messages_command == "mark-read":
        return success(
            await proxy.ipc.request(
                "messages.mark_read",
                {
                    "chat": args.chat,
                    "snapshot_token": args.snapshot_token,
                    "max_id": args.max_id,
                    "confirmation": args.confirm,
                },
                side_effect_after_send=True,
                retry_read_once=False,
            )
        )

    if args.command == "messages" and args.messages_command == "get":
        if args.legacy_schema:
            return success(await proxy.get_messages(args.chat, args.ids))
        return success(
            await proxy.ipc.request(
                "messages.get",
                {"chat": args.chat, "ids": args.ids, "schema": "v3"},
            )
        )

    if args.command == "topics" and args.topics_command == "list":
        return success(
            await proxy.ipc.request(
                "topics.list",
                {"chat": args.chat, "cursor": args.cursor, "limit": args.limit},
            )
        )

    if args.command == "topics" and args.topics_command == "history":
        since = _parse_iso(args.since)
        until = _parse_iso(args.until)
        return success(
            await proxy.ipc.request(
                "topics.history",
                {
                    "chat": args.chat,
                    "topic_id": args.topic_id,
                    "cursor": args.cursor,
                    "limit": args.limit,
                    "since": since.isoformat() if since else None,
                    "until": until.isoformat() if until else None,
                },
            )
        )

    if args.command == "media" and args.media_command == "download":
        confirmed = bool(args.confirm)
        return success(
            await proxy.ipc.request(
                "media.download",
                {
                    "chat": args.chat,
                    "ids": args.ids,
                    "output": args.output,
                    "confirm": args.confirm,
                    "allow_large_download": args.allow_large_download,
                },
                side_effect_after_send=confirmed,
                retry_read_once=not confirmed,
            )
        )

    if args.command == "forward":
        result = await proxy.forward_messages(
            args.source_chat,
            args.destination_chat,
            args.ids,
            dry_run=args.dry_run,
            allow_large_batch=args.allow_large_batch,
        )
        return success(result)

    if args.command == "send":
        result = await proxy.send_text_message(
            args.destination_chat,
            args.text,
            dry_run=args.dry_run,
        )
        data = _jsonable(result)
        if args.dry_run:
            data["text"] = args.text
        return success(data)

    if args.command == "send-capture":
        return success(
            await proxy.ipc.request(
                "send.capture",
                {
                    "destination_chat": args.destination_chat,
                    "text": args.text,
                    "first_reply_timeout_seconds": args.first_reply_timeout,
                    "settle_seconds": args.settle_seconds,
                    "max_messages": args.max_messages,
                    "url_domain": args.url_domain,
                    "dry_run": args.dry_run,
                },
                side_effect_after_send=not args.dry_run,
                retry_read_once=args.dry_run,
            )
        )

    raise TelegramBridgeError(INVALID_ARGUMENT, "未知命令。")


def main(argv: list[str] | None = None) -> int:
    _configure_console_streams()
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv == ["--tg-daemon-worker"]:
        from .daemon_main import main as daemon_main

        return daemon_main()

    json_mode = "--json" in argv
    jsonl_mode = "--jsonl" in argv
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        json_mode = bool(getattr(args, "json", json_mode))
        jsonl_mode = bool(getattr(args, "jsonl", jsonl_mode))
        # version is a pure executable-contract probe: it must not create a
        # daemon, runtime directory, log file, Session, or any other state.
        if args.command != "version":
            setup_logging()
        payload = asyncio.run(run_command(args))
        emit(payload, json_mode, jsonl_mode)
        return 0
    except TelegramBridgeError as exc:
        payload = failure(exc.code, exc.message, exc.details)
        emit(payload, json_mode, jsonl_mode)
        return _exit_code(exc.code)
    except SessionBusyError as exc:
        payload = failure(SESSION_BUSY, str(exc))
        emit(payload, json_mode, jsonl_mode)
        return _exit_code(SESSION_BUSY)
    except FloodWaitError as exc:
        seconds = int(getattr(exc, "seconds", 0) or 0)
        payload = failure(
            FLOOD_WAIT,
            f"Telegram 要求等待 {seconds} 秒后再试。" if seconds else "Telegram 触发 Flood Wait。",
            {"retry_after_seconds": seconds},
        )
        emit(payload, json_mode, jsonl_mode)
        return _exit_code(FLOOD_WAIT)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        logging.getLogger("telegram_exporter.tgctl").exception("tgctl command failed")
        payload = failure("TELEGRAM_ERROR", f"Telegram 操作失败：{type(exc).__name__}")
        emit(payload, json_mode, jsonl_mode)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
