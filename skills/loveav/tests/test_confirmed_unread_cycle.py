from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SCRIPT = SCRIPTS / "run_confirmed_unread_cycle.py"
SPEC = importlib.util.spec_from_file_location("run_confirmed_unread_cycle", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_category_sources_follow_settings_and_require_private_identity() -> None:
    settings = {"group_export_categories": {"-1001": "av", "-1002": "pikpak消息"}}
    config = {
        "sources": {
            "first": {"chat_id": "-1001", "title": "AV一号"},
            "second": {"chat_id": "-1002", "title": "资源群"},
        }
    }
    assert [row["source_key"] for row in MODULE._category_sources(settings, config, "av")] == ["first"]
    with unittest.TestCase().assertRaises(MODULE.CycleError):
        MODULE._category_sources(
            {"group_export_categories": {"-1999": "av"}}, config, "av"
        )


def test_missav_extraction_deduplicates_normalized_codes_and_ignores_noise() -> None:
    messages = [
        {"text": "ABP-123 与 abp 123 https://missav.ai/cn/fc2-ppv-123456"},
        {"text": "普通分辨率 1920x1080，链接 https://example.com/ABC-999"},
    ]
    assert MODULE.extract_missav_codes(messages) == ["FC2-PPV-123456", "ABP-123"]


def test_incremental_merge_keeps_old_and_new_source_messages() -> None:
    old = {
        "canonical_url": "https://mypikpak.com/s/a",
        "source_messages": [
            {
                "message_id": 1,
                "created": "2026-09-01T00:00:00+08:00",
                "message_url": "https://t.me/c/1/1",
                "full_message": "旧消息",
                "password": "",
                "tags": [],
            }
        ],
    }
    new = {
        "canonical_url": "https://mypikpak.com/s/a",
        "source_messages": [
            {
                "message_id": 2,
                "created": "2026-09-10T00:00:00+08:00",
                "message_url": "https://t.me/c/1/2",
                "full_message": "新消息",
                "password": "abcd",
                "tags": ["合集"],
            }
        ],
    }
    merged = MODULE._merge_channel_record(old, new)
    assert merged["source_message_ids"] == [1, 2]
    assert merged["password"] == "abcd"
    assert merged["password_tag"] == "#有密码"
    assert merged["note"] == "新消息"


def test_haijiao_is_silent_in_batch_parser_unless_explicitly_enabled() -> None:
    parser = MODULE.parser()
    default = parser.parse_args(["--confirm-mark-read", MODULE.MARK_READ_CONFIRMATION])
    explicit = parser.parse_args(
        ["--confirm-mark-read", MODULE.MARK_READ_CONFIRMATION, "--include-haijiao"]
    )
    assert default.include_haijiao is False
    assert explicit.include_haijiao is True


class TestConfirmedUnreadCycle(unittest.TestCase):
    def test_contract_cases(self) -> None:
        cases = [value for name, value in globals().items() if name.startswith("test_") and callable(value)]
        for case in cases:
            with self.subTest(case=case.__name__):
                case()
