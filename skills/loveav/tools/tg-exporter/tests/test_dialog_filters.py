from types import SimpleNamespace

from telethon import types
from telethon.utils import get_peer_id

from telegram_exporter.dialog_filters import apply_folder_memberships, filter_title, folder_matches_group
from telegram_exporter.models import GroupInfo


def _filter(**kwargs):
    defaults = dict(
        id=2,
        title="学习",
        pinned_peers=[],
        include_peers=[],
        exclude_peers=[],
        groups=False,
        broadcasts=False,
        exclude_muted=False,
        exclude_read=False,
        exclude_archived=False,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_explicit_include_and_exclude_precedence():
    peer = types.InputPeerChannel(channel_id=123, access_hash=1)
    chat_id = int(get_peer_id(peer))
    group = GroupInfo(chat_id=chat_id, title="A", is_broadcast=True)

    assert folder_matches_group(_filter(include_peers=[peer]), group)
    assert not folder_matches_group(_filter(include_peers=[peer], exclude_peers=[peer]), group)


def test_dynamic_group_folder_honors_read_muted_archived_exclusions():
    base = _filter(groups=True, exclude_read=True, exclude_muted=True, exclude_archived=True)

    assert folder_matches_group(
        base,
        GroupInfo(chat_id=-1, title="Unread", is_group=True, is_unread=True),
    )
    assert not folder_matches_group(
        base,
        GroupInfo(chat_id=-2, title="Read", is_group=True, is_unread=False),
    )
    assert not folder_matches_group(
        base,
        GroupInfo(chat_id=-3, title="Muted", is_group=True, is_unread=True, is_muted=True),
    )
    assert not folder_matches_group(
        base,
        GroupInfo(chat_id=-4, title="Archived", is_group=True, is_unread=True, is_archived=True),
    )


def test_group_and_broadcast_flags_are_distinct():
    group = GroupInfo(chat_id=-1, title="Group", is_group=True)
    broadcast = GroupInfo(chat_id=-2, title="Channel", is_broadcast=True)

    assert folder_matches_group(_filter(groups=True), group)
    assert not folder_matches_group(_filter(groups=True), broadcast)
    assert folder_matches_group(_filter(broadcasts=True), broadcast)


def test_apply_memberships_preserves_account_filter_order_and_omits_empty_folder():
    groups = [
        GroupInfo(chat_id=-1, title="Math", is_group=True),
        GroupInfo(chat_id=-2, title="News", is_broadcast=True),
    ]
    filters = [
        _filter(id=10, title="学习", groups=True),
        _filter(id=20, title="资讯", broadcasts=True),
        _filter(id=30, title="联系人专用"),
    ]

    assert apply_folder_memberships(groups, filters) == 2
    assert [(ref.folder_id, ref.title, ref.order) for ref in groups[0].folders] == [(10, "学习", 0)]
    assert [(ref.folder_id, ref.title, ref.order) for ref in groups[1].folders] == [(20, "资讯", 1)]


def test_filter_title_supports_text_with_entities_shape():
    assert filter_title(SimpleNamespace(title=SimpleNamespace(text="保研"))) == "保研"
