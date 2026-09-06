from telegram_exporter.proxy import parse_windows_proxy_server


def test_parse_plain_windows_proxy():
    proxy = parse_windows_proxy_server("127.0.0.1:7890")
    assert proxy is not None
    assert proxy.proxy_type == "http"
    assert proxy.host == "127.0.0.1"
    assert proxy.port == 7890


def test_parse_protocol_map_prefers_socks():
    proxy = parse_windows_proxy_server("http=127.0.0.1:7890;socks=127.0.0.1:7891")
    assert proxy is not None
    assert proxy.proxy_type == "socks5"
    assert proxy.port == 7891


def test_parse_protocol_map_https_fallback():
    proxy = parse_windows_proxy_server("http=127.0.0.1:7890;https=127.0.0.1:7890")
    assert proxy is not None
    assert proxy.proxy_type == "http"
    assert proxy.port == 7890


def test_invalid_proxy_returns_none():
    assert parse_windows_proxy_server("") is None
    assert parse_windows_proxy_server("not-a-proxy") is None
