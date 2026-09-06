from __future__ import annotations

from telegram_exporter.session_lock import SessionLease


def test_session_lease_can_release_and_reacquire(tmp_path) -> None:
    session_base = tmp_path / "telegram"
    first = SessionLease(session_base)
    first.acquire()
    first.release()

    second = SessionLease(session_base)
    second.acquire()
    second.release()

    assert session_base.with_suffix(".session.lock").exists()
