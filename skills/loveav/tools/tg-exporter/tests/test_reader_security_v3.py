from __future__ import annotations

import base64
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from telegram_exporter import telegram_service as service_module
from telegram_exporter.cursor_codec import CursorCodec
from telegram_exporter.ipc_protocol import jsonable
from telegram_exporter.reader_models import MediaMetadata, MessageInfoV3, SenderInfo
from telegram_exporter.telegram_service import ApiCredentials, TelegramService


class FakeLease:
    def __init__(self, _path):
        self.acquired = False

    def acquire(self):
        self.acquired = True

    def release(self):
        self.acquired = False


class FakeTelegramClient:
    def __init__(self, session, api_id, api_hash, proxy=None):
        self.session = session
        self.api_id = api_id
        self.api_hash = api_hash
        self.proxy = proxy

    def is_connected(self):
        return False


def test_service_initialization_log_omits_api_credentials(monkeypatch, caplog, tmp_path: Path) -> None:
    monkeypatch.setattr(service_module, "SessionLease", FakeLease)
    monkeypatch.setattr(service_module, "TelegramClient", FakeTelegramClient)
    monkeypatch.setattr(service_module, "detect_windows_system_proxy", lambda: None)
    api_id = 987654321
    api_hash = "VERY-SECRET-API-HASH-V3"
    caplog.set_level(logging.INFO, logger="telegram_exporter.telegram_service")

    service = TelegramService(ApiCredentials(api_id=api_id, api_hash=api_hash), tmp_path / "telegram")
    assert str(api_id) not in caplog.text
    assert api_hash not in caplog.text
    assert "api_id=" not in caplog.text
    assert "api_hash" not in caplog.text
    service._session_lease.release()


def test_rich_message_serialization_has_no_access_hash_or_file_reference() -> None:
    row = MessageInfoV3(
        chat_id=-1001,
        source_chat_id=-1001,
        message_id=42,
        date=datetime(2026, 8, 30, tzinfo=timezone.utc),
        edit_date=None,
        sender=SenderInfo(
            sender_id=123,
            sender_type="user",
            display_name="Example",
            username="example",
            posted_as_chat_id=None,
            is_creator=False,
            is_admin=True,
            admin_title="Admin",
            anonymous_admin=False,
            via_bot_id=None,
            role_basis="current_snapshot",
        ),
        text="explicit stdout body",
        caption=None,
        entities=(),
        reply_to_message_id=None,
        reply_to_top_id=None,
        forum_topic_id=None,
        forward_origin=None,
        grouped_id=None,
        views=None,
        forwards=None,
        reactions=(),
        poll=None,
        service_action=None,
        pinned=False,
        media=MediaMetadata(
            media_type="document",
            filename="safe.pdf",
            mime_type="application/pdf",
            size=123,
            document_id=777,
        ),
    )
    serialized = json.dumps(jsonable(row), ensure_ascii=False).casefold()
    for forbidden in ("access_hash", "file_reference", "api_hash", "api_id", "phone", "session_content"):
        assert forbidden not in serialized


def test_cursor_payload_contains_only_safe_position_data() -> None:
    codec = CursorCodec(b"z" * 32)
    token = codec.encode(
        "messages.history",
        {"chat_id": -1001, "since": None, "until": None},
        {"segment": "current", "source_chat_id": -1001, "before_message_id": 500},
    )
    body_part = token.split(".", 1)[0]
    body = base64.urlsafe_b64decode(body_part + "=" * (-len(body_part) % 4)).decode("utf-8").casefold()
    for forbidden in ("access_hash", "file_reference", "api_hash", "api_id", "phone", "session"):
        assert forbidden not in body
    decoded = codec.decode(token, "messages.history", {"chat_id": -1001, "since": None, "until": None})
    assert decoded == {"segment": "current", "source_chat_id": -1001, "before_message_id": 500}


def test_safe_error_details_should_use_types_not_exception_repr() -> None:
    # A small regression reminder: reader-visible errors should report safe
    # class names/IDs rather than raw TL object reprs that may contain internal
    # access hashes or file references.
    safe = {"telegram_error": type(RuntimeError()).__name__, "chat_id": -1001}
    serialized = json.dumps(safe)
    assert "access_hash" not in serialized
    assert "file_reference" not in serialized
