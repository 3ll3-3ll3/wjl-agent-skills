#!/usr/bin/env python3
"""Prepare a timestamp-named student/faculty archive bundle for Google Drive.

Final destinations:
    大学PPT生成记录/学生认证/<中文学校名>/
    大学PPT生成记录/教师认证/<中文学校名>/

Local bundle preparation is not archive completion. The connected Drive workflow
must upload MD/PPTX/PNG and read the target folder back.
"""
from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path

MODE_FOLDER = {"student": "学生认证", "faculty": "教师认证"}
MODE_LABEL = {"student": "学生认证", "faculty": "教师认证"}
TEMPLATE_NAME = {"student": "certificate_template.pptx", "faculty": "teacher_certificate_template.pptx"}


def minute_record_stem(now: datetime | None = None) -> str:
    current = now or datetime.now().astimezone()
    return current.strftime("%Y-%m-%d_%H-%M")


def archive_folder(root: Path, auth_type: str, school_cn: str) -> Path:
    return root / MODE_FOLDER[auth_type] / school_cn


def choose_record_stem(folder: Path, student_id: str, now: datetime | None = None) -> str:
    stem = minute_record_stem(now)
    if any((folder / f"{stem}.{ext}").exists() for ext in ("md", "pptx", "png")):
        return f"{stem}_{student_id}"
    return stem


def require_real_drive_urls(ppt_url: str, png_url: str, prepare_only: bool) -> None:
    if prepare_only:
        return
    missing = []
    if not ppt_url.startswith(("https://drive.google.com/", "https://docs.google.com/")):
        missing.append("PPT")
    if not png_url.startswith(("https://drive.google.com/", "https://docs.google.com/")):
        missing.append("PNG")
    if missing:
        raise SystemExit("Final archive record requires real Google Drive URLs for: " + ", ".join(missing))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--archive-root", default="大学PPT生成记录")
    p.add_argument("--auth-type", choices=("student", "faculty"), required=True)
    p.add_argument("--school-cn", required=True)
    p.add_argument("--school-en", required=True)
    p.add_argument("--first-name", required=True)
    p.add_argument("--last-name", required=True)
    p.add_argument("--student-id", required=True)
    p.add_argument("--address", required=True)
    p.add_argument("--city", required=True)
    p.add_argument("--province", required=True)
    p.add_argument("--postal-code", required=True)
    p.add_argument("--latitude", required=True)
    p.add_argument("--longitude", required=True)
    p.add_argument("--ppt", required=True)
    p.add_argument("--png", required=True)
    p.add_argument("--campus", default="")
    p.add_argument("--source-clue", default="")
    p.add_argument("--qa", default="第一行单行；正文自然顺排；右下角官方英文校名单行；源模板演示标识保留")
    p.add_argument("--ppt-drive-url", default="")
    p.add_argument("--png-drive-url", default="")
    p.add_argument("--prepare-only", action="store_true")
    args = p.parse_args()

    require_real_drive_urls(args.ppt_drive_url, args.png_drive_url, args.prepare_only)

    archive_root = Path(args.archive_root).resolve()
    folder = archive_folder(archive_root, args.auth_type, args.school_cn)
    folder.mkdir(parents=True, exist_ok=True)
    now = datetime.now().astimezone()
    stem = choose_record_stem(folder, args.student_id, now)

    ppt_dst = folder / f"{stem}.pptx"
    png_dst = folder / f"{stem}.png"
    md_dst = folder / f"{stem}.md"
    shutil.copy2(args.ppt, ppt_dst)
    shutil.copy2(args.png, png_dst)

    full_name = f"{args.first_name} {args.last_name}".strip()
    lines = [
        f"# {args.school_cn}生成记录 — {stem}",
        "",
        f"- 认证类型：{MODE_LABEL[args.auth_type]}",
        f"- 使用模板：{TEMPLATE_NAME[args.auth_type]}",
        f"- 中文校名：{args.school_cn}",
        f"- 官方英文全名：{args.school_en}",
        f"- First name：{args.first_name}",
        f"- Last name：{args.last_name}",
        f"- 完整随机姓名：{full_name}",
        f"- Student ID：{args.student_id}",
        f"- Address：{args.address}",
        f"- City：{args.city}",
        f"- State/Province：{args.province}",
        f"- Postal/Zip code：{args.postal_code}",
    ]
    if args.campus:
        lines.append(f"- 校区：{args.campus}")
    lines += [
        f"- Latitude：{args.latitude}",
        f"- Longitude：{args.longitude}",
        f"- 生成时间：{now.isoformat(timespec='minutes')}",
    ]
    if args.source_clue:
        lines.append(f"- 用户原始输入：{args.source_clue}")
    lines += [f"- PPT 视觉验收：{args.qa}", ""]

    if args.ppt_drive_url:
        lines.append(f"[PPT 文件]({args.ppt_drive_url})")
    else:
        lines.append("[PPT 文件](待 Google Drive 上传成功后写入真实链接)")
    lines.append("")
    if args.png_drive_url:
        lines.append(f"![PPT 预览]({args.png_drive_url})")
    else:
        lines.append("![PPT 预览](待 Google Drive 上传成功后写入真实链接)")
    lines.append("")

    md_dst.write_text("\n".join(lines), encoding="utf-8")
    print(md_dst)
    if args.prepare_only:
        print("PREPARE_ONLY: Google Drive upload + folder readback are still required.")


if __name__ == "__main__":
    main()
