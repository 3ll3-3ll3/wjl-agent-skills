from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "plan_pikpak_notification_redeem.py"
SPEC = importlib.util.spec_from_file_location("plan_pikpak_notification_redeem", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def row(chat_id: int, message_id: int, text: str) -> dict:
    return {
        "chat_id": chat_id,
        "message_id": message_id,
        "date": "2026-09-08T10:00:00+08:00",
        "text": text,
        "caption": None,
    }


def test_two_sources_with_same_keyword_create_one_job_and_keep_both_origins() -> None:
    plan = MODULE.build_plan(
        [
            ("pikpak_notice_updates", [row(-1001, 10, "资源更新：#在下王老师")]),
            ("pikpak_notice_share", [row(-1002, 20, "回复关键词：在下王老师")]),
        ]
    )

    assert plan["summary"]["input_messages"] == 2
    assert plan["summary"]["keyword_occurrences"] == 2
    assert plan["summary"]["unique_keywords"] == 1
    assert plan["summary"]["deduplicated_keyword_occurrences"] == 1
    assert plan["jobs"][0]["send_text"] == "#在下王老师"
    assert {(ref["chat_id"], ref["message_id"]) for ref in plan["jobs"][0]["source_messages"]} == {
        (-1001, 10),
        (-1002, 20),
    }


def test_ascii_keyword_comparison_is_case_insensitive_and_nfkc_normalized() -> None:
    plan = MODULE.build_plan(
        [
            ("a", [row(-1001, 1, "提取关键词：#ＳｅｘＣａｔ０７")]),
            ("b", [row(-1002, 2, "#sexcat07")]),
        ]
    )

    assert plan["summary"]["unique_keywords"] == 1
    assert plan["jobs"][0]["keyword_key"] == "sexcat07"
    assert plan["jobs"][0]["send_text"] == "#SexCat07"


def test_unambiguous_single_hashtag_is_allowed() -> None:
    plan = MODULE.build_plan([("a", [row(-1001, 1, "新资源已经发布 #Moonstar")])])

    assert plan["summary"]["unique_keywords"] == 1
    assert plan["jobs"][0]["send_text"] == "#Moonstar"
    assert not plan["review"]


def test_ambiguous_or_missing_keyword_goes_to_review_without_body_persistence() -> None:
    plan = MODULE.build_plan(
        [
            ("a", [row(-1001, 1, "可能是 #Alpha，也可能是 #Beta")]),
            ("b", [row(-1002, 2, "没有明确提取词的普通通知")]),
        ]
    )

    assert plan["summary"]["unique_keywords"] == 0
    assert plan["summary"]["review_messages"] == 2
    rendered = str(plan)
    assert "可能是" not in rendered
    assert "普通通知" not in rendered


def test_same_message_row_is_not_processed_twice() -> None:
    duplicate = row(-1001, 9, "回复关键词：#quru")
    plan = MODULE.build_plan([("a", [duplicate, duplicate])])

    assert plan["summary"]["input_messages"] == 2
    assert plan["summary"]["duplicate_message_rows"] == 1
    assert plan["summary"]["unique_keywords"] == 1


def test_ack_policy_never_allows_ack_before_save() -> None:
    plan = MODULE.build_plan([("a", [row(-1001, 1, "回复关键词：#demo")])])

    assert plan["ack_policy"] == {
        "mode": "per_source_frozen_range_all_success_or_safe_contiguous_prefix",
        "ack_before_resources_saved": False,
        "snapshot_after_messages_excluded": True,
    }


if __name__ == "__main__":
    tests = [value for name, value in globals().items() if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
    print(f"{len(tests)} tests passed")
