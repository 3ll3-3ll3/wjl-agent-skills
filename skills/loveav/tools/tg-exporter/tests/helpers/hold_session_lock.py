from __future__ import annotations

import sys
import time
from pathlib import Path

from telegram_exporter.paths import session_path
from telegram_exporter.session_lock import SessionLease


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: hold_session_lock.py READY_FILE")
    ready_file = Path(sys.argv[1])
    lease = SessionLease(session_path())
    lease.acquire()
    ready_file.parent.mkdir(parents=True, exist_ok=True)
    ready_file.write_text("ready", encoding="utf-8")
    try:
        time.sleep(60)
    finally:
        lease.release()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
