#!/usr/bin/env python3
"""Inspect placeholder counts in the selected student/faculty template."""
from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = {
    "student": ROOT / "assets" / "certificate_template.pptx",
    "faculty": ROOT / "assets" / "teacher_certificate_template.pptx",
}
TOKENS = ("{{name}}", "{{student_id}}", "{{facultyid}}", "{{school_name}}")


def inspect(pptx: Path) -> dict[str, int]:
    counts = {t: 0 for t in TOKENS}
    with zipfile.ZipFile(pptx, "r") as zf:
        for info in zf.infolist():
            if info.filename.startswith("ppt/slides/slide") and info.filename.endswith(".xml"):
                text = zf.read(info.filename).decode("utf-8")
                for token in TOKENS:
                    counts[token] += text.count(token)
    return counts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pptx", type=Path, nargs="?")
    parser.add_argument("--auth-type", choices=("student", "faculty"), default="student")
    args = parser.parse_args()
    pptx = args.pptx or TEMPLATES[args.auth_type]
    for k, v in inspect(pptx).items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()
