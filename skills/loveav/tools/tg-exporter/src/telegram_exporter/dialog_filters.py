from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from telethon.utils import get_peer_id

from .models import FolderRef, GroupInfo


def filter_title(dialog_filter: Any) -> str:
    """Return a displayable Telegram folder title across TL schema versions."""

    value = getattr(dialog_filter, "title", "")
    if isinstance(value, str):
        return value
    text = getattr(value, "text", None)
    if isinstance(text, str):
        return text
    return str(value or "").strip()


def peer_ids(peers: Iterable[Any] | None) -> set[int]:
    result: set[int] = set()
    for peer in peers or ():
        try:
            result.add(int(get_peer_id(peer)))
        except (TypeError, ValueError, AttributeError):
            continue
    return result


def folder_matches_group(dialog_filter: Any, group: GroupInfo) -> bool:
    """Evaluate Telegram's dialog-filter rules for a group/channel catalogue item.

    Explicit exclusions win. Explicit/pinned inclusions are treated as "always
    include". Otherwise the folder's dynamic group/broadcast flags and
    muted/read/archived exclusions are evaluated against the catalogue snapshot.
    """

    excluded = peer_ids(getattr(dialog_filter, "exclude_peers", None))
    if group.chat_id in excluded:
        return False

    explicitly_included = peer_ids(getattr(dialog_filter, "include_peers", None))
    explicitly_included.update(peer_ids(getattr(dialog_filter, "pinned_peers", None)))
    if group.chat_id in explicitly_included:
        return True

    include_by_type = bool(
        (getattr(dialog_filter, "groups", False) and group.is_group)
        or (getattr(dialog_filter, "broadcasts", False) and group.is_broadcast)
    )
    if not include_by_type:
        return False

    if getattr(dialog_filter, "exclude_muted", False) and group.is_muted:
        return False
    if getattr(dialog_filter, "exclude_read", False) and not group.is_unread:
        return False
    if getattr(dialog_filter, "exclude_archived", False) and group.is_archived:
        return False
    return True


def apply_folder_memberships(groups: list[GroupInfo], filters: Iterable[Any]) -> int:
    """Attach account chat-folder memberships to groups; return useful folder count."""

    folder_count = 0
    for order, dialog_filter in enumerate(filters):
        # DialogFilterDefault represents Telegram's all-chats view rather than a
        # custom account folder. The selector already has its own "all" option.
        if type(dialog_filter).__name__ == "DialogFilterDefault":
            continue

        title = filter_title(dialog_filter)
        folder_id = getattr(dialog_filter, "id", None)
        if not title or folder_id is None:
            continue

        matched = [group for group in groups if folder_matches_group(dialog_filter, group)]
        if not matched:
            # The exporter only lists groups/channels. A Telegram folder containing
            # only private users/bots is intentionally omitted from this selector.
            continue

        ref = FolderRef(folder_id=int(folder_id), title=title, order=order)
        for group in matched:
            group.folders = (*group.folders, ref)
        folder_count += 1

    return folder_count
