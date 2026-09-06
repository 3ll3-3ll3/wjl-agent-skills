from __future__ import annotations

import os
import time

from telegram_exporter import avatar_cache


def test_avatar_cache_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr(avatar_cache, "avatar_cache_dir", lambda: tmp_path)

    path = avatar_cache.write_cached_avatar(-100123, b"avatar-bytes")

    assert path.name == "m100123.img"
    assert avatar_cache.read_cached_avatar(-100123) == b"avatar-bytes"


def test_stale_avatar_cache_is_ignored(monkeypatch, tmp_path):
    monkeypatch.setattr(avatar_cache, "avatar_cache_dir", lambda: tmp_path)
    path = avatar_cache.write_cached_avatar(456, b"old-avatar")
    old = time.time() - (8 * 24 * 60 * 60)
    os.utime(path, (old, old))

    assert avatar_cache.read_cached_avatar(456) is None
