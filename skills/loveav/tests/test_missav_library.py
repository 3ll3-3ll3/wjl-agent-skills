import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "manage_missav_library.py"


def write_csv(path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


class MissavLibraryTest(unittest.TestCase):
    def run_script(self, *args: str) -> dict:
        result = subprocess.run([sys.executable, str(SCRIPT), *args], text=True, encoding="utf-8", capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_merges_raindrop_and_skill_sources_without_duplicate_code(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            library = temp / "missav" / "library" / "missav-library.csv"
            official = temp / "raindrop.csv"
            skill = temp / "skill.csv"
            write_csv(official, ["id", "title", "note", "excerpt", "url", "folder", "tags", "created", "cover", "highlights", "favorite"], [
                {"id": "7", "title": "ABF-123", "note": "RD", "excerpt": "", "url": "https://missav.ai/cn/abf-123", "folder": "收藏 / 日本AV / MissAV", "tags": "女优甲", "created": "2026-08-01", "cover": "", "highlights": "", "favorite": "false"},
                {"id": "8", "title": "SHOULD-999", "note": "", "excerpt": "", "url": "https://example.com/SHOULD-999", "folder": "收藏 / 其他", "tags": "", "created": "", "cover": "", "highlights": "", "favorite": "false"},
            ])
            write_csv(skill, ["url", "title", "tags", "actress_tags", "type_tags", "status", "needs_lookup", "reference_matches", "excluded_from_raindrop", "export_blacklist_matches", "target_folder", "actress_raw", "matched_tag", "notes"], [
                {"url": "https://missav.ai/dm96/cn/ABF-123", "title": "ABF-123", "tags": "女优乙", "actress_tags": "女优乙", "type_tags": "", "status": "ok", "needs_lookup": "no", "reference_matches": "女优乙", "excluded_from_raindrop": "no", "export_blacklist_matches": "", "target_folder": "参考女优Tag命中", "actress_raw": "女优乙", "matched_tag": "女优乙", "notes": "Skill"},
            ])
            preview = self.run_script("--library", str(library), "--input", str(official), "--input", str(skill))
            self.assertEqual(preview["counts"]["added"], 1)
            self.assertEqual(preview["counts"]["out_of_scope"], 1)
            self.assertEqual(preview["counts"]["conflict"], 1)
            self.assertFalse(library.exists())

            committed = self.run_script("--library", str(library), "--input", str(official), "--input", str(skill), "--commit", "--confirm", "WRITE_MISSAV_LIBRARY")
            self.assertTrue(committed["committed"])
            with library.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["loveav_canonical_code"], "ABF-123")
            self.assertEqual(rows[0]["loveav_in_raindrop"], "true")
            self.assertEqual(rows[0]["loveav_in_skill_added"], "true")
            self.assertEqual(rows[0]["loveav_has_missav"], "true")
            self.assertEqual(rows[0]["loveav_has_123av"], "false")
            self.assertEqual(rows[0]["url"], "https://missav.ai/cn/abf-123")
            self.assertEqual(rows[0]["tags"], "女优乙")
            self.assertGreaterEqual(len(json.loads(rows[0]["loveav_variants_json"])), 2)

            repeated = self.run_script("--library", str(library), "--input", str(official), "--input", str(skill))
            self.assertEqual(repeated["counts"]["duplicate"], 2)
            self.assertFalse(repeated["write_required"])

    def test_supports_special_confirmed_code_shapes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            library = temp / "library" / "missav-library.csv"
            skill = temp / "skill.csv"
            headers = ["url", "title", "tags", "actress_tags", "type_tags", "status", "needs_lookup", "reference_matches", "excluded_from_raindrop", "export_blacklist_matches", "target_folder", "actress_raw", "matched_tag", "notes"]
            write_csv(skill, headers, [
                {"url": "https://missav.ai/dm558/110223-001", "title": "110223-001", "target_folder": "其他"},
                {"url": "https://missav.ai/dm166/pondo-030326_001", "title": "PONDO-030326_001", "target_folder": "其他"},
                {"url": "https://missav.ai/dm96/cn/MKBD-S03", "title": "MKBD-S03", "target_folder": "其他"},
            ])
            result = self.run_script("--library", str(library), "--input", str(skill), "--commit", "--confirm", "WRITE_MISSAV_LIBRARY")
            self.assertEqual(result["counts"]["added"], 3)
            with library.open("r", encoding="utf-8", newline="") as handle:
                codes = [row["loveav_canonical_code"] for row in csv.DictReader(handle)]
            self.assertEqual(codes, ["110223-001", "PONDO-030326_001", "MKBD-S03"])

    def test_prefers_newer_clean_tags_without_losing_old_variant(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            library = temp / "library" / "missav-library.csv"
            official = temp / "raindrop.csv"
            headers = ["id", "title", "note", "excerpt", "url", "folder", "tags", "created", "cover", "highlights", "favorite"]
            write_csv(official, headers, [
                {"id": "1", "title": "ABF-017", "url": "https://missav.ai/dm13/cn/abf-017", "folder": "日本av / MissAV", "tags": "女优甲, VR, 全高清_(FHD)", "created": "2026-07-25T05:34:01Z"},
                {"id": "2", "title": "ABF-017", "url": "https://missav.ai/cn/abf-017", "folder": "日本av / MissAV", "tags": "女优甲, 巨乳", "created": "2026-07-27T12:55:17Z"},
            ])
            result = self.run_script("--library", str(library), "--input", str(official), "--commit", "--confirm", "WRITE_MISSAV_LIBRARY")
            self.assertEqual(result["counts"]["added"], 1)
            self.assertEqual(result["counts"]["conflict"], 1)
            with library.open("r", encoding="utf-8", newline="") as handle:
                row = next(csv.DictReader(handle))
            self.assertEqual(row["url"], "https://missav.ai/cn/abf-017")
            self.assertEqual(row["tags"], "女优甲, 巨乳")
            self.assertNotIn("VR", row["tags"])
            self.assertEqual(len(json.loads(row["loveav_variants_json"])), 2)

    def test_includes_123av_combined_folder_and_root_detail_but_not_home(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            library = temp / "library" / "missav-library.csv"
            official = temp / "raindrop.csv"
            headers = ["id", "title", "note", "excerpt", "url", "folder", "tags", "created", "cover", "highlights", "favorite"]
            write_csv(official, headers, [
                {"id": "1", "title": "SIRO-5688", "url": "https://123av.fans/en/v/siro-5688-uncensored-leaked", "folder": "日本av / javxxx&123av"},
                {"id": "2", "title": "HMN-858", "url": "https://123av.com/cn/v/hmn-858", "folder": "日本av"},
                {"id": "3", "title": "123AV — Home", "url": "https://123av.com/cn", "folder": "日本av / 日本网站"},
            ])
            result = self.run_script("--library", str(library), "--input", str(official), "--commit", "--confirm", "WRITE_MISSAV_LIBRARY")
            self.assertEqual(result["counts"]["added"], 2)
            self.assertEqual(result["counts"]["out_of_scope"], 1)
            with library.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual([row["loveav_canonical_code"] for row in rows], ["SIRO-5688", "HMN-858"])
            self.assertTrue(all(row["loveav_has_123av"] == "true" for row in rows))
            self.assertTrue(all(row["loveav_has_missav"] == "false" for row in rows))

    def test_uses_full_fc2_from_trusted_123av_detail_when_title_is_truncated(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            library = temp / "library" / "missav-library.csv"
            official = temp / "raindrop.csv"
            headers = ["id", "title", "note", "excerpt", "url", "folder", "tags", "created", "cover", "highlights", "favorite"]
            write_csv(official, headers, [
                {"id": "1", "title": "PPV-253552", "url": "https://123av.com/cn/v/fc2-ppv-2535523", "folder": "日本av / javxxx&123av"},
            ])
            result = self.run_script("--library", str(library), "--input", str(official), "--commit", "--confirm", "WRITE_MISSAV_LIBRARY")
            self.assertEqual(result["counts"]["added"], 1)
            self.assertEqual(result["counts"]["review"], 0)
            with library.open("r", encoding="utf-8", newline="") as handle:
                row = next(csv.DictReader(handle))
            self.assertEqual(row["loveav_canonical_code"], "FC2-PPV-2535523")


if __name__ == "__main__":
    unittest.main()
