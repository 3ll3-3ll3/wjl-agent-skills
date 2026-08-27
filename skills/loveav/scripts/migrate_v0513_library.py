#!/usr/bin/env python3
"""只读提取 v0.5.13 SQLite 中可用于 LoveAV 主体库复核的候选数据。

本脚本永远不直接创建或覆盖正式 ``missav-library.csv``，也不读取、复制或修改
规则与黑名单。输出仅用于后续按 ``references/curated-library.md`` 预览和确认合并。
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable


CODE_RE = re.compile(r"^(?:FC2-PPV-\d{5,9}|[A-Z]{2,12}-\d{2,7}(?:-[A-Z0-9]{1,12})?)$")
SECRET_WORDS = ("token", "secret", "password", "passwd", "otp", "session", "cookie", "api_hash", "credential")


def normalize_code(value: object) -> str:
    text = str(value or "").strip().upper()
    text = re.sub(r"[＿_\s]+", "-", text)
    text = re.sub(r"-{2,}", "-", text)
    fc2 = re.fullmatch(r"FC2-?(?:PPV-?)?(\d{5,9})", text, re.IGNORECASE)
    if fc2:
        text = f"FC2-PPV-{fc2.group(1)}"
    return text if CODE_RE.fullmatch(text) else ""


def safe_text(value: object) -> str:
    return str(value or "").replace("\x00", "").strip()


def csv_value(value: object) -> str:
    """Prevent formula interpretation when a CSV is opened in a spreadsheet."""
    text = safe_text(value)
    return f"'{text}" if text.startswith(("=", "+", "-", "@")) else text


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    rows = connection.execute(f"pragma table_info({quote_identifier(table)})").fetchall()
    return {str(row[1]) for row in rows}


def query_rows(connection: sqlite3.Connection, table: str, wanted: Iterable[str]) -> list[dict[str, object]]:
    columns = table_columns(connection, table)
    selected = [name for name in wanted if name in columns and not any(word in name.lower() for word in SECRET_WORDS)]
    if not selected:
        return []
    sql = "select " + ", ".join(quote_identifier(name) for name in selected) + f" from {quote_identifier(table)}"
    return [dict(zip(selected, row)) for row in connection.execute(sql).fetchall()]


def write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, object]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({field: csv_value(row.get(field, "")) for field in fieldnames})
                count += 1
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return count


def build_rows(connection: sqlite3.Connection) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    code_rows = query_rows(
        connection,
        "codes",
        [
            "id", "code", "best_url", "status", "source_url", "missav_error",
            "raindrop_folder", "raindrop_title", "raindrop_excerpt", "raindrop_note",
            "raindrop_cover", "raindrop_created", "raindrop_collection_id", "raindrop_remote_id",
            "created_at", "updated_at",
        ],
    )
    if not code_rows:
        raise RuntimeError("旧数据库没有可读取的 codes 表或该表为空。")

    tag_rows = query_rows(connection, "actress_tags", ["id", "tag_name", "created_at", "updated_at"])
    tag_by_id = {int(row["id"]): safe_text(row.get("tag_name")) for row in tag_rows if row.get("id") is not None}
    links = query_rows(connection, "actress_code_map", ["actress_id", "code_id"])
    tags_by_code: defaultdict[int, list[str]] = defaultdict(list)
    for link in links:
        code_id, actress_id = link.get("code_id"), link.get("actress_id")
        if code_id is None or actress_id is None:
            continue
        tag = tag_by_id.get(int(actress_id), "")
        if tag and tag not in tags_by_code[int(code_id)]:
            tags_by_code[int(code_id)].append(tag)

    genre_rows = query_rows(connection, "genre_tags", ["id", "name"])
    genre_by_id = {int(row["id"]): safe_text(row.get("name")) for row in genre_rows if row.get("id") is not None}
    genre_links = query_rows(connection, "code_genres", ["code_id", "genre_id"])
    genres_by_code: defaultdict[int, list[str]] = defaultdict(list)
    for link in genre_links:
        code_id, genre_id = link.get("code_id"), link.get("genre_id")
        if code_id is None or genre_id is None:
            continue
        genre = genre_by_id.get(int(genre_id), "")
        if genre and genre not in genres_by_code[int(code_id)]:
            genres_by_code[int(code_id)].append(genre)

    seen_rows: list[dict[str, object]] = []
    candidate_rows: list[dict[str, object]] = []
    review_rows: list[dict[str, object]] = []
    for row in sorted(code_rows, key=lambda item: int(item.get("id") or 0)):
        code = normalize_code(row.get("code"))
        status = safe_text(row.get("status")) or "unknown"
        code_id = int(row.get("id") or 0)
        tags = tags_by_code[code_id]
        genres = genres_by_code[code_id]
        base = {
            "tool": "missav",
            "canonical_key": code.replace("-", "") if code else f"legacy-id-{code_id}",
            "primary_value": code or safe_text(row.get("code")),
            "secondary_value": safe_text(row.get("best_url")),
            "status": status,
            "tags": "|".join(tags),
            "genres": "|".join(genres),
            "folder": safe_text(row.get("raindrop_folder")),
            "first_seen_at": safe_text(row.get("created_at")),
            "last_seen_at": safe_text(row.get("updated_at")) or safe_text(row.get("created_at")),
            "seen_count": 1,
            "rule_version": "v0.5.13-legacy",
            "legacy_id": code_id,
            "selection_state": "pending" if status == "ok" and code else "review",
            "notes": safe_text(row.get("missav_error")),
        }
        seen_rows.append({
            "tool": "missav",
            "canonical_key": base["canonical_key"],
            "primary_value": base["primary_value"],
            "status": status,
            "legacy_id": code_id,
            "source": "v0.5.13 codes",
        })
        if status == "ok" and code:
            candidate_rows.append(base)
        else:
            review_rows.append(base)

    observed = Counter(tag for tags in tags_by_code.values() for tag in tags)
    observed_rows = [
        {"tag": tag, "code_count": count, "candidate_reference": "review"}
        for tag, count in sorted(observed.items(), key=lambda item: (-item[1], item[0]))
    ]
    return seen_rows, candidate_rows, review_rows + observed_rows


def write_legacy_metadata(connection: sqlite3.Connection, output: Path) -> int:
    rows = query_rows(
        connection,
        "codes",
        ["id", "code", "best_url", "raindrop_folder", "raindrop_title", "raindrop_excerpt", "raindrop_note", "raindrop_cover", "raindrop_created", "raindrop_collection_id", "raindrop_remote_id"],
    )
    fields = ["legacy_id", "code", "best_url", "folder", "title", "excerpt", "note", "cover", "created", "collection_id", "remote_id"]
    normalized = []
    for row in rows:
        normalized.append({
            "legacy_id": row.get("id"), "code": normalize_code(row.get("code")) or row.get("code"),
            "best_url": row.get("best_url"), "folder": row.get("raindrop_folder"),
            "title": row.get("raindrop_title"), "excerpt": row.get("raindrop_excerpt"),
            "note": row.get("raindrop_note"), "cover": row.get("raindrop_cover"),
            "created": row.get("raindrop_created"), "collection_id": row.get("raindrop_collection_id"),
            "remote_id": row.get("raindrop_remote_id"),
        })
    return write_csv(output, fields, normalized)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="v0.5.13 missav_data.db (opened read-only)")
    parser.add_argument("--output", required=True, type=Path, help="私人迁移预览目录；不得指向正式主体库文件")
    args = parser.parse_args()

    source = args.source.resolve()
    output = args.output.resolve()
    if not source.exists() or source.suffix.lower() not in {".db", ".sqlite", ".sqlite3"}:
        raise SystemExit(f"找不到可读 SQLite 文件：{source}")
    output.mkdir(parents=True, exist_ok=True)

    uri = f"file:{source.as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        tables = {row[0] for row in connection.execute("select name from sqlite_master where type='table'")}
        required = {"codes", "actress_tags", "actress_code_map"}
        missing = sorted(required - tables)
        if missing:
            raise SystemExit(f"旧数据库缺少必要表：{', '.join(missing)}")
        seen_rows, candidate_rows, review_and_observed = build_rows(connection)
        observed_rows = [row for row in review_and_observed if "tag" in row]
        review_rows = [row for row in review_and_observed if "tag" not in row]
        files: dict[str, int] = {}
        files["preview/v0513-seen-candidates.csv"] = write_csv(
            output / "preview/v0513-seen-candidates.csv",
            ["tool", "canonical_key", "primary_value", "status", "legacy_id", "source"],
            seen_rows,
        )
        files["preview/v0513-library-candidates.csv"] = write_csv(
            output / "preview/v0513-library-candidates.csv",
            ["tool", "canonical_key", "primary_value", "secondary_value", "status", "tags", "genres", "folder", "first_seen_at", "last_seen_at", "seen_count", "rule_version", "legacy_id", "selection_state", "notes"],
            candidate_rows,
        )
        files["preview/v0513-review-candidates.csv"] = write_csv(
            output / "preview/v0513-review-candidates.csv",
            ["tool", "canonical_key", "primary_value", "secondary_value", "status", "tags", "genres", "folder", "first_seen_at", "last_seen_at", "seen_count", "rule_version", "legacy_id", "selection_state", "notes"],
            review_rows,
        )
        files["preview/v0513-observed-actress-tags.csv"] = write_csv(
            output / "preview/v0513-observed-actress-tags.csv",
            ["tag", "code_count", "candidate_reference"],
            observed_rows,
        )
        files["preview/v0513-raindrop-metadata.csv"] = write_legacy_metadata(connection, output / "preview/v0513-raindrop-metadata.csv")
    finally:
        connection.close()

    source_hash = sha256_file(source)
    manifest = {
        "format_version": "loveav-v0513-preview-v2",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": {"name": source.name, "sha256": source_hash, "read_only": True},
        "selection_policy": "Preview only. Merge confirmed rows into the single missav-library.csv using references/curated-library.md.",
        "counts": {"seen": len(seen_rows), "curated_candidates": len(candidate_rows), "review_candidates": len(review_rows), "observed_actress_tags": len(observed_rows)},
        "files": {},
    }
    for relative, count in files.items():
        target = output / relative
        manifest["files"][relative] = {"rows": count, "sha256": sha256_file(target)}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = [
        "# v0.5.13 数据迁移预览",
        "",
        f"- 源数据库：`{source.name}`",
        f"- 源 SHA-256：`{source_hash}`",
        f"- 已见番号：{len(seen_rows)}",
        f"- `ok` 主体库候选：{len(candidate_rows)}（仅预览，未写正式主体库）",
        f"- 待复核候选：{len(review_rows)}",
        f"- 观察到的女优 Tag：{len(observed_rows)}（仅候选，不自动加入参考库）",
        "",
        "这些 CSV 只是候选预览，不是第二套历史库。只有用户明确选择并确认后，才能按唯一主体库契约合并进 `missav-library.csv`。",
        "原始数据库未写入；现有规则与黑名单未读取或修改；凭据、Session、Telegram 原文未读取或导出。",
    ]
    (output / "MIGRATION_PREVIEW.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "source_sha256": source_hash, "files": files}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
