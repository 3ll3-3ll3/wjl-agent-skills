#!/usr/bin/env python3
"""Generate a short random Chinese-pinyin demo identity for the certificate workflow."""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAMES_PATH = ROOT / "data" / "names.json"


def generate_identity(
    seed: int | None = None,
    student_id_length: int | None = None,
    max_name_chars: int = 11,
    id_prefix: str = "",
) -> dict[str, str]:
    """Generate a layout-friendly random demo identity.

    Current workflow rules:
    - prefer a short pinyin name;
    - use a fresh numeric Student ID;
    - normally use 7-8 digits;
    - do not add a fixed prefix unless a caller explicitly provides one.

    Rendered QA, not this helper, remains the final authority on first-line fit.
    """
    rng = random.Random(seed)

    if student_id_length is None:
        student_id_length = rng.choice((7, 8))
    if student_id_length not in (7, 8):
        raise ValueError("student_id_length must be 7 or 8 for the current workflow")
    if id_prefix and not id_prefix.isdigit():
        raise ValueError("id_prefix must contain digits only")
    if len(id_prefix) > student_id_length:
        raise ValueError("id_prefix cannot be longer than student_id_length")

    data = json.loads(NAMES_PATH.read_text(encoding="utf-8"))
    candidates = [
        (surname, given)
        for surname in data["surnames"]
        for given in data["given_names"]
        if len(surname["pinyin"]) + 1 + len(given["pinyin"]) <= max_name_chars
    ]
    if not candidates:
        raise ValueError("No pinyin name candidates satisfy max_name_chars")

    surname, given = rng.choice(candidates)
    tail_len = student_id_length - len(id_prefix)
    tail = "".join(str(rng.randrange(10)) for _ in range(tail_len))
    student_id = id_prefix + tail

    return {
        "first_name": surname["pinyin"],
        "last_name": given["pinyin"],
        "name": f"{surname['pinyin']} {given['pinyin']}",
        "student_id": student_id,
        "zh_name": f"{surname['zh']}{given['zh']}",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int)
    parser.add_argument(
        "--student-id-length",
        type=int,
        choices=(7, 8),
        default=None,
        help="Default: randomly choose 7 or 8 digits.",
    )
    parser.add_argument(
        "--id-prefix",
        default="",
        help="Optional explicit numeric prefix. Empty by default per current workflow.",
    )
    parser.add_argument("--max-name-chars", type=int, default=11)
    args = parser.parse_args()

    print(
        json.dumps(
            generate_identity(
                seed=args.seed,
                student_id_length=args.student_id_length,
                max_name_chars=args.max_name_chars,
                id_prefix=args.id_prefix,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
