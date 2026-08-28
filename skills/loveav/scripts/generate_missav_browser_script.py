#!/usr/bin/env python3
"""从正式 MissAV 主体库生成已注入参考女优 Tag 的完整浏览器脚本。"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Iterable

from manage_missav_library import comparable_key, normalize_candidate


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE = ROOT / "assets" / "missav-browser-script.txt"
DEFAULT_TYPE_BOUNDARIES = ROOT / "assets" / "missav-type-boundary-tags.txt"
REFERENCE_BLACKLIST_FILE = "1-参考女优Tag库黑名单.txt"
EXPORT_BLACKLIST_FILE = "2-Raindrop导出黑名单.txt"

SYSTEM_TAGS = {"未知女优", "#未知女优", "需要查找", "已存在", "重复输入"}
EXPLICIT_TYPE_TAGS = {"教师", "女优", "女優", "演员", "演員", "VR"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_tag(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").lstrip("\ufeff")).strip()[:120]


def split_lines(path: Path | None) -> list[str]:
    if path is None:
        return []
    output: list[str] = []
    seen: set[str] = set()
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        tag = normalize_tag(raw)
        if tag.startswith("# "):
            continue
        if tag and tag not in seen:
            seen.add(tag)
            output.append(tag)
    return output


def resolve_blacklist_path(library: Path, explicit: Path | None, filename: str) -> Path:
    """优先使用显式路径，否则读取主体库同级数据树中的正式规则文件。"""
    path = explicit if explicit is not None else library.parent.parent / "rules" / filename
    if not path.is_file():
        raise FileNotFoundError(
            f"缺少正式黑名单文件：{path}。请恢复该文件，或通过命令行参数指定实际路径。"
        )
    return path


def type_boundaries(path: Path = DEFAULT_TYPE_BOUNDARIES) -> set[str]:
    return set(split_lines(path)) | SYSTEM_TAGS | EXPLICIT_TYPE_TAGS


def looks_like_actress_tag(tag: str, boundaries: set[str]) -> bool:
    if not tag or tag in boundaries or re.search(r"\s", tag) or len(tag) > 120:
        return False
    if re.search(r"https?:|www\.|\.com|\.ai", tag, re.I) or re.search(r"\d", tag):
        return False
    return bool(re.search(r"[\u3040-\u30ff\u3400-\u9fff]", tag) or re.fullmatch(r"[A-Za-z][A-Za-z.'_-]{1,39}", tag))


def actress_tags_from_value(value: object, boundaries: set[str]) -> list[str]:
    """沿用 v0.5.13 规则：从 Tags 开头读取，遇到类型边界或非女优形状即停止。"""
    output: list[str] = []
    for raw in str(value or "").split(","):
        tag = normalize_tag(raw)
        if tag in boundaries or not looks_like_actress_tag(tag, boundaries):
            break
        output.append(tag)
    return output


def parse_variants(value: object) -> list[dict[str, object]]:
    try:
        parsed = json.loads(str(value or "[]"))
    except json.JSONDecodeError as exc:
        raise ValueError("主体库包含无效的 loveav_variants_json。") from exc
    if not isinstance(parsed, list) or not all(isinstance(item, dict) for item in parsed):
        raise ValueError("主体库的 loveav_variants_json 必须是对象数组。")
    return parsed


def extract_reference_tags(library: Path, reference_blacklist: Iterable[str] = ()) -> tuple[list[str], dict[str, int]]:
    boundaries = type_boundaries()
    blocked = {normalize_tag(value) for value in reference_blacklist if normalize_tag(value)}
    output: list[str] = []
    seen: set[str] = set()
    row_count = 0
    variant_count = 0
    before_blacklist: set[str] = set()

    with library.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"tags", "loveav_variants_json"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError("所选文件不是 LoveAV 正式 missav-library.csv。")
        for row in reader:
            row_count += 1
            values = [row.get("tags", "")]
            variants = parse_variants(row.get("loveav_variants_json", ""))
            variant_count += len(variants)
            values.extend(variant.get("tags", "") for variant in variants)
            for value in values:
                for tag in actress_tags_from_value(value, boundaries):
                    before_blacklist.add(tag)
                    if tag in blocked or tag in seen:
                        continue
                    seen.add(tag)
                    output.append(tag)

    if not output:
        raise ValueError("正式主体库没有可注入的女优 Tag，或全部被第一层黑名单排除。")
    return output, {
        "library_rows": row_count,
        "source_variants": variant_count,
        "actress_tags_before_blacklist": len(before_blacklist),
        "reference_blacklist_matches": len(before_blacklist & blocked),
        "reference_tags_injected": len(output),
    }


def normalize_codes(values: Iterable[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for raw in values:
        code = normalize_candidate(raw)
        key = comparable_key(code)
        if code and key and key not in seen:
            seen.add(key)
            output.append(code)
    return output


def javascript_array(values: Iterable[str]) -> str:
    return json.dumps(list(values), ensure_ascii=False, indent=2)


def inject_script(template: str, codes: list[str], reference_tags: list[str], export_blacklist: list[str]) -> str:
    if "(async () =>" not in template:
        raise ValueError("MissAV 模板不是可直接运行的异步浏览器脚本。")

    code_pattern = re.compile(r"const\s+CODE_TEXT\s*=\s*`[\s\S]*?`\.trim\(\);")
    reference_pattern = re.compile(r"const\s+REFERENCE_ACTRESS_TAGS\s*=\s*\[[\s\S]*?\];")
    export_pattern = re.compile(r"const\s+RAINDROP_EXPORT_BLACKLIST_TAGS\s*=\s*\[[\s\S]*?\];")
    if not code_pattern.search(template) or not reference_pattern.search(template) or not export_pattern.search(template):
        raise ValueError("MissAV 模板缺少 CODE_TEXT、REFERENCE_ACTRESS_TAGS 或 RAINDROP_EXPORT_BLACKLIST_TAGS 占位区。")

    safe_codes = "\n".join(code.replace("`", "\\`").replace("${", "\\${") for code in codes)
    result = code_pattern.sub(lambda _: f"const CODE_TEXT = `{safe_codes}`.trim();", template, count=1)
    result = reference_pattern.sub(lambda _: f"const REFERENCE_ACTRESS_TAGS = {javascript_array(reference_tags)};", result, count=1)
    result = export_pattern.sub(lambda _: f"const RAINDROP_EXPORT_BLACKLIST_TAGS = {javascript_array(export_blacklist)};", result, count=1)
    return result.rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", type=Path, required=True, help="正式 missav-library.csv")
    parser.add_argument("--codes-file", type=Path, help="UTF-8、一行一个番号")
    parser.add_argument("--code", action="append", default=[], help="可重复传入的番号")
    parser.add_argument("--reference-blacklist", type=Path, help="第一层参考女优 Tag 黑名单 TXT")
    parser.add_argument("--export-blacklist", type=Path, help="第二层 Raindrop 导出黑名单 TXT")
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--output", type=Path, required=True, help="生成的完整 JavaScript 文件")
    args = parser.parse_args()

    raw_codes = list(args.code)
    if args.codes_file:
        raw_codes.extend(args.codes_file.read_text(encoding="utf-8-sig").splitlines())
    codes = normalize_codes(raw_codes)
    if not codes:
        raise ValueError("没有可写入脚本的合法番号。")

    reference_blacklist_path = resolve_blacklist_path(
        args.library, args.reference_blacklist, REFERENCE_BLACKLIST_FILE
    )
    export_blacklist_path = resolve_blacklist_path(
        args.library, args.export_blacklist, EXPORT_BLACKLIST_FILE
    )
    reference_blacklist = split_lines(reference_blacklist_path)
    export_blacklist = split_lines(export_blacklist_path)
    reference_tags, stats = extract_reference_tags(args.library, reference_blacklist)
    template = args.template.read_text(encoding="utf-8-sig")
    script = inject_script(template, codes, reference_tags, export_blacklist)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(script, encoding="utf-8", newline="\n")
    temporary.replace(args.output)

    report = {
        "library": str(args.library.resolve()),
        "library_sha256": sha256_file(args.library),
        "template": str(args.template.resolve()),
        "template_sha256": sha256_file(args.template),
        "reference_blacklist": str(reference_blacklist_path.resolve()),
        "reference_blacklist_sha256": sha256_file(reference_blacklist_path),
        "reference_blacklist_tags": len(reference_blacklist),
        "export_blacklist": str(export_blacklist_path.resolve()),
        "export_blacklist_sha256": sha256_file(export_blacklist_path),
        "output": str(args.output.resolve()),
        "output_sha256": sha256_file(args.output),
        "codes_injected": len(codes),
        "export_blacklist_tags_injected": len(export_blacklist),
        **stats,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
