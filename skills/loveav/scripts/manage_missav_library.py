#!/usr/bin/env python3
"""预览或确认合并 Raindrop/MissAV CSV 到唯一 missav-library.csv。

默认只在标准输出返回预览，不写任何文件。只有同时使用 ``--commit`` 和
``--confirm WRITE_MISSAV_LIBRARY`` 时，才会备份并原子更新主体库。
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse


OFFICIAL_HEADERS = [
    "id", "title", "note", "excerpt", "url", "folder", "tags", "created",
    "cover", "highlights", "favorite",
]
SCRIPT_HEADERS = [
    "url", "title", "tags", "actress_tags", "type_tags", "status",
    "needs_lookup", "reference_matches", "excluded_from_raindrop",
    "export_blacklist_matches", "target_folder", "actress_raw", "matched_tag", "notes",
]
META_HEADERS = [
    "loveav_canonical_code", "loveav_in_raindrop", "loveav_in_skill_added",
    "loveav_has_missav", "loveav_has_123av",
    "loveav_first_seen_at", "loveav_last_seen_at", "loveav_rule_version",
    "loveav_status", "loveav_variants_json", "loveav_notes",
]
LIBRARY_HEADERS = OFFICIAL_HEADERS + META_HEADERS

NOISE_PREFIXES = {
    "TV", "HTML", "HTTP", "HTTPS", "MESSAGE", "MEDIA", "PHOTO", "VIDEO",
    "DATE", "TITLE", "STATUS", "RESULT", "PAGE", "TELEGRAM", "GITHUB",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = [str(value or "").strip().lower() for value in (reader.fieldnames or [])]
        rows = []
        for raw in reader:
            rows.append({str(key or "").strip().lower(): str(value or "").strip() for key, value in raw.items()})
    return headers, rows


def detect_type(headers: list[str]) -> str:
    values = set(headers)
    if set(LIBRARY_HEADERS).issubset(values):
        return "library"
    if set(OFFICIAL_HEADERS).issubset(values):
        return "raindrop"
    if set(SCRIPT_HEADERS).issubset(values):
        return "skill"
    raise ValueError("无法识别 CSV：既不是 Raindrop 官方 11 列，也不是 MissAV 脚本 14 列。")


def split_folder(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"\s*(?:/|>|\\)\s*", value or "") if part.strip()]


def normalize_folder_part(value: str) -> str:
    return re.sub(r"\s+", "", value or "").casefold()


def site_kind(url: str) -> str:
    try:
        host = (urlparse(url).hostname or "").casefold().removeprefix("www.")
    except ValueError:
        return "other"
    if host == "missav.ai" or host.endswith(".missav.ai"):
        return "missav"
    if host in {"123av.com", "123av.fans"} or host.endswith(".123av.com") or host.endswith(".123av.fans"):
        return "123av"
    return "other"


def is_123av_detail_url(url: str) -> bool:
    if site_kind(url) != "123av":
        return False
    try:
        path = unquote(urlparse(url).path).rstrip("/")
    except ValueError:
        return False
    return re.search(r"/(?:[a-z]{2}/)?v/[^/]+$", path, re.I) is not None


def folder_has_target(part: str) -> bool:
    tokens = [token for token in re.split(r"[^a-z0-9]+", normalize_folder_part(part)) if token]
    return "missav" in tokens or "123av" in tokens


def in_raindrop_scope(folder: str, url: str = "") -> bool:
    parts = split_folder(folder)
    normalized = [normalize_folder_part(part) for part in parts]
    try:
        root_index = normalized.index("日本av")
    except ValueError:
        return False
    if any(folder_has_target(part) for part in parts[root_index + 1 :]):
        return True
    return is_123av_detail_url(url)


def normalize_candidate(value: str) -> str:
    text = unquote(str(value or "")).strip().upper()
    text = text.replace("＿", "_").replace("－", "-")
    text = re.sub(r"\s+", "", text)
    fc2 = re.fullmatch(r"FC2[-_]*(?:PPV[-_]*)?(\d{4,10})", text)
    if fc2:
        return f"FC2-PPV-{fc2.group(1)}"
    pondo = re.fullmatch(r"PONDO[-_](\d{6})[-_](\d{3})", text)
    if pondo:
        return f"PONDO-{pondo.group(1)}_{pondo.group(2)}"
    dated = re.fullmatch(r"(\d{6})[-_](\d{3})", text)
    if dated:
        return f"{dated.group(1)}-{dated.group(2)}"
    ppv = re.fullmatch(r"(\d{4})[-_]?PPV[-_]?(\d{3,6})", text)
    if ppv:
        return f"{ppv.group(1)}-PPV{ppv.group(2)}"
    normal = re.fullmatch(r"([A-Z]{2,12})[-_]?(\d{2,8})(?:[-_]([A-Z0-9]{1,12}))?", text)
    if normal and normal.group(1) not in NOISE_PREFIXES:
        suffix = f"-{normal.group(3)}" if normal.group(3) else ""
        return f"{normal.group(1)}-{normal.group(2)}{suffix}"
    alpha_serial = re.fullmatch(r"([A-Z]{2,12})[-_]([A-Z]{1,4}\d{1,6})", text)
    if alpha_serial and alpha_serial.group(1) not in NOISE_PREFIXES:
        return f"{alpha_serial.group(1)}-{alpha_serial.group(2)}"
    return ""


def comparable_key(code: str) -> str:
    return re.sub(r"[-_\s]+", "", code or "").upper()


def candidate_codes(title: str, url: str) -> list[str]:
    title_values: list[str] = []
    title_text = str(title or "").strip()
    direct = normalize_candidate(title_text)
    if direct:
        title_values.append(direct)
    else:
        patterns = [
            r"FC2[-_\s]*(?:PPV[-_\s]*)?\d{4,10}",
            r"PONDO[-_]\d{6}[-_]\d{3}",
            r"(?<!\d)\d{6}[-_]\d{3}(?!\d)",
            r"(?<!\d)\d{4}[-_]?PPV[-_]?\d{3,6}(?!\d)",
            r"\b[A-Z]{2,12}[-_]?[0-9]{2,8}(?:[-_][A-Z0-9]{1,12})?\b",
            r"\b[A-Z]{2,12}[-_][A-Z]{1,4}[0-9]{1,6}\b",
        ]
        upper = title_text.upper()
        for pattern in patterns:
            for match in re.findall(pattern, upper):
                normalized = normalize_candidate(match)
                if normalized:
                    title_values.append(normalized)

    url_value = ""
    if url:
        try:
            slug = unquote(urlparse(url).path.rstrip("/").split("/")[-1])
        except ValueError:
            slug = ""
        slug = re.sub(r"-(?:chinese-subtitle|uncensored-leak(?:ed)?)$", "", slug, flags=re.I)
        normalized = normalize_candidate(slug)
        if normalized:
            url_value = normalized

    if url_value.startswith("FC2-PPV-") and site_kind(url) == "123av":
        full_number = url_value.removeprefix("FC2-PPV-")
        shortened = [value.removeprefix("PPV-") for value in title_values if value.startswith("PPV-")]
        if shortened and all(full_number.startswith(value) and len(value) < len(full_number) for value in shortened):
            return [url_value]

    output: list[str] = []
    seen: set[str] = set()
    for value in [*title_values, *([url_value] if url_value else [])]:
        key = comparable_key(value)
        if key and key not in seen:
            seen.add(key)
            output.append(value)
    return output


def source_record(row: dict[str, str], source_type: str) -> dict[str, str]:
    if source_type == "raindrop":
        return {field: row.get(field, "") for field in OFFICIAL_HEADERS}
    return {
        "id": "",
        "title": row.get("title", ""),
        "note": row.get("notes", ""),
        "excerpt": "",
        "url": row.get("url", ""),
        "folder": row.get("target_folder", ""),
        "tags": row.get("tags", ""),
        "created": "",
        "cover": "",
        "highlights": "",
        "favorite": "false",
    }


def parse_variants(value: str) -> list[dict[str, object]]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def variant_signature(value: dict[str, object]) -> str:
    stable = {"source_type": value.get("source_type", "")}
    stable.update({field: value.get(field, "") for field in OFFICIAL_HEADERS})
    return json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def variant_time(value: dict[str, object]) -> str:
    return str(value.get("created") or value.get("observed_at") or "")


def variant_rank(value: dict[str, object]) -> tuple[int, int, str]:
    source_priority = 2 if value.get("source_type") == "skill" else 1
    site_priority = {"missav": 2, "123av": 1}.get(site_kind(str(value.get("url") or "")), 0)
    return source_priority, site_priority, variant_time(value)


def canonical_missav_url(code: str) -> str:
    return f"https://missav.ai/cn/{code.casefold()}"


def rebuild_primary(row: dict[str, str], code: str, variants: list[dict[str, object]], rule_version: str, fallback_time: str) -> None:
    ranked = sorted((value for value in variants if isinstance(value, dict)), key=variant_rank, reverse=True)
    if not ranked:
        raise ValueError(f"番号 {code} 没有可用来源变体。")
    preferred = ranked[0]
    for field in OFFICIAL_HEADERS:
        value = str(preferred.get(field) or "")
        if not value:
            value = next((str(item.get(field) or "") for item in ranked if item.get(field)), "")
        row[field] = value

    has_missav = any(site_kind(str(value.get("url") or "")) == "missav" for value in ranked)
    has_123av = any(site_kind(str(value.get("url") or "")) == "123av" for value in ranked)
    if has_missav:
        row["url"] = canonical_missav_url(code)

    times = sorted(value for value in (variant_time(item) for item in ranked) if value)
    row.update({
        "loveav_canonical_code": code,
        "loveav_in_raindrop": "true" if any(item.get("source_type") == "raindrop" for item in ranked) else "false",
        "loveav_in_skill_added": "true" if any(item.get("source_type") == "skill" for item in ranked) else "false",
        "loveav_has_missav": "true" if has_missav else "false",
        "loveav_has_123av": "true" if has_123av else "false",
        "loveav_first_seen_at": times[0] if times else fallback_time,
        "loveav_last_seen_at": times[-1] if times else fallback_time,
        "loveav_rule_version": rule_version,
        "loveav_status": "active",
        "loveav_variants_json": json.dumps(ranked, ensure_ascii=False, separators=(",", ":")),
        "loveav_notes": row.get("loveav_notes", ""),
    })


def load_library(path: Path) -> tuple[list[dict[str, str]], dict[str, dict[str, str]]]:
    if not path.exists():
        return [], {}
    headers, rows = read_rows(path)
    if detect_type(headers) != "library":
        raise ValueError("现有主体库表头不符合 LoveAV 主体库契约。")
    ordered: list[dict[str, str]] = []
    keyed: dict[str, dict[str, str]] = {}
    for row in rows:
        normalized = {field: row.get(field, "") for field in LIBRARY_HEADERS}
        key = comparable_key(normalized["loveav_canonical_code"])
        if not key or key in keyed:
            raise ValueError("现有主体库包含空番号键或重复番号键，必须先人工复核。")
        keyed[key] = normalized
        ordered.append(normalized)
    return ordered, keyed


def prepare_merge(library: Path, inputs: list[Path], forced_type: str, rule_version: str) -> tuple[list[dict[str, str]], dict[str, object]]:
    ordered, keyed = load_library(library)
    timestamp = now_iso()
    counts = {name: 0 for name in ("input", "added", "duplicate", "enriched", "conflict", "invalid", "out_of_scope", "review")}
    examples: dict[str, list[dict[str, object]]] = {name: [] for name in counts if name != "input"}

    for input_path in inputs:
        headers, rows = read_rows(input_path)
        source_type = detect_type(headers) if forced_type == "auto" else forced_type
        if source_type == "library":
            raise ValueError("输入不能是另一份主体库；双库冲突必须先单独复核。")
        for row_number, raw in enumerate(rows, start=2):
            counts["input"] += 1
            if source_type == "raindrop" and not in_raindrop_scope(raw.get("folder", ""), raw.get("url", "")):
                counts["out_of_scope"] += 1
                if len(examples["out_of_scope"]) < 10:
                    examples["out_of_scope"].append({"file": input_path.name, "row": row_number, "folder": raw.get("folder", ""), "title": raw.get("title", "")})
                continue
            record = source_record(raw, source_type)
            candidates = candidate_codes(record.get("title", ""), record.get("url", ""))
            if not candidates:
                counts["invalid"] += 1
                if len(examples["invalid"]) < 10:
                    examples["invalid"].append({"file": input_path.name, "row": row_number, "title": record.get("title", ""), "url": record.get("url", "")})
                continue
            if len(candidates) != 1:
                counts["review"] += 1
                if len(examples["review"]) < 10:
                    examples["review"].append({"file": input_path.name, "row": row_number, "candidates": candidates, "title": record.get("title", ""), "url": record.get("url", "")})
                continue

            code = candidates[0]
            key = comparable_key(code)
            variant = {"source_type": source_type, "source_file": input_path.name, "source_row": row_number, "observed_at": timestamp, **record}
            existing = keyed.get(key)
            if existing is None:
                created = {field: "" for field in LIBRARY_HEADERS}
                rebuild_primary(created, code, [variant], rule_version, timestamp)
                keyed[key] = created
                ordered.append(created)
                counts["added"] += 1
                continue

            conflict_fields: list[str] = []
            for field in OFFICIAL_HEADERS:
                incoming = record.get(field, "")
                current = existing.get(field, "")
                if incoming and current and incoming != current:
                    conflict_fields.append(field)

            variants = parse_variants(existing.get("loveav_variants_json", ""))
            signatures = {variant_signature(item) for item in variants if isinstance(item, dict)}
            signature = variant_signature(variant)
            variant_is_new = signature not in signatures
            if variant_is_new:
                variants.append(variant)
                rebuild_primary(existing, code, variants, rule_version, timestamp)
            if conflict_fields and variant_is_new:
                counts["conflict"] += 1
                if len(examples["conflict"]) < 10:
                    examples["conflict"].append({"file": input_path.name, "row": row_number, "code": code, "fields": conflict_fields})
            elif variant_is_new:
                counts["enriched"] += 1
            else:
                counts["duplicate"] += 1

    report = {
        "library": str(library),
        "inputs": [str(path) for path in inputs],
        "counts": counts,
        "examples": examples,
        "result_total": len(ordered),
        "write_required": counts["added"] + counts["enriched"] + counts["conflict"] > 0,
    }
    return ordered, report


def write_library(path: Path, rows: list[dict[str, str]]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = ""
    if path.exists():
        backup_dir = path.parent.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = backup_dir / f"missav-library-{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        shutil.copy2(path, backup_path)
        backup = str(backup_path)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=LIBRARY_HEADERS, extrasaction="ignore", lineterminator="\r\n")
            writer.writeheader()
            writer.writerows(rows)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return backup


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", required=True, type=Path, help="唯一 missav-library.csv 路径")
    parser.add_argument("--input", required=True, action="append", type=Path, help="可重复：官方 Raindrop CSV 或脚本结果 CSV")
    parser.add_argument("--source-type", choices=("auto", "raindrop", "skill"), default="auto")
    parser.add_argument("--rule-version", default="loveav-v1")
    parser.add_argument("--commit", action="store_true", help="确认后备份并原子写入主体库")
    parser.add_argument("--confirm", default="", help="写入时必须为 WRITE_MISSAV_LIBRARY")
    args = parser.parse_args()

    inputs = [path.resolve() for path in args.input]
    missing = [str(path) for path in inputs if not path.is_file()]
    if missing:
        raise SystemExit(f"找不到输入 CSV：{', '.join(missing)}")
    library = args.library.resolve()
    rows, report = prepare_merge(library, inputs, args.source_type, args.rule_version)
    report["committed"] = False
    report["backup"] = ""
    if args.commit:
        if args.confirm != "WRITE_MISSAV_LIBRARY":
            raise SystemExit("拒绝写入：--commit 必须同时提供 --confirm WRITE_MISSAV_LIBRARY")
        report["backup"] = write_library(library, rows)
        report["committed"] = True
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
