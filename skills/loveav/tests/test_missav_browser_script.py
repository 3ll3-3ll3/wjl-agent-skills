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
        self.assertEqual(hashlib.sha256(template.read_bytes()).hexdigest(), "309a30fbfaa39649daf3e8272b7fb4e4022ce2c05144bf27108551c0aa034e4c")
        self.assertEqual(hashlib.sha256(boundaries.read_bytes()).hexdigest(), "b872f9fde88f64feb6ab2181b5223cd5e8d8a09a9b348cce928b903b3f1bb4aa")

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
            self.assertEqual(report["actress_tags_before_blacklist"], 3)
            self.assertEqual(report["reference_blacklist_matches"], 1)
            self.assertEqual(report["reference_tags_injected"], 2)
            self.assertIn("ABF-123", generated)
            self.assertIn("FC2-PPV-1234567", generated)
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
