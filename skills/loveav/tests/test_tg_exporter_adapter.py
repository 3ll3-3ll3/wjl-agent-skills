from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "tg_exporter_adapter.py"
SPEC = importlib.util.spec_from_file_location("loveav_tg_exporter_adapter", SCRIPT)
assert SPEC and SPEC.loader
adapter = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = adapter
SPEC.loader.exec_module(adapter)


def completed(arguments: list[str], payload: dict, returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(arguments, returncode, json.dumps(payload, ensure_ascii=False), "")


def test_explicit_location_has_highest_priority(tmp_path: Path) -> None:
    executable = tmp_path / "release-v0.3.2" / "tgctl.exe"
    executable.parent.mkdir()
    executable.write_bytes(b"test")

    located = adapter.locate_tgctl(executable)

    assert located.path == executable.resolve()
    assert located.source == "explicit"
    assert located.inferred_version == "0.3.2"


def test_private_config_location_is_supported(tmp_path: Path) -> None:
    executable = tmp_path / "release-v0.3.2" / "tgctl.exe"
    executable.parent.mkdir()
    executable.write_bytes(b"test")
    config = tmp_path / "tools.json"
    config.write_text(json.dumps({"tg_exporter": {"tgctl_path": str(executable)}}), encoding="utf-8")

    located = adapter.locate_tgctl(config=config)

    assert located.path == executable.resolve()
    assert located.source == "config"


def test_health_supports_formal_v032_release_path_fallback(tmp_path: Path) -> None:
    executable = tmp_path / "release-v0.3.2" / "tgctl.exe"
    executable.parent.mkdir()
    executable.write_bytes(b"test")
    located = adapter.LocatedTgctl(executable, "release", "0.3.2")

    def runner(command: list[str], _timeout: float):
        if command[1] == "version":
            return completed(
                command,
                {"ok": False, "error": {"code": "INVALID_ARGUMENT", "message": "unknown command"}},
                2,
            )
        assert command[1:] == ["status", "--json"]
        return completed(command, {"ok": True, "data": {"authorized": True, "session": "%APPDATA%\\..."}})

    result = adapter.health_check(located, runner=runner)

    assert result["ok"] is True
    assert result["authorized"] is True
    assert result["tgctl_version"] == "0.3.2"
    assert result["reader_schema"] == "tgctl.reader.v1"
    assert "session" not in result


def test_collects_two_pages_and_removes_boundary_duplicate(tmp_path: Path) -> None:
    located = adapter.LocatedTgctl(tmp_path / "tgctl.exe", "test", "0.3.3")
    calls: list[list[str]] = []

    def runner(command: list[str], _timeout: float):
        calls.append(command)
        if "--cursor" not in command:
            return completed(
                command,
                {
                    "ok": True,
                    "data": {
                        "items": [
                            {"chat_id": -1, "source_chat_id": -1, "message_id": 3},
                            {"chat_id": -1, "source_chat_id": -1, "message_id": 2},
                        ],
                        "has_more": True,
                        "next_cursor": "page-2",
                    },
                },
            )
        return completed(
            command,
            {
                "ok": True,
                "data": {
                    "items": [
                        {"chat_id": -1, "source_chat_id": -1, "message_id": 2},
                        {"chat_id": -1, "source_chat_id": -1, "message_id": 1},
                    ],
                    "has_more": False,
                    "next_cursor": None,
                },
            },
        )

    result = adapter.collect_pages(
        located,
        mode="history",
        query={"chat": "-1"},
        total_limit=4,
        page_size=2,
        runner=runner,
    )

    assert [item["message_id"] for item in result["items"]] == [3, 2, 1]
    assert result["pages"] == 2
    assert result["duplicates_removed"] == 1
    assert result["source_exhausted"] is True
    assert "--cursor" in calls[1]
    assert calls[1][calls[1].index("--cursor") + 1] == "page-2"


def test_later_page_failure_is_not_reported_as_complete(tmp_path: Path) -> None:
    located = adapter.LocatedTgctl(tmp_path / "tgctl.exe", "test", "0.3.3")
    call_count = 0

    def runner(command: list[str], _timeout: float):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return completed(
                command,
                {
                    "ok": True,
                    "data": {
                        "items": [{"chat_id": -1, "message_id": 2}],
                        "has_more": True,
                        "next_cursor": "page-2",
                    },
                },
            )
        return completed(
            command,
            {"ok": False, "error": {"code": "FLOOD_WAIT", "message": "wait", "details": {"retry_after_seconds": 5}}},
            6,
        )

    with pytest.raises(adapter.AdapterError) as exc_info:
        adapter.collect_pages(
            located,
            mode="history",
            query={"chat": "-1"},
            total_limit=2,
            page_size=1,
            runner=runner,
        )

    assert exc_info.value.code == "FLOOD_WAIT"
    assert exc_info.value.details["pages_completed"] == 1
    assert exc_info.value.details["items_collected"] == 1


def test_repeated_cursor_stops_instead_of_looping(tmp_path: Path) -> None:
    located = adapter.LocatedTgctl(tmp_path / "tgctl.exe", "test", "0.3.3")

    def runner(command: list[str], _timeout: float):
        return completed(
            command,
            {"ok": True, "data": {"items": [], "has_more": True, "next_cursor": "same"}},
        )

    with pytest.raises(adapter.AdapterError) as exc_info:
        adapter.collect_pages(
            located,
            mode="history",
            query={"chat": "-1"},
            total_limit=2,
            page_size=1,
            runner=runner,
        )

    assert exc_info.value.code == "TGCTL_CURSOR_LOOP"


def test_forward_defaults_to_dry_run_and_preserves_message_ids(tmp_path: Path) -> None:
    located = adapter.LocatedTgctl(tmp_path / "tgctl.exe", "test", "0.3.3")
    calls: list[list[str]] = []

    def runner(command: list[str], _timeout: float):
        calls.append(command)
        return completed(command, {"ok": True, "data": {"planned": 2}})

    result = adapter.forward_messages(
        located,
        source_chat="-1001",
        destination_chat="-1002",
        message_ids=[10, 11, 10],
        runner=runner,
    )

    assert result["dry_run"] is True
    assert result["message_ids"] == [10, 11]
    assert "--dry-run" in calls[0]
    assert calls[0][-1] == "--json"


def test_forward_requires_exact_confirmation_for_real_write(tmp_path: Path) -> None:
    located = adapter.LocatedTgctl(tmp_path / "tgctl.exe", "test", "0.3.3")
    calls: list[list[str]] = []

    def runner(command: list[str], _timeout: float):
        calls.append(command)
        return completed(command, {"ok": True, "data": {"forwarded": 21}})

    result = adapter.forward_messages(
        located,
        source_chat="-1001",
        destination_chat="-1002",
        message_ids=list(range(1, 22)),
        confirmation=adapter.FORWARD_CONFIRMATION,
        runner=runner,
    )

    assert result["dry_run"] is False
    assert "--dry-run" not in calls[0]
    assert "--allow-large-batch" in calls[0]


def test_forward_rejects_more_than_two_hundred_messages(tmp_path: Path) -> None:
    located = adapter.LocatedTgctl(tmp_path / "tgctl.exe", "test", "0.3.3")
    with pytest.raises(adapter.AdapterError) as exc_info:
        adapter.forward_messages(
            located,
            source_chat="-1001",
            destination_chat="-1002",
            message_ids=list(range(1, 202)),
        )
    assert exc_info.value.code == "FORWARD_BATCH_TOO_LARGE"


def test_collect_unread_reuses_signed_snapshot_across_pages(tmp_path: Path) -> None:
    located = adapter.LocatedTgctl(tmp_path / "tgctl.exe", "test", "0.3.3")
    calls: list[list[str]] = []

    def runner(command: list[str], _timeout: float):
        calls.append(command)
        if "--cursor" not in command:
            return completed(command, {"ok": True, "data": {
                "lower": 10, "upper": 12, "unread_count": 2, "snapshot_token": "signed",
                "items": [{"chat_id": -1, "message_id": 11}], "has_more": True, "next_cursor": "p2",
            }})
        return completed(command, {"ok": True, "data": {
            "lower": 10, "upper": 12, "unread_count": 2, "snapshot_token": "signed",
            "items": [{"chat_id": -1, "message_id": 12}], "has_more": False, "next_cursor": None,
        }})

    result = adapter.collect_unread_snapshot(located, chat="-1", page_size=1, runner=runner)
    assert [row["message_id"] for row in result["items"]] == [11, 12]
    assert result["snapshot_token"] == "signed"
    assert calls[1][calls[1].index("--cursor") + 1] == "p2"


def test_collect_unread_rejects_changed_snapshot(tmp_path: Path) -> None:
    located = adapter.LocatedTgctl(tmp_path / "tgctl.exe", "test", "0.3.3")
    count = 0

    def runner(command: list[str], _timeout: float):
        nonlocal count
        count += 1
        return completed(command, {"ok": True, "data": {
            "lower": 10, "upper": 12 + count, "unread_count": 2, "snapshot_token": f"signed-{count}",
            "items": [], "has_more": count == 1, "next_cursor": "p2" if count == 1 else None,
        }})

    with pytest.raises(adapter.AdapterError) as exc_info:
        adapter.collect_unread_snapshot(located, chat="-1", page_size=1, runner=runner)
    assert exc_info.value.code == "TGCTL_SNAPSHOT_CHANGED"


def test_redeem_adapter_defaults_to_dry_run_and_real_write_needs_exact_confirmation(tmp_path: Path) -> None:
    located = adapter.LocatedTgctl(tmp_path / "tgctl.exe", "test", "0.3.3")
    calls: list[list[str]] = []

    def runner(command: list[str], _timeout: float):
        calls.append(command)
        return completed(command, {"ok": True, "data": {"captured": [], "captured_count": 0}})

    adapter.send_and_capture(located, destination_chat="-1", text="#demo", runner=runner)
    adapter.send_and_capture(
        located,
        destination_chat="-1",
        text="#demo",
        confirmation=adapter.REDEEM_CONFIRMATION,
        runner=runner,
    )
    assert "--dry-run" in calls[0]
    assert "--dry-run" not in calls[1]
