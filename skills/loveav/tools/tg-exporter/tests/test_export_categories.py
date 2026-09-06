from datetime import datetime, timezone

import pytest

from telegram_exporter.export_categories import (
    all_categories,
    ensure_category_dirs,
    export_timestamp_name,
    next_available_json_path,
    normalize_categories,
    validate_category_name,
)
from telegram_exporter.models import DEFAULT_EXPORT_CATEGORY


def test_category_validation_and_normalization():
    assert validate_category_name("保研") == "保研"
    with pytest.raises(ValueError):
        validate_category_name("A/B")
    with pytest.raises(ValueError):
        validate_category_name("CON")

    assert normalize_categories(["AI", "ai", "资料", "A/B", DEFAULT_EXPORT_CATEGORY]) == ["AI", "资料"]
    assert all_categories(["AI"]) == [DEFAULT_EXPORT_CATEGORY, "AI"]


def test_category_directories_are_created_under_output_root(tmp_path):
    ensure_category_dirs(tmp_path, ["第一类", "第二类"])

    assert (tmp_path / DEFAULT_EXPORT_CATEGORY).is_dir()
    assert (tmp_path / "第一类").is_dir()
    assert (tmp_path / "第二类").is_dir()


def test_timestamp_path_never_overwrites_same_second(tmp_path):
    stem = export_timestamp_name(datetime(2026, 8, 29, 11, 1, 18, tzinfo=timezone.utc))
    folder = tmp_path / "第一类" / "群组1"
    first = next_available_json_path(folder, stem)
    first.write_text("{}", encoding="utf-8")
    second = next_available_json_path(folder, stem)

    assert first.name.endswith(".json")
    assert second.stem == first.stem + "_2"
