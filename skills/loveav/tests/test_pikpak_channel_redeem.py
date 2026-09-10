from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path


SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SCRIPT = SCRIPTS / "redeem_pikpak_channel_buttons.py"
SPEC = importlib.util.spec_from_file_location("redeem_pikpak_channel_buttons", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _parent(message_id: int) -> dict:
    return {
        "source_chat_id": -1001234567890,
        "message_id": message_id,
        "text": f"频道资源 {message_id}",
        "buttons": [],
    }


def _reply(message_id: int, parent_id: int, *buttons: dict) -> dict:
    return {
        "source_chat_id": -1009999999999,
        "message_id": message_id,
        "discussion_parent_message_id": parent_id,
        "text": "插眼成功！",
        "buttons": list(buttons),
    }


def test_plan_deduplicates_same_start_payload_and_keeps_all_parents() -> None:
    url = "https://t.me/resource_bot?start=opaque-token"
    plan = MODULE.build_plan(
        [
            _parent(10),
            _parent(11),
            _reply(101, 10, {"type": "url", "text": "查看", "url": url}),
            _reply(102, 11, {"type": "url", "text": "查看", "url": url}),
        ],
        "resource_bot",
    )

    assert plan["summary"] == {
        "channel_posts": 2,
        "posts_with_start_link": 2,
        "posts_without_start_link": 0,
        "unique_start_jobs": 1,
    }
    assert plan["jobs"][0]["parent_ids"] == [10, 11]


def test_plan_ignores_other_bots_and_non_start_buttons() -> None:
    plan = MODULE.build_plan(
        [
            _parent(10),
            _reply(
                101,
                10,
                {"type": "url", "text": "错误 Bot", "url": "https://t.me/other_bot?start=secret"},
                {"type": "url", "text": "无 start", "url": "https://t.me/resource_bot"},
                {"type": "url", "text": "资源", "url": "https://mypikpak.com/s/public"},
            ),
        ],
        "resource_bot",
    )

    assert plan["jobs"] == []
    assert plan["summary"]["posts_without_start_link"] == 1


def test_dry_run_summary_never_exposes_start_payload(monkeypatch, tmp_path: Path) -> None:
    secret_payload = "never-show-this-value"
    monkeypatch.setattr(
        MODULE,
        "_load_source",
        lambda _config, _key: {
            "chat_id": "-1001234567890",
            "resource_bot_username": "resource_bot",
        },
    )
    monkeypatch.setattr(
        MODULE.archive,
        "_fetch_live",
        lambda *_args, **_kwargs: {
            "items": [
                _parent(10),
                _reply(
                    101,
                    10,
                    {
                        "type": "url",
                        "text": "查看",
                        "url": f"https://t.me/resource_bot?start={secret_payload}",
                    },
                ),
            ],
            "comment_messages": 1,
        },
    )
    args = argparse.Namespace(
        config=tmp_path / "config.json",
        source_key="demo",
        tgctl=None,
        total_limit=100,
        confirm=None,
        output_root=tmp_path,
        folder="demo",
        first_reply_timeout=8.0,
        settle_seconds=2.0,
        pause_seconds=0.0,
        timeout=30.0,
    )

    result = MODULE.execute(args)

    assert result["dry_run"] is True
    assert result["unique_start_jobs"] == 1
    assert secret_payload not in repr(result)
    assert "jobs" not in result
