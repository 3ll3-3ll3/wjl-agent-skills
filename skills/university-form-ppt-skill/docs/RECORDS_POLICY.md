# Google Drive records policy

The only permanent per-generation archive is Google Drive.

Paths are separated by certification mode:

```text
大学PPT生成记录/学生认证/<中文学校名>/
大学PPT生成记录/教师认证/<中文学校名>/
```

Each run stores a matching MD/PPTX/PNG trio named with local minute precision: `YYYY-MM-DD_HH-mm`. Append `_<student_id>` only for a same-school, same-mode, same-minute collision.

MD must include certification type, template used, school data, original input, generated identity and numeric ID, campus/coordinates, QA result, and real Drive URLs for PPTX and PNG.

Archiving is mandatory and automatic. A run is complete only after the correct mode folder exists, the school subfolder exists, all three files upload, and folder readback confirms the trio.
