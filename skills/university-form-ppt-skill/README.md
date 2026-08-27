# University Student/Faculty Form + PPT Skill

[English](README.md) | [简体中文](README.zh-CN.md)

This skill supports the same end-to-end workflow for two modes: **Student certification** and **Faculty certification**.

It identifies a university and role from a school name/email/domain or related clue, verifies official school/campus data, generates a short random Chinese-pinyin demo identity and numeric ID, fills the correct user-approved PPT template, renders the real PPT to PNG for QA, and automatically archives the completed three-file record to Google Drive.

## Templates

- Student: `assets/certificate_template.pptx`
- Faculty: `assets/teacher_certificate_template.pptx`

Student placeholders: `{{name}}`, `{{student_id}}`, `{{school_name}}`.
Faculty placeholders: `{{name}}`, `{{facultyid}}`, `{{school_name}}`.

## Google Drive archive

Records are separated by certification type:

```text
大学PPT生成记录/学生认证/<中文学校名>/
大学PPT生成记录/教师认证/<中文学校名>/
```

Every completed run stores matching minute-precision files:

```text
YYYY-MM-DD_HH-mm.md
YYYY-MM-DD_HH-mm.pptx
YYYY-MM-DD_HH-mm.png
```

Archiving is mandatory and automatic. A run is complete only after PPTX/PNG/MD upload and folder readback verification.

## Shared output contract

Student and faculty modes keep the same user-facing fields and order: Chinese school name, Official English Name, First name, Last name, Student ID, Address, City, State/Province, Postal/Zip code, then coordinates. In faculty mode the same generated numeric value is inserted into `{{facultyid}}`; the compatibility output label remains `Student ID` unless the user explicitly asks for `Faculty ID` wording.

## Shared PPT rules

Both modes preserve all non-placeholder formatting/content, keep name + numeric ID on the first line, allow later body text to wrap naturally, keep the bottom-right official English full school name on one line, preserve source-template demo/non-valid markings, and require an actual PPT-to-PNG render check before delivery.

If replacement causes one-word-per-line wrapping, isolated words/fields, or a broken paragraph flow, the output fails QA. The correct behavior is for following words to continue sequentially according to the original paragraph flow. Repair this with the smallest necessary local text-flow adjustment, never with artificial hard line breaks, hard-split words, or an abbreviated school name.

## Repository role

GitHub stores reusable workflow assets only: `SKILL.md`, docs, scripts, tests, and the latest approved student/faculty templates. Per-school generation records belong only in Google Drive.
