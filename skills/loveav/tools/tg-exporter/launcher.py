from __future__ import annotations

import sys


def _smoke_test() -> int:
    # Import the packaged production GUI + daemon stack without opening windows
    # or touching a real Telegram Session. GitHub Actions uses this to catch
    # hidden-import / PyInstaller regressions.
    import telegram_exporter.daemon_gui  # noqa: F401
    import telegram_exporter.daemon_main  # noqa: F401
    import telegram_exporter.ipc_client  # noqa: F401
    import telegram_exporter.ipc_transport  # noqa: F401

    return 0


def run() -> int:
    if "--smoke-test" in sys.argv:
        return _smoke_test()

    from telegram_exporter.main import main

    return main()


if __name__ == "__main__":
    raise SystemExit(run())
