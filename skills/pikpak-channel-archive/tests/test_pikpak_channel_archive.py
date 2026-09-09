from __future__ import annotations

import csv
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SCRIPT = SCRIPTS / "archive_pikpak_channel.py"
SPEC = importlib.util.spec_from_file_location("archive_pikpak_channel", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def message(message_id: int, text: str, *, entities: list[dict] | None = None, media: dict | None = None) -> dict:
    return {
        "chat_id": -1001234567890,
        "source_chat_id": -1001234567890,
        "message_id": message_id,
        "date": f"2026-09-{message_id:02d}T01:00:00+00:00",
        "edit_date": None,
        "text": text,
        "caption": None,
        "entities": entities or [],
        "media": media,
    }


def payload(*items: dict, exhausted: bool = True) -> dict:
    return {"ok": True, "complete": True, "source_exhausted": exhausted, "items": list(items)}


def test_only_messages_with_pikpak_urls_are_archived() -> None:
    records, summary = MODULE.build_library(
        payload(
            message(1, "每日更新播报，没有直链"),
            message(2, "资源甲\n#主播 #合集\nhttps://mypikpak.com/s/a"),
        ),
        folder="层楼PikPak资源社",
    )
    assert summary["input_messages"] == 2
    assert summary["resource_messages"] == 1
    assert len(records) == 1
    assert records[0]["title"] == "资源甲"
    assert records[0]["password_tag"] == "#无密码"
    assert records[0]["tags"] == ["无密码", "主播", "合集"]


def test_pwd_inside_share_token_is_not_misread_as_password() -> None:
    records, summary = MODULE.build_library(
        payload(message(1, "资源\nhttps://mypikpak.com/s/VOpWD9FOgelsUicSi8wYrl60o2")),
        folder="层楼PikPak资源社",
    )
    assert summary["resources_with_password"] == 0
    assert records[0]["password"] == ""
    assert records[0]["password_status"] == "not_provided"
    assert records[0]["password_tag"] == "#无密码"


def test_hidden_text_url_is_not_lost() -> None:
    records, summary = MODULE.build_library(
        payload(message(1, "点击这里", entities=[{"type": "TextUrl", "url": "https://mypikpak.com/s/hidden"}])),
        folder="层楼PikPak资源社",
    )
    assert len(records) == 1
    assert summary["hidden_pikpak_links"] == 1
    assert records[0]["source_messages"][0]["hidden_link"] is True


def test_duplicate_url_keeps_all_source_messages_but_one_library_row() -> None:
    records, summary = MODULE.build_library(
        payload(
            message(1, "旧标题\nhttps://mypikpak.com/s/a"),
            message(2, "新标题\nhttps://mypikpak.com/s/a"),
        ),
        folder="层楼PikPak资源社",
    )
    assert len(records) == 1
    assert summary["duplicate_url_groups"] == 1
    assert records[0]["title"] == "新标题"
    assert records[0]["source_message_ids"] == [1, 2]
    assert len(records[0]["source_messages"]) == 2


def test_incomplete_history_is_rejected() -> None:
    with unittest.TestCase().assertRaises(MODULE.ArchiveError):
        MODULE.build_library(payload(message(1, "https://mypikpak.com/s/a"), exhausted=False), folder="x")


def test_files_are_atomic_raindrop_compatible_and_hashed() -> None:
    records, summary = MODULE.build_library(
        payload(message(1, "资源\nhttps://mypikpak.com/s/a\n密码：abcd")),
        folder="层楼PikPak资源社",
    )
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        manifest = MODULE.write_archive(records, summary, root)
        assert (root / "current" / "resource-library.jsonl").is_file()
        assert (root / "current" / "resource-library.csv").read_bytes().startswith(b"\xef\xbb\xbf")
        with (root / "current" / "raindrop-full.csv").open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            assert reader.fieldnames == MODULE.RAINDROP_COLUMNS
            row = next(reader)
            assert row["folder"] == "层楼PikPak资源社"
            assert row["url"] == "https://mypikpak.com/s/a"
            assert row["note"].splitlines()[:3] == [
                "https://mypikpak.com/s/a",
                "#有密码",
                "密码：abcd",
            ]
            assert row["note"].count("https://mypikpak.com/s/a") == 1
            assert "有密码" in row["tags"]
        update = Path(manifest["update_dir"])
        with (update / "raindrop-added.csv").open("r", encoding="utf-8-sig", newline="") as handle:
            assert len(list(csv.DictReader(handle))) == 1
        assert manifest["delta"]["added"] == 1
        assert manifest["raindrop_direction"] == "local_to_raindrop_only"
        assert manifest["images_downloaded"] is False
        assert json.loads((root / "current" / "manifest.json").read_text(encoding="utf-8"))["telegram_state_changed"] is False


def test_raindrop_note_puts_link_and_no_password_tag_before_original_message() -> None:
    records, _ = MODULE.build_library(
        payload(message(1, "资源标题\n第一段\nhttps://mypikpak.com/s/a\n第二段")),
        folder="层楼PikPak资源社",
    )
    row = MODULE._raindrop_row(records[0])
    lines = row["note"].splitlines()
    assert lines[:2] == ["https://mypikpak.com/s/a", "#无密码"]
    assert lines.index("资源标题") < lines.index("第一段") < lines.index("第二段")
    assert row["note"].count("https://mypikpak.com/s/a") == 1
    assert "无密码" in row["tags"]


def test_second_run_creates_incremental_delta_and_snapshot() -> None:
    initial, first_summary = MODULE.build_library(
        payload(message(1, "资源甲\nhttps://mypikpak.com/s/a")), folder="层楼PikPak资源社"
    )
    changed, second_summary = MODULE.build_library(
        payload(
            message(1, "资源甲（已更新）\nhttps://mypikpak.com/s/a"),
            message(2, "资源乙\nhttps://mypikpak.com/s/b"),
        ),
        folder="层楼PikPak资源社",
    )
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        MODULE.write_archive(initial, first_summary, root)
        result = MODULE.write_archive(changed, second_summary, root)
        assert result["delta"]["added"] == 1
        assert result["delta"]["updated"] == 1
        assert result["delta"]["removed"] == 0
        assert result["snapshot"] is not None
        assert (Path(result["snapshot"]) / "resource-library.jsonl").is_file()
        with (Path(result["update_dir"]) / "raindrop-added.csv").open(
            "r", encoding="utf-8-sig", newline=""
        ) as handle:
            rows = list(csv.DictReader(handle))
        assert [row["url"] for row in rows] == ["https://mypikpak.com/s/b"]


def test_legacy_layout_is_migrated_into_snapshot() -> None:
    records, summary = MODULE.build_library(
        payload(message(1, "资源\nhttps://mypikpak.com/s/a")), folder="层楼PikPak资源社"
    )
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        old = root / "library" / "resource-library.jsonl"
        old.parent.mkdir(parents=True)
        old.write_bytes(MODULE._json_bytes(records, jsonl=True))
        (root / "raindrop").mkdir()
        (root / "raindrop" / "raindrop-full.csv").write_text("old", encoding="utf-8")
        result = MODULE.write_archive(records, summary, root)
        assert result["legacy_layout_migrated"] is True
        assert not (root / "library").exists()
        assert (Path(result["snapshot"]) / "original-layout" / "library" / "resource-library.jsonl").is_file()


class TestPikpakChannelArchive(unittest.TestCase):
    def test_contract_cases(self) -> None:
        cases = [value for name, value in globals().items() if name.startswith("test_") and callable(value)]
        for case in cases:
            with self.subTest(case=case.__name__):
                case()
