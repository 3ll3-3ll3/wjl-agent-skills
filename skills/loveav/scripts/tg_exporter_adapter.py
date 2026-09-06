from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


ADAPTER_SCHEMA = "loveav.tgctl-adapter.v1"
EXPECTED_READER_SCHEMA = "tgctl.reader.v1"
MINIMUM_TGCTL_VERSION = (0, 3, 2)
MAX_PAGE_SIZE = 500
MAX_PAGES = 1000
_VERSION_RE = re.compile(r"(?:^|[^0-9])v?(\d+)\.(\d+)\.(\d+)(?:[^0-9]|$)", re.IGNORECASE)


class AdapterError(RuntimeError):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


@dataclass(frozen=True, slots=True)
class LocatedTgctl:
    path: Path
    source: str
    inferred_version: str | None


Runner = Callable[[list[str], float], subprocess.CompletedProcess[str]]


def _version_tuple(value: str | None) -> tuple[int, int, int] | None:
    if not value:
        return None
    match = _VERSION_RE.search(value)
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def _version_text(value: tuple[int, int, int] | None) -> str | None:
    if value is None:
        return None
    return ".".join(str(part) for part in value)


def _infer_version_from_path(path: Path) -> str | None:
    for part in reversed(path.parts):
        parsed = _version_tuple(part)
        if parsed is not None:
            return _version_text(parsed)
    return None


def _candidate_roots() -> list[Path]:
    roots: list[Path] = []
    for start in (Path.cwd(), Path(__file__).resolve().parent.parent):
        for root in (start, *start.parents):
            if root not in roots:
                roots.append(root)
            if len(roots) >= 16:
                break
    return roots


def _default_config_paths() -> list[Path]:
    paths: list[Path] = []
    explicit = os.environ.get("LOVEAV_TOOLS_CONFIG")
    if explicit:
        paths.append(Path(explicit).expanduser())
    data_dir = os.environ.get("LOVEAV_DATA_DIR")
    if data_dir:
        paths.append(Path(data_dir).expanduser() / "config" / "tools.json")
    for root in _candidate_roots():
        paths.append(root / "LoveAV-Data" / "config" / "tools.json")
    paths.append(Path.home() / "LoveAV-Data" / "config" / "tools.json")
    return list(dict.fromkeys(path.resolve(strict=False) for path in paths))


def _configured_tgctl(config_path: Path) -> Path | None:
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AdapterError(
            "INVALID_CONFIG",
            "LoveAV TG Exporter 配置文件无法读取。",
            {"config": str(config_path), "error": type(exc).__name__},
        ) from exc
    if not isinstance(payload, dict):
        raise AdapterError("INVALID_CONFIG", "LoveAV TG Exporter 配置顶层必须是 JSON object。")
    value = payload.get("tgctl_path")
    section = payload.get("tg_exporter")
    if value is None and isinstance(section, dict):
        value = section.get("tgctl_path")
    if value in {None, ""}:
        return None
    if not isinstance(value, str):
        raise AdapterError("INVALID_CONFIG", "tgctl_path 必须是字符串。")
    return Path(os.path.expandvars(value)).expanduser().resolve(strict=False)


def _release_candidates() -> list[Path]:
    candidates: list[Path] = []
    loveav_root = Path(__file__).resolve().parent.parent
    patterns = [
        loveav_root / "tools" / "tg-exporter" / "dist",
        *(root / "tg-exporter" / "dist" for root in _candidate_roots()),
    ]
    for dist in dict.fromkeys(path.resolve(strict=False) for path in patterns):
        if not dist.is_dir():
            continue
        for path in dist.glob("release-v*/tgctl.exe"):
            if path.is_file() and "candidate" not in str(path).casefold():
                candidates.append(path.resolve())
    return list(dict.fromkeys(candidates))


def locate_tgctl(explicit: str | Path | None = None, config: str | Path | None = None) -> LocatedTgctl:
    if explicit:
        path = Path(explicit).expanduser().resolve(strict=False)
        if not path.is_file():
            raise AdapterError("TGCTL_NOT_FOUND", "指定的 tgctl 不存在。", {"path": str(path)})
        return LocatedTgctl(path, "explicit", _infer_version_from_path(path))

    config_paths = [Path(config).expanduser().resolve(strict=False)] if config else _default_config_paths()
    for config_path in config_paths:
        if not config_path.is_file():
            continue
        configured = _configured_tgctl(config_path)
        if configured is None:
            continue
        if not configured.is_file():
            raise AdapterError(
                "TGCTL_NOT_FOUND",
                "LoveAV 私人配置指向的 tgctl 不存在。",
                {"config": str(config_path), "path": str(configured)},
            )
        return LocatedTgctl(configured, "config", _infer_version_from_path(configured))

    releases = _release_candidates()
    if releases:
        releases.sort(key=lambda path: _version_tuple(_infer_version_from_path(path)) or (0, 0, 0), reverse=True)
        path = releases[0]
        return LocatedTgctl(path, "release", _infer_version_from_path(path))

    path_value = shutil.which("tgctl.exe") or shutil.which("tgctl")
    if path_value:
        path = Path(path_value).resolve()
        return LocatedTgctl(path, "path", _infer_version_from_path(path))

    raise AdapterError(
        "TGCTL_NOT_FOUND",
        "未找到可用的 tgctl。请安装 TG Exporter 正式版，或在 LoveAV 私人配置中设置 tgctl_path。",
    )


def _default_runner(command: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    kwargs: dict[str, Any] = {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": timeout,
        "check": False,
        "shell": False,
    }
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run(command, **kwargs)


def run_tgctl_json(
    executable: Path,
    arguments: list[str],
    *,
    timeout: float = 120.0,
    runner: Runner = _default_runner,
) -> dict[str, Any]:
    try:
        completed = runner([str(executable), *arguments], timeout)
    except subprocess.TimeoutExpired as exc:
        raise AdapterError("TGCTL_TIMEOUT", "tgctl 请求超时。", {"timeout_seconds": timeout}) from exc
    except OSError as exc:
        raise AdapterError("TGCTL_START_FAILED", "tgctl 无法启动。", {"error": type(exc).__name__}) from exc

    stdout = completed.stdout.strip()
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise AdapterError(
            "TGCTL_INVALID_JSON",
            "tgctl 没有返回有效的 JSON。",
            {"exit_code": completed.returncode, "stderr_present": bool(completed.stderr.strip())},
        ) from exc
    if not isinstance(payload, dict):
        raise AdapterError("TGCTL_INVALID_JSON", "tgctl JSON 顶层必须是 object。")
    if completed.returncode != 0 or payload.get("ok") is not True:
        error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
        raise AdapterError(
            str(error.get("code") or "TGCTL_FAILED"),
            str(error.get("message") or "tgctl 请求失败。"),
            {"exit_code": completed.returncode, "tgctl_details": error.get("details")},
        )
    return payload


def version_info(located: LocatedTgctl, *, runner: Runner = _default_runner, timeout: float = 30.0) -> dict[str, Any]:
    try:
        payload = run_tgctl_json(located.path, ["version", "--json"], timeout=timeout, runner=runner)
        data = payload.get("data")
        if not isinstance(data, dict):
            raise AdapterError("TGCTL_INVALID_VERSION", "tgctl version 缺少 data object。")
        version = str(data.get("tgctl_version") or "") or None
        reader_schema = str(data.get("reader_schema") or "") or None
        source = "command"
    except AdapterError as exc:
        if exc.code != "INVALID_ARGUMENT" or not located.inferred_version:
            raise
        version = located.inferred_version
        reader_schema = EXPECTED_READER_SCHEMA
        source = "release_path_legacy"

    parsed = _version_tuple(version)
    if parsed is None:
        raise AdapterError("TGCTL_INVALID_VERSION", "无法识别 tgctl 版本。")
    if parsed < MINIMUM_TGCTL_VERSION:
        raise AdapterError(
            "TGCTL_UPGRADE_REQUIRED",
            "tgctl 版本过旧。",
            {"detected": _version_text(parsed), "minimum": _version_text(MINIMUM_TGCTL_VERSION)},
        )
    if reader_schema != EXPECTED_READER_SCHEMA:
        raise AdapterError(
            "TGCTL_SCHEMA_INCOMPATIBLE",
            "tgctl Reader Schema 与 LoveAV 不兼容。",
            {"detected": reader_schema, "expected": EXPECTED_READER_SCHEMA},
        )
    return {
        "version": _version_text(parsed),
        "reader_schema": reader_schema,
        "source": source,
    }


def health_check(located: LocatedTgctl, *, runner: Runner = _default_runner, timeout: float = 30.0) -> dict[str, Any]:
    version = version_info(located, runner=runner, timeout=timeout)
    payload = run_tgctl_json(located.path, ["status", "--json"], timeout=timeout, runner=runner)
    data = payload.get("data")
    if not isinstance(data, dict):
        raise AdapterError("TGCTL_INVALID_STATUS", "tgctl status 缺少 data object。")
    return {
        "schema": ADAPTER_SCHEMA,
        "ok": True,
        "executable_source": located.source,
        "tgctl_version": data.get("tgctl_version") or version["version"],
        "daemon_version": data.get("daemon_version"),
        "reader_schema": data.get("reader_schema") or version["reader_schema"],
        "ipc_protocol": data.get("ipc_protocol"),
        "compatible": bool(data.get("compatible", True)),
        "same_version": data.get("same_version"),
        "authorized": bool(data.get("authorized")),
        "state": data.get("state") or ("connected" if data.get("authorized") else "idle"),
        "export_active": bool(data.get("export_active", False)),
        "queued_reads": int(data.get("queued_reads", 0) or 0),
        "capabilities": list(data.get("capabilities") or []),
        "hint": data.get("hint"),
    }


def _message_key(item: dict[str, Any]) -> tuple[Any, Any] | None:
    message_id = item.get("message_id", item.get("id"))
    source_chat_id = item.get("source_chat_id", item.get("chat_id"))
    if message_id is None or source_chat_id is None:
        return None
    return source_chat_id, message_id


def _command_arguments(mode: str, query: dict[str, Any], cursor: str | None, limit: int) -> list[str]:
    if mode == "history":
        arguments = ["messages", "history", "--chat", str(query["chat"]), "--limit", str(limit)]
        for flag in ("since", "until"):
            if query.get(flag):
                arguments.extend([f"--{flag}", str(query[flag])])
    elif mode == "search":
        arguments = ["messages", "search", "--limit", str(limit)]
        option_names = {
            "chat": "--chat",
            "contains": "--contains",
            "regex": "--regex",
            "sender_id": "--sender-id",
            "sender_role": "--sender-role",
            "since": "--since",
            "until": "--until",
            "message_type": "--message-type",
            "topic_id": "--topic",
            "has_link": "--has-link",
            "url_domain": "--url-domain",
        }
        for name, flag in option_names.items():
            value = query.get(name)
            if value not in {None, ""}:
                arguments.extend([flag, str(value)])
        if query.get("case_sensitive"):
            arguments.append("--case-sensitive")
    else:
        raise AdapterError("INVALID_ARGUMENT", "仅支持 history 或 search 分页。")
    if cursor:
        arguments.extend(["--cursor", cursor])
    arguments.append("--json")
    return arguments


def collect_pages(
    located: LocatedTgctl,
    *,
    mode: str,
    query: dict[str, Any],
    total_limit: int,
    page_size: int = MAX_PAGE_SIZE,
    timeout: float = 120.0,
    runner: Runner = _default_runner,
) -> dict[str, Any]:
    if total_limit < 1 or total_limit > MAX_PAGE_SIZE * MAX_PAGES:
        raise AdapterError("INVALID_ARGUMENT", f"total_limit 必须在 1 到 {MAX_PAGE_SIZE * MAX_PAGES} 之间。")
    if page_size < 1 or page_size > MAX_PAGE_SIZE:
        raise AdapterError("INVALID_ARGUMENT", f"page_size 必须在 1 到 {MAX_PAGE_SIZE} 之间。")
    if mode == "history" and not query.get("chat"):
        raise AdapterError("INVALID_ARGUMENT", "history 必须指定 chat。")

    items: list[dict[str, Any]] = []
    seen_messages: set[tuple[Any, Any]] = set()
    cursor: str | None = None
    seen_cursors: set[str] = set()
    pages = 0
    duplicates = 0
    identity_missing = 0
    source_exhausted = False

    while len(items) < total_limit:
        if pages >= MAX_PAGES:
            raise AdapterError(
                "PAGE_LIMIT_EXCEEDED",
                "tgctl 分页超过安全上限。",
                {"pages_completed": pages, "items_collected": len(items)},
            )
        request_limit = min(page_size, total_limit - len(items))
        arguments = _command_arguments(mode, query, cursor, request_limit)
        try:
            payload = run_tgctl_json(located.path, arguments, timeout=timeout, runner=runner)
        except AdapterError as exc:
            raise AdapterError(
                exc.code,
                exc.message,
                {**exc.details, "pages_completed": pages, "items_collected": len(items)},
            ) from exc
        data = payload.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            raise AdapterError(
                "TGCTL_INVALID_PAGE",
                "tgctl 分页缺少 data.items。",
                {"pages_completed": pages, "items_collected": len(items)},
            )
        pages += 1
        for raw_item in data["items"]:
            if not isinstance(raw_item, dict):
                raise AdapterError("TGCTL_INVALID_PAGE", "tgctl 消息项必须是 object。")
            key = _message_key(raw_item)
            if key is None:
                identity_missing += 1
                items.append(raw_item)
            elif key in seen_messages:
                duplicates += 1
            else:
                seen_messages.add(key)
                items.append(raw_item)
            if len(items) >= total_limit:
                break

        has_more = bool(data.get("has_more"))
        next_cursor = data.get("next_cursor")
        if not has_more:
            source_exhausted = True
            cursor = None
            break
        if not isinstance(next_cursor, str) or not next_cursor:
            raise AdapterError(
                "TGCTL_INVALID_PAGE",
                "tgctl 声明 has_more 但没有返回 next_cursor。",
                {"pages_completed": pages, "items_collected": len(items)},
            )
        if next_cursor in seen_cursors:
            raise AdapterError(
                "TGCTL_CURSOR_LOOP",
                "tgctl 返回了重复游标，已停止以避免无限分页。",
                {"pages_completed": pages, "items_collected": len(items)},
            )
        seen_cursors.add(next_cursor)
        cursor = next_cursor

    return {
        "schema": ADAPTER_SCHEMA,
        "ok": True,
        "complete": True,
        "mode": mode,
        "query": query,
        "requested": total_limit,
        "count": len(items),
        "pages": pages,
        "duplicates_removed": duplicates,
        "identity_missing": identity_missing,
        "source_exhausted": source_exhausted,
        "has_more": not source_exhausted and len(items) >= total_limit,
        "next_cursor": cursor if len(items) >= total_limit else None,
        "items": items,
    }


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path = path.expanduser().resolve(strict=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=path.parent, delete=False) as handle:
        handle.write(text)
        temporary = Path(handle.name)
    temporary.replace(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LoveAV 内嵌 TG Exporter 只读适配器")
    parser.add_argument("--tgctl", help="显式指定 tgctl.exe")
    parser.add_argument("--config", help="LoveAV 私人 tools.json")
    parser.add_argument("--timeout", type=float, default=120.0, help="每页超时秒数")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("locate")
    subparsers.add_parser("health")

    def add_page_options(command: argparse.ArgumentParser, *, chat_required: bool) -> None:
        command.add_argument("--chat", required=chat_required)
        command.add_argument("--total-limit", type=int, required=True)
        command.add_argument("--page-size", type=int, default=MAX_PAGE_SIZE)
        command.add_argument("--since")
        command.add_argument("--until")
        command.add_argument("--output", help="只在用户明确需要保存原始分页结果时使用")

    history = subparsers.add_parser("history")
    add_page_options(history, chat_required=True)

    search = subparsers.add_parser("search")
    add_page_options(search, chat_required=False)
    search.add_argument("--contains")
    search.add_argument("--regex")
    search.add_argument("--sender-id", type=int)
    search.add_argument("--sender-role", choices=["owner", "admin", "member"])
    search.add_argument("--message-type")
    search.add_argument("--topic-id", type=int)
    search.add_argument("--has-link", choices=["yes", "no", "all"], default="all")
    search.add_argument("--url-domain")
    search.add_argument("--case-sensitive", action="store_true")
    return parser


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        located = locate_tgctl(args.tgctl, args.config)
        if args.command == "locate":
            payload = {
                "schema": ADAPTER_SCHEMA,
                "ok": True,
                "source": located.source,
                "inferred_version": located.inferred_version,
                "path": str(located.path),
            }
        elif args.command == "health":
            payload = health_check(located, timeout=min(args.timeout, 30.0))
        else:
            health = health_check(located, timeout=min(args.timeout, 30.0))
            if not health["compatible"]:
                raise AdapterError("TGCTL_INCOMPATIBLE", "tgctl 与当前 LoveAV 适配器不兼容。")
            if not health["authorized"]:
                raise AdapterError("NOT_AUTHORIZED", "Telegram 尚未登录，请先打开 TG Exporter GUI 完成登录。")
            query = {
                key: getattr(args, key)
                for key in (
                    "chat",
                    "since",
                    "until",
                    "contains",
                    "regex",
                    "sender_id",
                    "sender_role",
                    "message_type",
                    "topic_id",
                    "has_link",
                    "url_domain",
                    "case_sensitive",
                )
                if hasattr(args, key) and getattr(args, key) not in {None, ""}
            }
            payload = collect_pages(
                located,
                mode=args.command,
                query=query,
                total_limit=args.total_limit,
                page_size=args.page_size,
                timeout=args.timeout,
            )
            payload["tgctl"] = {
                "version": health["tgctl_version"],
                "daemon_version": health["daemon_version"],
                "reader_schema": health["reader_schema"],
                "same_version": health["same_version"],
            }
            if args.output:
                _write_json_atomic(Path(args.output), payload)
        _emit(payload)
        return 0
    except AdapterError as exc:
        _emit({"schema": ADAPTER_SCHEMA, "ok": False, "error": {"code": exc.code, "message": exc.message, "details": exc.details}})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
