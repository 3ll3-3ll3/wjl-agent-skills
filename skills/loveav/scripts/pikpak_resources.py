"""LoveAV 共用的 PikPak 链接、密码和标题解析器。"""

from __future__ import annotations

import re
from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit


TARGET_DOMAIN = "mypikpak.com"
URL_RE = re.compile(
    r"(?:https?://|www\.)[^\s<>\"'\u3400-\u9fff，。；：！？【】（）《》「」『』]+",
    re.IGNORECASE,
)
PASSWORD_AFTER_URL_RE = re.compile(
    r"^[\s,，;；|]*(?:密码|提取码|访问码|口令|pwd|password)\s*[:：=]?\s*([A-Za-z0-9_-]{1,64})",
    re.IGNORECASE,
)
PASSWORD_ANYWHERE_RE = re.compile(
    r"(?:密码|提取码|访问码|口令|pwd|password)\s*[:：=]?\s*([A-Za-z0-9_-]{1,64})",
    re.IGNORECASE,
)
PASSWORD_ONLY_RE = re.compile(
    r"^\s*(?:密码|提取码|访问码|口令|pwd|password)\s*[:：=]",
    re.IGNORECASE,
)


def iter_url_candidates(message: dict[str, Any]) -> Iterable[tuple[str, str | None]]:
    for key in ("text", "caption"):
        value = message.get(key)
        if not isinstance(value, str):
            continue
        for match in URL_RE.finditer(value):
            raw = match.group(0).rstrip(".,;:!?)]}，。；：！？】）》」』")
            password_match = PASSWORD_AFTER_URL_RE.match(value[match.end() :])
            yield raw, password_match.group(1) if password_match else None

    entities = message.get("entities")
    if isinstance(entities, (list, tuple)):
        for entity in entities:
            if not isinstance(entity, dict):
                continue
            value = entity.get("url")
            if isinstance(value, str) and value:
                yield value, None


def canonical_url(value: str) -> str:
    candidate = value if "://" in value else f"https://{value}"
    parsed = urlsplit(candidate)
    hostname = (parsed.hostname or "").encode("idna").decode("ascii").lower().rstrip(".")
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("PikPak URL 必须是 http/https。")
    if hostname != TARGET_DOMAIN and not hostname.endswith(f".{TARGET_DOMAIN}"):
        raise ValueError("URL 不是受支持的 PikPak 域名。")
    port = f":{parsed.port}" if parsed.port else ""
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit(("https", f"{hostname}{port}", path, parsed.query, ""))


def canonical_resources(message: dict[str, Any]) -> list[dict[str, str | None]]:
    result: list[dict[str, str | None]] = []
    positions: dict[str, int] = {}
    for raw, password in iter_url_candidates(message):
        try:
            canonical = canonical_url(raw)
        except (UnicodeError, ValueError):
            continue
        display_url = raw.rstrip(".,;:!?)]}")
        key = canonical.casefold()
        resource = {
            "url": display_url,
            "canonical_url": canonical,
            "password": password,
            "copy_text": f"{display_url} 密码: {password}" if password else display_url,
        }
        if key not in positions:
            positions[key] = len(result)
            result.append(resource)
        elif password and not result[positions[key]]["password"]:
            result[positions[key]] = resource

    if len(result) == 1 and not result[0]["password"]:
        candidates: list[str] = []
        for key in ("text", "caption"):
            value = message.get(key)
            if not isinstance(value, str):
                continue
            for match in PASSWORD_ANYWHERE_RE.finditer(value):
                password = match.group(1)
                if password.casefold() not in {item.casefold() for item in candidates}:
                    candidates.append(password)
        if len(candidates) == 1:
            password = candidates[0]
            result[0] = {
                **result[0],
                "password": password,
                "copy_text": f"{result[0]['url']} 密码: {password}",
            }
    return result


def resource_title(message: dict[str, Any], fallback: str) -> str:
    for key in ("text", "caption"):
        value = message.get(key)
        if not isinstance(value, str):
            continue
        for raw_line in value.splitlines():
            line = raw_line.strip()
            if not line or URL_RE.fullmatch(line) or PASSWORD_ONLY_RE.match(line):
                continue
            cleaned = URL_RE.sub("", line).strip(" -|：:，,")
            if cleaned and not PASSWORD_ONLY_RE.match(cleaned):
                return cleaned[:180]
    return fallback[:180]


def resource_identity(resource: dict[str, Any]) -> tuple[str, str]:
    url = str(resource.get("canonical_url") or canonical_url(str(resource.get("url") or ""))).casefold()
    password = str(resource.get("password") or "").strip().casefold()
    return url, password
