from __future__ import annotations

import sys


def run() -> int:
    if "--smoke-test" in sys.argv:
        import telegram_exporter.daemon_main  # noqa: F401
        import telegram_exporter.ipc_client  # noqa: F401
        import telegram_exporter.reader_search  # noqa: F401
        import telegram_exporter.tgctl  # noqa: F401
        return 0

    if "--smoke-test-url-domain" in sys.argv:
        from telegram_exporter.reader_search import domain_filter_smoke_test

        return 0 if domain_filter_smoke_test() else 1

    if "--smoke-test-search-filters" in sys.argv:
        from telegram_exporter.reader_search import _compile_regex, domain_filter_smoke_test

        pattern = _compile_regex(r"release-\d+", case_sensitive=False)
        regex_ok = pattern is not None and pattern.search("Release-42") is not None
        return 0 if domain_filter_smoke_test() and regex_ok else 1

    from telegram_exporter.tgctl import main

    return main()


if __name__ == "__main__":
    raise SystemExit(run())
