from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from urllib.parse import urlsplit

logger = logging.getLogger("telegram_exporter.proxy")


@dataclass(frozen=True, slots=True)
class ProxyConfig:
    proxy_type: str
    host: str
    port: int

    def as_telethon_dict(self) -> dict[str, object]:
        return {
            "proxy_type": self.proxy_type,
            "addr": self.host,
            "port": self.port,
            "rdns": True,
        }

    @property
    def safe_label(self) -> str:
        return f"{self.proxy_type}://{self.host}:{self.port}"


def _parse_host_port(value: str, default_type: str = "http") -> ProxyConfig | None:
    raw = value.strip()
    if not raw:
        return None

    if "://" not in raw:
        raw = f"{default_type}://{raw}"

    parsed = urlsplit(raw)
    if not parsed.hostname or parsed.port is None:
        return None

    scheme = parsed.scheme.casefold()
    if scheme in {"socks", "socks5", "socks5h"}:
        proxy_type = "socks5"
    elif scheme in {"http", "https"}:
        proxy_type = "http"
    else:
        return None

    return ProxyConfig(proxy_type=proxy_type, host=parsed.hostname, port=int(parsed.port))


def parse_windows_proxy_server(proxy_server: str) -> ProxyConfig | None:
    """Parse Windows Internet Settings ProxyServer into a Telethon-compatible proxy.

    Common values include:
      - 127.0.0.1:7890
      - http://127.0.0.1:7890
      - http=127.0.0.1:7890;https=127.0.0.1:7890
      - socks=127.0.0.1:7891
    """
    raw = proxy_server.strip()
    if not raw:
        return None

    if ";" not in raw and "=" not in raw:
        return _parse_host_port(raw, "http")

    entries: dict[str, str] = {}
    for part in raw.split(";"):
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            key, value = part.split("=", 1)
            entries[key.strip().casefold()] = value.strip()
        else:
            entries.setdefault("http", part)

    # Prefer SOCKS when Windows explicitly exposes one. Otherwise use HTTPS/HTTP.
    for key, proxy_type in (("socks", "socks5"), ("https", "http"), ("http", "http")):
        value = entries.get(key)
        if value:
            return _parse_host_port(value, proxy_type)
    return None


def detect_windows_system_proxy() -> ProxyConfig | None:
    """Return the enabled per-user Windows system proxy, if one is configured.

    This intentionally reads only proxy endpoint metadata. It never reads Telegram
    credentials, proxy authentication secrets, or traffic contents.
    """
    if os.name != "nt":
        return None

    try:
        import winreg

        path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            enabled = int(winreg.QueryValueEx(key, "ProxyEnable")[0] or 0)
            if not enabled:
                return None
            proxy_server = str(winreg.QueryValueEx(key, "ProxyServer")[0] or "")
    except (OSError, ValueError):
        logger.debug("Windows system proxy is unavailable", exc_info=True)
        return None

    config = parse_windows_proxy_server(proxy_server)
    if config:
        logger.info("Detected Windows system proxy: %s", config.safe_label)
    else:
        logger.warning("Windows system proxy is enabled but ProxyServer could not be parsed")
    return config
