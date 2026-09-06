from telegram_exporter.storage import LocalState


def test_state_stores_only_checkpoint(tmp_path):
    state = LocalState(tmp_path / "state.json")
    state.mark_success(123, 999, "2026-08-28T12:00:00+08:00")
    assert state.last_message_id(123) == 999
    text = (tmp_path / "state.json").read_text(encoding="utf-8")
    assert "\"text\"" not in text.lower()
    assert "正文" not in text
    assert "999" in text


def test_checkpoint_never_moves_backward(tmp_path):
    state = LocalState(tmp_path / "state.json")
    state.mark_success(123, 1000, "2026-08-28T12:00:00+08:00")
    state.mark_success(123, 500, "2026-08-28T13:00:00+08:00")
    assert state.last_message_id(123) == 1000
