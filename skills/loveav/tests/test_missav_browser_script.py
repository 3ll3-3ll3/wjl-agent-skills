from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "generate_missav_browser_script.py"


class MissavBrowserScriptTest(unittest.TestCase):
    def test_bundled_assets_match_v0513_baseline(self) -> None:
        template = ROOT / "assets" / "missav-browser-script.txt"
        boundaries = ROOT / "assets" / "missav-type-boundary-tags.txt"
        # Git may materialize the same text asset with LF or CRLF.  The
        # v0.5.13 contract is the script text, not the checkout's newline
        # convention, so hash its canonical LF representation.
        template_bytes = template.read_text(encoding="utf-8").replace("\r\n", "\n").encode("utf-8")
        boundary_bytes = boundaries.read_text(encoding="utf-8").replace("\r\n", "\n").encode("utf-8")
        self.assertEqual(hashlib.sha256(template_bytes).hexdigest(), "f6e00d62cc0df9ee0b7a266f3278f1d3fb1685efe13144117e7081867bccdb5c")
        self.assertEqual(hashlib.sha256(boundary_bytes).hexdigest(), "7afbc6e0d1d9607ba60700478288c64d4c62d5687d7d34dd3422857bd3a25ea4")

    def test_blacklist_comment_lines_are_not_tags(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "blacklist.txt"
            path.write_text("# 当前为空\n#真实标签\n女优甲\n", encoding="utf-8")
            sys.path.insert(0, str(ROOT / "scripts"))
            try:
                from generate_missav_browser_script import split_lines

                self.assertEqual(split_lines(path), ["#真实标签", "女优甲"])
            finally:
                sys.path.pop(0)

    def test_generated_script_removes_only_proven_wasted_waits(self) -> None:
        sys.path.insert(0, str(ROOT / "scripts"))
        try:
            from generate_missav_browser_script import (
                RUNTIME_OPTIMIZATION_VERSION,
                apply_runtime_optimization,
            )

            template = (ROOT / "assets" / "missav-browser-script.txt").read_text(
                encoding="utf-8"
            )
            optimized = apply_runtime_optimization(template)
            self.assertEqual(RUNTIME_OPTIMIZATION_VERSION, "safe-fetch-v1")
            self.assertIn("e?.retryable !== false", optimized)
            self.assertIn("[408, 425, 429].includes(res.status) || res.status >= 500", optimized)
            self.assertIn("if (urlIndex + 1 < urls.length) await sleep(250);", optimized)
            self.assertIn("if (i + 1 < codesToProcess.length) await sleep(DELAY_MS);", optimized)
            self.assertNotIn("if (!res.ok) throw new Error(`HTTP ${res.status}`);", optimized)
            self.assertIn("const DELAY_MS = 900;", optimized)
            self.assertIn("const MAX_RETRY = 1;", optimized)
        finally:
            sys.path.pop(0)

    def test_uses_all_library_actress_tags_and_applies_both_blacklists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            library = temp / "missav-library.csv"
            codes = temp / "codes.txt"
            reference_blacklist = temp / "reference-blacklist.txt"
            export_blacklist = temp / "export-blacklist.txt"
            output = temp / "script.js"

            fields = ["loveav_canonical_code", "tags", "loveav_variants_json"]
            with library.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerow({
                    "loveav_canonical_code": "ABF-001",
                    "tags": "女优甲,女优乙,巨乳,VR",
                    "loveav_variants_json": json.dumps([
                        {"tags": "女优丙,苗条,全高清_(FHD)"},
                        {"tags": "女优甲,VR"},
                    ], ensure_ascii=False),
                })
                writer.writerow({
                    "loveav_canonical_code": "ABF-002",
                    "tags": "需要查找,#未知女优",
                    "loveav_variants_json": "[]",
                })

            codes.write_text("abf_123\nABF-123\nFC2 1234567\n无效内容\n", encoding="utf-8")
            reference_blacklist.write_text("女优乙\n", encoding="utf-8")
            export_blacklist.write_text("女优丙\n", encoding="utf-8")
            result = subprocess.run([
                sys.executable, str(SCRIPT),
                "--library", str(library),
                "--codes-file", str(codes),
                "--reference-blacklist", str(reference_blacklist),
                "--export-blacklist", str(export_blacklist),
                "--output", str(output),
            ], text=True, encoding="utf-8", capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            generated = output.read_text(encoding="utf-8")

            self.assertEqual(report["codes_injected"], 2)
            self.assertEqual(report["runtime_optimization"], "safe-fetch-v1")
            self.assertEqual(report["workspace_launcher"], "remembered-results-v2")
            self.assertEqual(report["actress_tags_before_blacklist"], 3)
            self.assertEqual(report["reference_blacklist_matches"], 1)
            self.assertEqual(report["reference_tags_injected"], 2)
            self.assertIn("ABF-123", generated)
            self.assertIn("FC2-PPV-1234567", generated)
            self.assertIn("手动选择当前女优 Tag 合集", generated)
            self.assertNotIn("选择旧女优 tag 合集 CSV", generated)
            self.assertIn("loveav-missav-workspace-v1", generated)
            self.assertIn("LOVEAV_DEFAULT_RESULTS_PATH_HINT", generated)
            self.assertIn(r"E:\\Desktop\\codex项目\\LoveAV-Data\\missav\\results", generated)
            self.assertIn("授权 / 更换默认工作目录", generated)
            self.assertIn("重新扫描最新女优 Tag 合集", generated)
            self.assertIn("正在打开目录选择器", generated)
            self.assertIn("正在重新扫描最新女优 Tag 合集", generated)
            self.assertIn("目录已更新；扫描完成", generated)
            self.assertIn("重新扫描完成", generated)
            workspace_handler = generated.split(
                "panel.querySelector('#missav-pick-workspace').onclick", 1
            )[1].split("panel.querySelector('#missav-rescan').onclick", 1)[0]
            self.assertIn("await chooseAndRememberResultsDirectory()", workspace_handler)
            self.assertNotIn("readRememberedResultsDirectory", workspace_handler)
            permission_helper = generated.split(
                "async function hasDirectoryPermission", 1
            )[1].split("function isCollectionCsvName", 1)[0]
            self.assertLess(
                permission_helper.index("handle.requestPermission"),
                permission_helper.index("handle.queryPermission"),
            )
            self.assertIn("indexedDB.open(LOVEAV_WORKSPACE_DB, 1)", generated)
            self.assertIn("await findLatestCollectionCsv(handle)", generated)
            self.assertIn("await createOutputDirectory(state.baseDirHandle)", generated)
            self.assertNotIn("请选择基础输出文件夹：E:\\Desktop\\王家乐", generated)
            self.assertIn('"女优甲"', generated)
            self.assertIn('"女优丙"', generated)
            self.assertNotIn('"女优乙"', generated)
            self.assertNotIn('"巨乳"', generated)
            self.assertIn("const RAINDROP_EXPORT_BLACKLIST_TAGS = [\n  \"女优丙\"\n];", generated)

    def test_rejects_non_library_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            library = temp / "wrong.csv"
            output = temp / "script.js"
            library.write_text("title,tags\nABF-001,女优甲\n", encoding="utf-8")
            result = subprocess.run([
                sys.executable, str(SCRIPT),
                "--library", str(library),
                "--code", "ABF-001",
                "--output", str(output),
            ], text=True, encoding="utf-8", capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(output.exists())

    def test_uses_default_blacklists_next_to_library_data_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "missav"
            library_dir = root / "library"
            rules_dir = root / "rules"
            library_dir.mkdir(parents=True)
            rules_dir.mkdir()
            library = library_dir / "missav-library.csv"
            output = Path(temp_dir) / "script.js"

            with library.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["loveav_canonical_code", "tags", "loveav_variants_json"],
                )
                writer.writeheader()
                writer.writerow({
                    "loveav_canonical_code": "ABF-001",
                    "tags": "女优甲,女优乙,巨乳",
                    "loveav_variants_json": "[]",
                })

            (rules_dir / "1-参考女优Tag库黑名单.txt").write_text(
                "女优乙\n", encoding="utf-8"
            )
            (rules_dir / "2-Raindrop导出黑名单.txt").write_text(
                "女优甲\n", encoding="utf-8"
            )
            result = subprocess.run([
                sys.executable,
                str(SCRIPT),
                "--library",
                str(library),
                "--code",
                "ABF-001",
                "--output",
                str(output),
            ], text=True, encoding="utf-8", capture_output=True)

            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            generated = output.read_text(encoding="utf-8")
            self.assertEqual(report["reference_blacklist_tags"], 1)
            self.assertEqual(report["export_blacklist_tags_injected"], 1)
            self.assertIn('"女优甲"', generated)
            self.assertNotIn('"女优乙"', generated)
            self.assertIn("1-参考女优Tag库黑名单.txt", report["reference_blacklist"])

    def test_missing_default_blacklist_stops_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "missav"
            library_dir = root / "library"
            library_dir.mkdir(parents=True)
            library = library_dir / "missav-library.csv"
            output = Path(temp_dir) / "script.js"
            library.write_text(
                "loveav_canonical_code,tags,loveav_variants_json\n"
                'ABF-001,"女优甲,巨乳",[]\n',
                encoding="utf-8",
            )
            result = subprocess.run([
                sys.executable,
                str(SCRIPT),
                "--library",
                str(library),
                "--code",
                "ABF-001",
                "--output",
                str(output),
            ], text=True, encoding="utf-8", capture_output=True)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("缺少正式黑名单文件", result.stderr)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
