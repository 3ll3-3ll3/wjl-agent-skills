import asyncio
from types import SimpleNamespace

from telegram_exporter.telegram_service import TelegramService


class FakeClient:
    def __init__(self, dialogs):
        self._dialogs = dialogs

    async def iter_dialogs(self):
        for dialog in self._dialogs:
            yield dialog

    async def __call__(self, _request):
        return SimpleNamespace(filters=[])


def _dialog(peer_id: int, title: str, *, migrated_to=None, is_group=True, is_channel=False):
    entity = SimpleNamespace(
        peer_id=peer_id,
        username=None,
        photo=None,
        migrated_to=migrated_to,
    )
    dialog_state = SimpleNamespace(
        unread_mark=False,
        read_inbox_max_id=0,
        notify_settings=None,
    )
    return SimpleNamespace(
        is_group=is_group,
        is_channel=is_channel,
        entity=entity,
        unread_count=0,
        dialog=dialog_state,
        message=None,
        name=title,
        archived=False,
    )


def test_list_groups_hides_legacy_basic_group_and_attaches_migration(monkeypatch):
    old_id = -123
    current_id = -100999
    target = SimpleNamespace(peer_id=current_id)
    dialogs = [
        _dialog(old_id, "数学群", migrated_to=target),
        _dialog(current_id, "数学群", is_group=True, is_channel=True),
    ]

    monkeypatch.setattr(
        "telegram_exporter.telegram_service.get_peer_id",
        lambda entity: entity.peer_id,
    )
    service = object.__new__(TelegramService)
    service.client = FakeClient(dialogs)

    groups = asyncio.run(service.list_groups())

    assert len(groups) == 1
    assert groups[0].chat_id == current_id
    assert groups[0].migrated_from_chat_id == old_id
