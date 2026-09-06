from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_json(path: Path, default: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except json.JSONDecodeError:
        return default


def write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp.replace(path)


class LocalState:
    """只记录每个群上次成功导出的 message_id，不保存任何消息正文。"""

    def __init__(self, path: Path):
        self.path = path
        self.data: dict[str, Any] = read_json(path, {})

    def last_message_id(self, chat_id: int) -> int:
        return int(self.data.get(str(chat_id), {}).get("last_export_message_id", 0))

    def mark_success(self, chat_id: int, message_id: int, exported_at: str) -> None:
        # Checkpoints are monotonic. Exporting an older historical date window later
        # must never make a future “since last export” run go backwards.
        previous = self.last_message_id(chat_id)
        next_id = max(previous, int(message_id))
        self.data[str(chat_id)] = {
            "last_export_message_id": next_id,
            "exported_at": exported_at,
        }
        write_json_atomic(self.path, self.data)
