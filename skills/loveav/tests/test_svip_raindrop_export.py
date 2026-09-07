from __future__ import annotations

import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "export_svip_raindrop_csv.py"
SPEC = importlib.util.spec_from_file_location("export_svip_raindrop_csv", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def record(
    message_id: int = 123,
    *,
    text: str = "资源标题\nhttps://mypikpak.com/s/a\n密码：abcd",
    resources: list[dict] | None = None,
    password_status: str = "bound",
) -> dict:
    return {
        "message_id": message_id,
        "date": "2026-09-07T12:30:00+08:00",
        "message_text": text,
        "message_copy_text": text,
        "classification": "accepted_pikpak_resource",
        "password_status": password_status,
        "pikpak_resources": resources
        or [
            {
                "url": "https://mypikpak.com/s/a",
                "password": "abcd",
                "copy_text": "https://mypikpak.com/s/a 密码: abcd",
            }
        ],
    }


def payload(*records: dict) -> dict:
    return {"ok": True, "data": {"results": {"main": list(records)}}}


def test_one_url_becomes_one_raindrop_row_with_full_message() -> None:
    rows, review, summary = MODULE.export(payload(record()), {}, MODULE.FOLDER)
    assert summary["new"] == 1
    assert review == []
    assert rows[0]["folder"] == "Svip PikPak链接消息"
    assert rows[0]["url"] == "https://mypikpak.com/s/a"
    assert rows[0]["title"] == "资源标题"
    assert "【原消息】\n资源标题" in rows[0]["note"]
    assert "密码：abcd" in rows[0]["note"]
    assert "消息 ID：123" in rows[0]["note"]
    assert rows[0]["created"] == "2026-09-07T12:30:00+08:00"
    assert rows[0]["tags"] == "Svip, PikPak, 有密码"


def test_multiple_urls_create_separate_rows_and_titles() -> None:
    resources = [
        {"url": "https://mypikpak.com/s/a", "password": None},
        {"url": "https://mypikpak.com/s/b", "password": "b2"},
    ]
    rows, _, summary = MODULE.export(
        payload(record(resources=resources, password_status="ambiguous")), {}, MODULE.FOLDER
    )
    assert summary["new"] == 2
    assert [row["title"] for row in rows] == ["资源标题｜1/2", "资源标题｜2/2"]
    assert "密码：待确认" in rows[0]["note"]
    assert "密码待确认" in rows[0]["tags"]
    assert "密码：b2" in rows[1]["note"]


def test_formula_like_title_is_escaped() -> None:
    rows, _, _ = MODULE.export(payload(record(text="=危险标题")), {}, MODULE.FOLDER)
    assert rows[0]["title"].startswith("'=")


def test_existing_raindrop_url_is_not_exported_again() -> None:
    library = {
        MODULE._url_key("https://mypikpak.com/s/a"): {
            "url": "https://mypikpak.com/s/a",
            "note": "密码：abcd",
        }
    }
    rows, review, summary = MODULE.export(payload(record()), library, MODULE.FOLDER)
    assert rows == []
    assert review == []
    assert summary["historical"] == 1


def test_existing_url_with_missing_password_enters_update_review() -> None:
    library = {
        MODULE._url_key("https://mypikpak.com/s/a"): {
            "url": "https://mypikpak.com/s/a",
            "note": "旧记录没有密码",
        }
    }
    rows, review, summary = MODULE.export(payload(record()), library, MODULE.FOLDER)
    assert rows == []
    assert len(review) == 1
    assert review[0]["review_reason"] == "Raindrop 已有 URL，待补充密码"
    assert summary["password_updates"] == 1


def test_same_batch_conflicting_password_is_not_silently_merged() -> None:
    first = record()
    second = record(
        message_id=124,
        resources=[{"url": "https://mypikpak.com/s/a", "password": "efgh"}],
    )
    rows, review, summary = MODULE.export(payload(first, second), {}, MODULE.FOLDER)
    assert len(rows) == 1
    assert len(review) == 1
    assert summary["password_conflicts"] == 1


def test_url_path_case_is_not_collapsed_during_deduplication() -> None:
    first = record(resources=[{"url": "https://mypikpak.com/s/AbC", "password": None}])
    second = record(
        message_id=124,
        resources=[{"url": "https://MYPikPak.com/s/abc", "password": None}],
    )
    rows, review, summary = MODULE.export(payload(first, second), {}, MODULE.FOLDER)
    assert len(rows) == 2
    assert review == []
    assert summary["batch_duplicates"] == 0


def test_written_csv_is_utf8_bom_and_has_only_raindrop_columns() -> None:
    rows, _, _ = MODULE.export(payload(record()), {}, MODULE.FOLDER)
    with tempfile.TemporaryDirectory() as directory:
        target = Path(directory) / "out.csv"
        MODULE._write_csv(target, rows, MODULE.RAINDROP_COLUMNS)
        assert target.read_bytes().startswith(b"\xef\xbb\xbf")
        with target.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            assert reader.fieldnames == MODULE.RAINDROP_COLUMNS
            assert list(reader)[0]["url"] == "https://mypikpak.com/s/a"


class TestSvipRaindropExport(unittest.TestCase):
    def test_all_contract_cases(self) -> None:
        cases = [
            value
            for name, value in globals().items()
            if name.startswith("test_") and callable(value)
        ]
        for case in cases:
            with self.subTest(case=case.__name__):
                case()
