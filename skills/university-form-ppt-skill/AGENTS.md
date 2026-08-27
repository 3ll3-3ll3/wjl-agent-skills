# AGENTS.md

This repository is a single-purpose student/faculty university certificate workflow. Follow `SKILL.md` as the source of truth.

Key invariants:

- Determine `student` vs `faculty` mode before selecting a template.
- Student template: `assets/certificate_template.pptx`.
- Faculty template: `assets/teacher_certificate_template.pptx`.
- Student placeholders: `{{name}}`, `{{student_id}}`, `{{school_name}}`.
- Faculty placeholders: `{{name}}`, `{{facultyid}}`, `{{school_name}}`.
- Replace only approved placeholders for the selected template.
- Do not rebuild the slide or casually reformat it.
- The first line containing name + numeric ID must stay on one line.
- Bottom-right official English school name must stay on one line after rendered QA.
- Body replacements must remain inline with natural paragraph wrapping; never insert hard line breaks or hard-split words.
- A one-word-per-line or isolated-word layout after replacement is a QA failure. Later words must continue sequentially through the paragraph as normal English text.
- Preserve any demo/non-valid markings present in the selected source template.
- Student and faculty modes share the same chat field contract.
- Google Drive archive is mandatory and automatic, separated under `学生认证` and `教师认证`, with folder readback before completion.
- Per-school records never belong in GitHub.
