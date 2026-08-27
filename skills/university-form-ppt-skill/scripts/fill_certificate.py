#!/usr/bin/env python3
"""Fill only approved placeholders in the selected student/faculty PPTX template."""
from __future__ import annotations

import argparse
import shutil
import tempfile
import zipfile
from pathlib import Path

try:
    from .random_identity import generate_identity
except ImportError:  # direct script execution
    from random_identity import generate_identity

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = {
    "student": ROOT / "assets" / "certificate_template.pptx",
    "faculty": ROOT / "assets" / "teacher_certificate_template.pptx",
}
EXPECTED = {
    "student": {"{{name}}": 1, "{{student_id}}": 1, "{{school_name}}": 2},
    "faculty": {"{{name}}": 1, "{{facultyid}}": 1, "{{school_name}}": 2},
}


def count_tokens(pptx: Path, tokens: tuple[str, ...] | None = None) -> dict[str, int]:
    token_list = tokens or ("{{name}}", "{{student_id}}", "{{facultyid}}", "{{school_name}}")
    counts = {k: 0 for k in token_list}
    with zipfile.ZipFile(pptx, "r") as zf:
        for info in zf.infolist():
            if info.filename.startswith("ppt/slides/slide") and info.filename.endswith(".xml"):
                text = zf.read(info.filename).decode("utf-8")
                for token in counts:
                    counts[token] += text.count(token)
    return counts


def fill(template: Path, output: Path, auth_type: str, name: str, numeric_id: str, school_name: str) -> None:
    expected = EXPECTED[auth_type]
    counts = count_tokens(template, tuple(expected))
    if counts != expected:
        raise SystemExit(f"Unexpected placeholder counts for {auth_type}: {counts}; expected {expected}")

    replacements = {"{{name}}": name, "{{school_name}}": school_name}
    replacements["{{student_id}}" if auth_type == "student" else "{{facultyid}}"] = numeric_id

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / output.name
        with zipfile.ZipFile(template, "r") as zin, zipfile.ZipFile(tmp, "w") as zout:
            for info in zin.infolist():
                payload = zin.read(info.filename)
                if info.filename.startswith("ppt/slides/slide") and info.filename.endswith(".xml"):
                    text = payload.decode("utf-8")
                    for token, value in replacements.items():
                        text = text.replace(token, value)
                    payload = text.encode("utf-8")
                zout.writestr(info, payload)
        shutil.move(tmp, output)

    remaining = count_tokens(output, tuple(expected))
    if any(remaining.values()):
        raise SystemExit(f"Output still contains placeholders: {remaining}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--auth-type", choices=("student", "faculty"), default="student")
    parser.add_argument("--template", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--school-name", required=True)
    parser.add_argument("--name")
    parser.add_argument("--student-id", dest="numeric_id")
    parser.add_argument("--faculty-id", dest="numeric_id")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--student-id-length", type=int, choices=(7, 8), default=7)
    parser.add_argument("--max-name-chars", type=int, default=12)
    args = parser.parse_args()

    identity = generate_identity(args.seed, student_id_length=args.student_id_length, max_name_chars=args.max_name_chars)
    name = args.name or identity["name"]
    numeric_id = args.numeric_id or identity["student_id"]
    template = args.template or TEMPLATES[args.auth_type]
    fill(template, args.output, args.auth_type, name, numeric_id, args.school_name)
    print(f"auth_type={args.auth_type}")
    print(f"name={name}")
    print(f"numeric_id={numeric_id}")
    print(f"school_name={args.school_name}")
    print(f"output={args.output}")
    print("qa_required=render_and_visually_check_first_line_body_natural_flow_no_one_word_per_line_and_bottom_right_school_name")


if __name__ == "__main__":
    main()
