from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from telegram_exporter import tgctl
from telegram_exporter.bridge_errors import (
    DOWNLOAD_CONFIRMATION_REQUIRED,
    DOWNLOAD_LIMIT_EXCEEDED,
    INVALID_CURSOR,
    TelegramBridgeError,
)
from telegram_exporter.cursor_codec import CursorCodec
from telegram_exporter.reader_media import LARGE_FILE_LIMIT, media_download
from telegram_exporter.reader_models import DialogInfo

CHAT_ID = -(10**12 + 77)


class MessageMediaDocument:
    def __init__(self, size: int = 12):
        self.document = SimpleNamespace(id=77, mime_type="application/pdf", size=size)
        self.spoiler = False


class MediaMessage:
    def __init__(self, message_id: int, *, filename: str = "report.pdf", size: int = 12):
        self.id = message_id
        self.media = MessageMediaDocument(size=size)
        self.file = SimpleNamespace(
            name=filename,
            mime_type="application/pdf",
            size=size,
            width=None,
            height=None,
            duration=None,
        )
        self.photo = None
        self.voice = None
        self.video = None
        self.audio = None
        self.sticker = None
        self.gif = None


class MediaClient:
    def __init__(self, messages):
        self.messages = {message.id: message for message in messages}
        self.download_calls: list[tuple[int, str]] = []

    async def get_messages(self, _entity, ids):
        return [self.messages.get(int(value)) for value in ids]

    async def download_media(self, message, file):
        path = Path(file)
        self.download_calls.append((message.id, str(path)))
        path.write_bytes(b"hello-media")
        return str(path)


class MediaReader:
    def __init__(self, messages):
        self.cursor = CursorCodec(b"m" * 32)
        self.client = MediaClient(messages)
        self.row = DialogInfo(chat_id=CHAT_ID, title="Files", username=None, dialog_type="supergroup")

    async def resolve_dialog(self, _reference):
        return self.row, CHAT_ID


def _plan(reader: MediaReader, tmp_path: Path, *, ids: list[int] | None = None, allow_large: bool = False) -> str:
    with pytest.raises(TelegramBridgeError) as exc_info:
        asyncio.run(
            media_download(
                reader,
                CHAT_ID,
                ids or [1],
                str(tmp_path / "downloads"),
                allow_large_download=allow_large,
            )
        )
    assert exc_info.value.code == DOWNLOAD_CONFIRMATION_REQUIRED
    details = exc_info.value.details
    assert details["file_count"] == len(ids or [1])
    assert details["confirmation_token"]
    return details["confirmation_token"]


def test_media_plan_does_not_write_and_confirm_downloads_atomically(tmp_path: Path) -> None:
    reader = MediaReader([MediaMessage(1, filename="paper.pdf")])
    output = tmp_path / "downloads"
    token = _plan(reader, tmp_path)
    assert not output.exists()
    assert reader.client.download_calls == []

    result = asyncio.run(media_download(reader, CHAT_ID, [1], str(output), confirm=token))
    assert result["downloaded_count"] == 1
    assert len(reader.client.download_calls) == 1
    final = Path(result["files"][0]["path"])
    assert final.exists()
    assert final.read_bytes() == b"hello-media"
    assert not list(output.glob("*.part"))


def test_media_confirmation_is_bound_to_output_and_plan(tmp_path: Path) -> None:
    reader = MediaReader([MediaMessage(1)])
    token = _plan(reader, tmp_path)
    with pytest.raises(TelegramBridgeError) as exc_info:
        asyncio.run(media_download(reader, CHAT_ID, [1], str(tmp_path / "other"), confirm=token))
    assert exc_info.value.code == INVALID_CURSOR


def test_media_normal_limit_requires_large_override(tmp_path: Path) -> None:
    messages = [MediaMessage(i) for i in range(1, 22)]
    reader = MediaReader(messages)
    with pytest.raises(TelegramBridgeError) as exc_info:
        asyncio.run(media_download(reader, CHAT_ID, list(range(1, 22)), str(tmp_path / "downloads")))
    assert exc_info.value.code == DOWNLOAD_LIMIT_EXCEEDED
    token = _plan(reader, tmp_path, ids=list(range(1, 22)), allow_large=True)
    assert token


def test_media_hard_file_cap_rejects_before_download(tmp_path: Path) -> None:
    reader = MediaReader([])
    ids = list(range(1, LARGE_FILE_LIMIT + 2))
    with pytest.raises(TelegramBridgeError) as exc_info:
        asyncio.run(
            media_download(
                reader,
                CHAT_ID,
                ids,
                str(tmp_path / "downloads"),
                allow_large_download=True,
            )
        )
    assert exc_info.value.code == DOWNLOAD_LIMIT_EXCEEDED
    assert reader.client.download_calls == []


def test_media_cli_parser_requires_explicit_output_and_supports_confirmation() -> None:
    parser = tgctl.build_parser()
    args = parser.parse_args(
        [
            "media",
            "download",
            "--chat",
            "me",
            "--ids",
            "1",
            "2",
            "--output",
            r"D:\\Downloads\\tg",
            "--confirm",
            "token",
            "--allow-large-download",
            "--json",
        ]
    )
    assert args.command == "media"
    assert args.media_command == "download"
    assert args.ids == [1, 2]
    assert args.confirm == "token"
    assert args.allow_large_download is True
