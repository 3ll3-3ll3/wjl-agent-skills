from datetime import datetime, timezone
from pathlib import Path

from scripts.archive_record import choose_record_stem, minute_record_stem


def test_minute_record_stem_uses_minute_precision():
    now = datetime(2026, 8, 27, 1, 11, 59, tzinfo=timezone.utc)
    assert minute_record_stem(now) == "2026-08-27_01-11"


def test_student_id_is_only_added_on_same_minute_collision(tmp_path: Path):
    now = datetime(2026, 8, 27, 1, 11, tzinfo=timezone.utc)
    assert choose_record_stem(tmp_path, "7314286", now) == "2026-08-27_01-11"

    (tmp_path / "2026-08-27_01-11.png").write_bytes(b"png")
    assert choose_record_stem(tmp_path, "7314286", now) == "2026-08-27_01-11_7314286"
