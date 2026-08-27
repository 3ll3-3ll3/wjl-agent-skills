from datetime import datetime, timezone
from pathlib import Path
import pytest

from scripts.archive_record import archive_folder, choose_record_stem, minute_record_stem, require_real_drive_urls


def test_minute_record_stem_is_precise_to_one_minute():
    dt = datetime(2026, 8, 27, 9, 37, 59, tzinfo=timezone.utc)
    assert minute_record_stem(dt) == "2026-08-27_09-37"


def test_mode_separated_archive_folders(tmp_path: Path):
    assert archive_folder(tmp_path, "student", "四川大学") == tmp_path / "学生认证" / "四川大学"
    assert archive_folder(tmp_path, "faculty", "四川大学") == tmp_path / "教师认证" / "四川大学"


def test_same_minute_collision_appends_student_id(tmp_path: Path):
    dt = datetime(2026, 8, 27, 9, 37, tzinfo=timezone.utc)
    folder = tmp_path / "学生认证" / "四川大学"
    folder.mkdir(parents=True)
    (folder / "2026-08-27_09-37.md").write_text("x", encoding="utf-8")
    assert choose_record_stem(folder, "6483275", dt) == "2026-08-27_09-37_6483275"


def test_final_archive_requires_real_drive_urls():
    with pytest.raises(SystemExit):
        require_real_drive_urls("", "", prepare_only=False)


def test_real_drive_urls_are_accepted():
    require_real_drive_urls(
        "https://docs.google.com/presentation/d/example/edit",
        "https://drive.google.com/file/d/example/view",
        prepare_only=False,
    )
