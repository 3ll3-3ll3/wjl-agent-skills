from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "filter_svip_resource_replies.py"
SPEC = importlib.util.spec_from_file_location("filter_svip_resource_replies", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

CHAT_ID = -1001234567890


def message(
    message_id: int,
    *,
    sender: dict | None = None,
    url: str = "https://mypikpak.com/s/example",
    reply: int | None = None,
    photo: bool = False,
) -> dict:
    return {
        "chat_id": CHAT_ID,
        "message_id": message_id,
        "date": "2026-08-31T12:00:00+08:00",
        "sender": sender or {
            "sender_id": None,
            "is_creator": None,
            "is_admin": None,
            "anonymous_admin": False,
            "posted_as_chat_id": None,
            "unknown_reason": "telegram_sender_not_provided",
        },
        "text": url,
        "caption": None,
        "entities": [],
        "reply_to_message_id": reply,
        "media": {"media_type": "photo"} if photo else None,
    }


def classify(*rows: dict) -> dict:
    return MODULE.classify_messages(list(rows), CHAT_ID)


def test_verified_admin_and_owner_enter_main_results() -> None:
    admin = message(1, sender={"sender_id": 10, "is_admin": True, "is_creator": False})
    owner = message(2, sender={"sender_id": 11, "is_admin": True, "is_creator": True})
    result = classify(admin, owner)
    assert result["summary"]["counts"]["verified_moderator"] == 2
    assert [row["classification"] for row in result["results"]["main"]] == [
        "verified_moderator",
        "verified_moderator",
    ]


def test_anonymous_admin_and_current_chat_send_as_enter_main_results() -> None:
    anonymous = message(
        1,
        sender={
            "sender_id": None,
            "is_admin": True,
            "is_creator": None,
            "anonymous_admin": True,
            "posted_as_chat_id": CHAT_ID,
        },
    )
    send_as = message(
        2,
        sender={
            "sender_id": CHAT_ID,
            "is_admin": None,
            "is_creator": None,
            "anonymous_admin": False,
            "posted_as_chat_id": CHAT_ID,
        },
    )
    result = classify(anonymous, send_as)
    assert result["summary"]["counts"]["verified_moderator"] == 2


def test_known_member_is_excluded_even_when_shape_looks_official() -> None:
    row = message(
        1,
        sender={
            "sender_id": 123,
            "is_admin": False,
            "is_creator": False,
            "anonymous_admin": False,
            "posted_as_chat_id": None,
        },
        reply=9,
        photo=True,
    )
    result = classify(row)
    assert result["summary"]["counts"]["excluded_known_member"] == 1
    assert result["results"]["main"] == []


def test_unknown_reply_and_photo_is_trusted_business_inference() -> None:
    result = classify(message(1, reply=9, photo=True))
    row = result["results"]["main"][0]
    assert row["classification"] == "trusted_official_reply"
    assert row["evidence"] == [
        "telegram_omitted_sender",
        "reply_to_message_present",
        "photo_present",
    ]


def test_partial_shape_needs_review_and_no_shape_is_excluded() -> None:
    result = classify(message(1, reply=9), message(2, photo=True), message(3))
    assert result["summary"]["counts"]["needs_review"] == 2
    assert result["summary"]["counts"]["excluded_insufficient_evidence"] == 1


def test_forwarded_unknown_needs_review() -> None:
    row = message(
        1,
        sender={
            "sender_id": None,
            "unknown_reason": "forwarded_message_without_actual_sender",
        },
        reply=9,
        photo=True,
    )
    result = classify(row)
    assert result["results"]["review"][0]["classification"] == "needs_review"


def test_exact_and_subdomain_match_but_lookalike_domain_does_not() -> None:
    exact = message(1, url="https://mypikpak.com/s/a", reply=9, photo=True)
    subdomain = message(2, url="https://cdn.mypikpak.com/s/b", reply=9, photo=True)
    evil = message(3, url="https://mypikpak.com.evil.example/s/c", reply=9, photo=True)
    result = classify(exact, subdomain, evil)
    assert result["summary"]["main"] == 2
    assert result["summary"]["counts"]["excluded_no_pikpak_url"] == 1


def test_url_can_touch_chinese_punctuation() -> None:
    row = message(8, reply=9, photo=True)
    row["text"] = "资源：https://mypikpak.com/s/abc，密码见图"
    result = classify(row)
    assert result["results"]["main"][0]["pikpak_urls"] == ["https://mypikpak.com/s/abc"]


def test_password_after_url_is_bound_to_copyable_resource() -> None:
    row = message(9, reply=9, photo=True)
    row["text"] = "https://mypikpak.com/s/abc密码: cfg8"
    result = classify(row)
    record = result["results"]["main"][0]
    assert record["pikpak_urls"] == ["https://mypikpak.com/s/abc"]
    assert record["pikpak_resources"] == [
        {
            "url": "https://mypikpak.com/s/abc",
            "password": "cfg8",
            "copy_text": "https://mypikpak.com/s/abc 密码: cfg8",
        }
    ]


def test_unlabelled_chinese_text_is_not_absorbed_into_resource() -> None:
    row = message(10, reply=9, photo=True)
    row["text"] = "https://mypikpak.com/s/abc正文说明"
    result = classify(row)
    resource = result["results"]["main"][0]["pikpak_resources"][0]
    assert resource["url"] == "https://mypikpak.com/s/abc"
    assert resource["password"] is None


def test_wrong_chat_is_excluded_before_business_inference() -> None:
    row = message(1, reply=9, photo=True)
    row["chat_id"] = -1009999999999
    result = classify(row)
    assert result["summary"]["counts"]["excluded_wrong_source"] == 1


def test_output_contains_no_raw_body_or_sender_identity() -> None:
    row = message(1, reply=9, photo=True)
    row["text"] = "私密说明 https://mypikpak.com/s/a"
    result = classify(row)
    record = result["results"]["main"][0]
    assert "text" not in record
    assert "caption" not in record
    assert "sender" not in record
    assert record["pikpak_urls"] == ["https://mypikpak.com/s/a"]


class TestSvipResourceReplies(unittest.TestCase):
    """让仓库现有的标准库 unittest 门禁执行上面的契约用例。"""

    def test_all_contract_cases(self) -> None:
        cases = [
            value
            for name, value in globals().items()
            if name.startswith("test_") and callable(value)
        ]
        for case in cases:
            with self.subTest(case=case.__name__):
                case()
