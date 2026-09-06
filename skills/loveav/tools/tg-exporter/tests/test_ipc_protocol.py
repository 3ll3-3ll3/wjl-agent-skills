from __future__ import annotations

import json

import pytest

from telegram_exporter.bridge_errors import IPC_PROTOCOL_ERROR, IPC_RESPONSE_TOO_LARGE, TelegramBridgeError
from telegram_exporter import ipc_identity as identity_module
from telegram_exporter.ipc_protocol import (
    MAX_FRAME_BYTES,
    PROTOCOL,
    decode_frame,
    encode_frame,
    make_request,
    validate_request,
)


def test_protocol_round_trip_is_utf8_json_bytes() -> None:
    request = make_request(client_kind="tgctl", app_version="0.2.0", method="system.hello")
    encoded = encode_frame(request)
    assert isinstance(encoded, bytes)
    assert b"pickle" not in encoded.lower()
    decoded = validate_request(decode_frame(encoded))
    assert decoded["protocol"] == PROTOCOL
    assert decoded["method"] == "system.hello"


def test_protocol_rejects_non_json() -> None:
    with pytest.raises(TelegramBridgeError) as exc_info:
        decode_frame(b"not-json")
    assert exc_info.value.code == IPC_PROTOCOL_ERROR


def test_protocol_rejects_wrong_major() -> None:
    request = make_request(client_kind="tgctl", app_version="0.2.0", method="system.hello")
    request["protocol"] = "tgipc/999"
    with pytest.raises(TelegramBridgeError) as exc_info:
        validate_request(request)
    assert exc_info.value.code == IPC_PROTOCOL_ERROR


def test_frame_hard_cap() -> None:
    with pytest.raises(TelegramBridgeError) as exc_info:
        encode_frame({"blob": "x" * (MAX_FRAME_BYTES + 1)})
    assert exc_info.value.code == IPC_RESPONSE_TOO_LARGE


def test_identity_is_stable_and_secret_not_plaintext_json(tmp_path, monkeypatch) -> None:
    identity_path = tmp_path / "ipc_identity.json"
    monkeypatch.setattr(identity_module, "ipc_identity_lock_path", lambda: tmp_path / "identity.lock")
    first = identity_module.load_or_create_identity(identity_path)
    second = identity_module.load_or_create_identity(identity_path)
    assert first == second
    assert len(first.auth_secret) == 32
    payload = json.loads(identity_path.read_text(encoding="utf-8"))
    assert payload["instance_id"] == first.instance_id
    assert first.auth_secret.hex() not in identity_path.read_text(encoding="utf-8")
