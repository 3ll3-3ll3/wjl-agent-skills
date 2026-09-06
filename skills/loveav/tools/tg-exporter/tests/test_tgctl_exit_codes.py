from __future__ import annotations

import io
import json
import sys

from telegram_exporter import tgctl
from telegram_exporter.session_lock import SessionBusyError


def test_session_busy_returns_exit_code_8(monkeypatch, capsys) -> None:
    async def fake_run(_args):
        raise SessionBusyError("session busy for test")

    monkeypatch.setattr(tgctl, "setup_logging", lambda: None)
    monkeypatch.setattr(tgctl, "run_command", fake_run)

    code = tgctl.main(["status", "--json"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert captured.err == ""
    assert code == 8
    assert payload["ok"] is False
    assert payload["error"]["code"] == "SESSION_BUSY"


def test_console_streams_are_reconfigured_to_utf8(monkeypatch) -> None:
    stdout_bytes = io.BytesIO()
    stderr_bytes = io.BytesIO()
    stdout = io.TextIOWrapper(stdout_bytes, encoding="cp1252", newline="\n")
    stderr = io.TextIOWrapper(stderr_bytes, encoding="cp1252", newline="\n")
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)

    tgctl._configure_console_streams()

    assert stdout.encoding.casefold() == "utf-8"
    assert stderr.encoding.casefold() == "utf-8"
    tgctl.emit(tgctl.failure("SESSION_BUSY", "Telegram Session 正在被另一个进程使用。"), True)
    stdout.flush()

    payload = json.loads(stdout_bytes.getvalue().decode("utf-8"))
    assert payload["error"]["code"] == "SESSION_BUSY"
    assert "正在被另一个进程使用" in payload["error"]["message"]
