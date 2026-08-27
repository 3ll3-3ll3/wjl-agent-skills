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
            self.assertEqual(set(rows[0]["tags"].split(",")), {"女优甲", "女优乙"})
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
            ])
            result = self.run_script("--library", str(library), "--input", str(skill), "--commit", "--confirm", "WRITE_MISSAV_LIBRARY")
            self.assertEqual(result["counts"]["added"], 2)
            with library.open("r", encoding="utf-8", newline="") as handle:
                codes = [row["loveav_canonical_code"] for row in csv.DictReader(handle)]
            self.assertEqual(codes, ["110223-001", "PONDO-030326_001"])


if __name__ == "__main__":
    unittest.main()
