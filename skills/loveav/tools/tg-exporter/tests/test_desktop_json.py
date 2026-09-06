from datetime import datetime, timezone

from telegram_exporter.desktop_json import ExportMessage, build_chat_export, serialize_message


def test_plain_text_message_shape():
    msg = ExportMessage(
        id=42,
        date=datetime(2026, 8, 28, 3, 0, tzinfo=timezone.utc),
        from_name="Alice",
        from_id="user123",
        text='中文 emoji 😂 quote " newline\nsecond',
        reply_to_message_id=41,
    )
    data = serialize_message(msg)
    assert data["id"] == 42
    assert data["type"] == "message"
    assert data["date_unixtime"] == str(int(msg.date.timestamp()))
    assert data["from"] == "Alice"
    assert data["from_id"] == "user123"
    assert data["reply_to_message_id"] == 41
    assert data["text"] == msg.text
    assert data["text_entities"] == [{"type": "plain", "text": msg.text}]


def test_chat_export_is_independent_container():
    payload = build_chat_export(name="Math", chat_id=-100123, chat_type="private_supergroup", messages=[])
    assert payload == {"name": "Math", "type": "private_supergroup", "id": 100123, "messages": []}
