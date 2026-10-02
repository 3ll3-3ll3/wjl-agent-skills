from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPTS = Path(__file__).parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
SCRIPT = SCRIPTS / "run_pikpak_notification_redeem.py"
SPEC = importlib.util.spec_from_file_location("run_pikpak_notification_redeem", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def row(chat_id: int, message_id: int, text: str) -> dict:
    return {"chat_id": chat_id, "message_id": message_id, "text": text, "caption": None}


def sources() -> dict:
    return {
        "pikpak_notice_updates": {"chat_id": -1001},
        "pikpak_notice_share": {"chat_id": -1002},
        "pikpak_extraction_group": {"chat_id": -1003},
        "pikpak_collection_group": {"chat_id": -1004},
    }


def test_captured_duplicate_resources_prefer_password_and_detect_conflict() -> None:
    resources, conflict = MODULE._capture_resources(
        [
            row(-1003, 1, "标题\nhttps://mypikpak.com/s/ABC"),
            row(-1003, 2, "标题\nhttps://mypikpak.com/s/ABC\n密码: 7788"),
        ],
        "demo",
    )
    assert conflict is None
    assert len(resources) == 1
    assert resources[0]["password"] == "7788"

    resources, conflict = MODULE._capture_resources(
        [
            row(-1003, 1, "https://mypikpak.com/s/ABC 密码: 1111"),
            row(-1003, 2, "https://mypikpak.com/s/ABC 密码: 2222"),
        ],
        "demo",
    )
    assert resources == []
    assert conflict == "password_conflict"


def test_message_success_requires_all_keywords_and_review_never_succeeds() -> None:
    snapshots = {
        "a": {"items": [row(-1, 10, "a"), row(-1, 11, "b")]},
    }
    plan = {
        "jobs": [
            {"keyword_key": "one", "source_messages": [{"source_key": "a", "message_id": 10}]},
            {"keyword_key": "two", "source_messages": [{"source_key": "a", "message_id": 10}]},
        ],
        "review": [{"source_key": "a", "message_id": 11}],
    }
    status = MODULE._message_success_map(snapshots, plan, {"one": True, "two": False})
    assert status == {"a": {10: False, 11: False}}


def test_ack_defaults_to_all_or_none_and_optional_prefix_stops_before_failure() -> None:
    snapshot = {"lower": 9, "upper": 13, "count": 3, "unread_count": 3}
    assert MODULE._safe_ack_max(snapshot, {10: True, 11: False, 12: True}, allow_prefix=False) is None
    assert MODULE._safe_ack_max(snapshot, {10: True, 11: False, 12: True}, allow_prefix=True) == 10
    assert MODULE._safe_ack_max(snapshot, {10: True, 11: True, 12: True}, allow_prefix=False) == 13


def test_ack_refuses_when_loaded_count_does_not_match_telegram_unread_count() -> None:
    snapshot = {"lower": 9, "upper": 13, "count": 2, "unread_count": 3}
    assert MODULE._safe_ack_max(snapshot, {10: True, 11: True}, allow_prefix=True) is None


def test_dry_run_freezes_both_sources_but_never_sends_or_marks_read(monkeypatch) -> None:
    snapshots = {
        "-1001": {
            "lower": 9,
            "upper": 10,
            "unread_count": 1,
            "snapshot_token": "a",
            "pages": 1,
            "count": 1,
            "items": [row(-1001, 10, "资源更新：#demo")],
        },
        "-1002": {
            "lower": 19,
            "upper": 20,
            "unread_count": 1,
            "snapshot_token": "b",
            "pages": 1,
            "count": 1,
            "items": [row(-1002, 20, "回复关键词：demo")],
        },
    }
    monkeypatch.setattr(
        MODULE.adapter,
        "health_check",
        lambda *_args, **_kwargs: {
            "compatible": True,
            "authorized": True,
            "export_active": False,
            "capabilities": list(MODULE.adapter.REDEEM_CAPABILITIES),
        },
    )
    monkeypatch.setattr(
        MODULE.adapter,
        "collect_unread_snapshot",
        lambda _located, *, chat, **_kwargs: snapshots[chat],
    )
    monkeypatch.setattr(MODULE.adapter, "send_and_capture", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("send")))
    monkeypatch.setattr(MODULE.adapter, "mark_unread_snapshot_read", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("ack")))

    result = MODULE.execute(
        located=MODULE.adapter.LocatedTgctl(Path("tgctl.exe"), "test", "0.3.3"),
        private_sources=sources(),
        confirmation=None,
    )

    assert result["dry_run"] is True
    assert result["plan_summary"]["unique_keywords"] == 1
    assert result["jobs"] == [{"keyword_key": "demo", "status": "planned", "resource_count": None}]
    assert all(value["reason"] == "dry_run" for value in result["acknowledgements"].values())


def test_write_outcome_unknown_stops_and_never_marks_read(monkeypatch) -> None:
    snapshots = {
        "-1001": {"lower": 9, "upper": 10, "unread_count": 1, "snapshot_token": "a", "pages": 1, "count": 1, "items": [row(-1001, 10, "#one")]},
        "-1002": {"lower": 19, "upper": 20, "unread_count": 1, "snapshot_token": "b", "pages": 1, "count": 1, "items": [row(-1002, 20, "#two")]},
    }
    monkeypatch.setattr(MODULE.adapter, "health_check", lambda *_a, **_k: {"compatible": True, "authorized": True, "export_active": False, "capabilities": list(MODULE.adapter.REDEEM_CAPABILITIES)})
    monkeypatch.setattr(MODULE.adapter, "collect_unread_snapshot", lambda _located, *, chat, **_kwargs: snapshots[chat])

    def unknown(*_args, **_kwargs):
        raise MODULE.adapter.AdapterError("WRITE_OUTCOME_UNKNOWN", "unknown")

    monkeypatch.setattr(MODULE.adapter, "send_and_capture", unknown)
    monkeypatch.setattr(MODULE.adapter, "mark_unread_snapshot_read", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("ack")))
    result = MODULE.execute(
        located=MODULE.adapter.LocatedTgctl(Path("tgctl.exe"), "test", "0.3.3"),
        private_sources=sources(),
        confirmation=MODULE.adapter.REDEEM_CONFIRMATION,
    )
    assert result["fatal_error"]["code"] == "WRITE_OUTCOME_UNKNOWN"
    assert all(not value["confirmed"] for value in result["acknowledgements"].values())
