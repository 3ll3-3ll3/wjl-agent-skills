from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from .models import DEFAULT_EXPORT_CATEGORY

_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def validate_category_name(value: str) -> str:
    """Return a Windows-safe category name or raise ValueError.

    Category display names map 1:1 to folders under the selected output root,
    so silently rewriting invalid characters would create confusing collisions.
    """

    name = str(value).strip()
    if not name:
        raise ValueError("分类名称不能为空。")
    if name in {".", ".."}:
        raise ValueError("分类名称不能是 . 或 ..。")
    if name.endswith((".", " ")):
        raise ValueError("分类名称不能以句点或空格结尾。")
    if _INVALID_CHARS.search(name):
        raise ValueError('分类名称不能包含 < > : " / \\ | ? * 或控制字符。')
    stem = name.split(".", 1)[0].upper()
    if stem in _RESERVED:
        raise ValueError(f"分类名称不能使用 Windows 保留名称 {stem}。")
    return name


def normalize_categories(raw) -> list[str]:
    """Normalize persisted custom categories while preserving user order."""

    if not isinstance(raw, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for value in raw:
        try:
            name = validate_category_name(str(value))
        except ValueError:
            continue
        if name == DEFAULT_EXPORT_CATEGORY:
            continue
        folded = name.casefold()
        if folded in seen:
            continue
        seen.add(folded)
        result.append(name)
    return result


def all_categories(custom_categories: list[str]) -> list[str]:
    return [DEFAULT_EXPORT_CATEGORY, *normalize_categories(custom_categories)]


def ensure_category_dirs(output_root: Path, custom_categories: list[str]) -> None:
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    for category in all_categories(custom_categories):
        (root / category).mkdir(parents=True, exist_ok=True)


def export_timestamp_name(moment: datetime) -> str:
    return moment.astimezone().strftime("%Y-%m-%d_%H-%M-%S")


def next_available_json_path(folder: Path, stem: str) -> Path:
    """Never overwrite a previous independent export, even in the same second."""

    folder.mkdir(parents=True, exist_ok=True)
    candidate = folder / f"{stem}.json"
    if not candidate.exists():
        return candidate
    suffix = 2
    while True:
        candidate = folder / f"{stem}_{suffix}.json"
        if not candidate.exists():
            return candidate
        suffix += 1
