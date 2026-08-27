---
name: university-form-ppt-skill
description: Identify a university and certification mode from a school name/email/domain or related clue, verify official school/campus data, generate a short random Chinese-pinyin demo identity, fill the matching latest user-approved student or faculty PPT template, render-check the result, and automatically archive the completed record to the correct Google Drive branch.
---

# University Student/Faculty Certificate + Drive Archive Skill

`SKILL.md` is the operational source of truth for this repository.

## 1. Trigger and automatic execution

When the user provides an obvious university clue, execute the full workflow directly without asking whether to proceed. Inputs may include:

- Chinese/English university name;
- student or faculty email address;
- student or faculty email domain, including a bare domain such as `@stu.scu.edu.cn`;
- college/school/faculty name;
- another clear clue tied to one university.

The workflow has two certification modes:

- `student` = 学生认证;
- `faculty` = 教师认证.

Determine the mode from the user's wording and the verified role/domain evidence. Obvious student domains/addresses select student mode; obvious faculty/staff/teacher addresses select faculty mode. If the institution is clear but the role genuinely cannot be determined, ask only for the certification mode instead of guessing.

Do not infer a person's real name from an email username/local-part.

## 2. University research and verification

Identify the institution and verify, in priority order, through:

1. the university's official website;
2. official admissions pages;
3. official international/exchange pages;
4. official contact/information-disclosure pages;
5. reliable map/geographic sources after the campus/address has been verified.

Verify:

- official Chinese university name;
- official English full name;
- main/representative campus or campuses;
- Address;
- City;
- State/Province;
- Postal/Zip code;
- campus coordinates.

Never self-translate, abbreviate, shorten, or invent the official English university name. Use the same verified official English full name in every `{{school_name}}` replacement.

## 3. Campus and coordinate rules

- Address and coordinates must refer to real, corresponding campuses.
- Prefer WGS84 output; normalize GCJ-02/BD-09 internally when necessary.
- One relevant campus: output one Latitude/Longitude pair.
- Multiple campuses: output at most the two most important/common/representative campuses, clearly labeled.
- The form address must correspond to the selected primary campus.
- Never fabricate an address, postal code, campus, or coordinate.

## 4. Random identity and output fields

For every run:

- generate a normal two- or three-character Chinese name;
- transliterate it to pinyin;
- prefer short combinations to protect the first PPT line;
- project-specific convention: `First name` = surname pinyin; `Last name` = given-name pinyin;
- PPT `{{name}}` = `SurnamePinyin GivenNamePinyin`.

Generate a fresh numeric ID for every run:

- normally 7–8 digits;
- no fixed institutional prefix unless explicitly requested;
- the same generated numeric value is used as `{{student_id}}` in student mode or `{{facultyid}}` in faculty mode;
- for compatibility with the established chat/form workflow, the returned field label remains `Student ID` in both modes unless the user explicitly asks for `Faculty ID` wording.

If the first line wraps, first regenerate a shorter name, then a shorter numeric ID, then render again. Do not solve first-line overflow by changing body font, body font size, line spacing, body text-box geometry, or body position.

## 5. Student and faculty templates

Use the latest user-approved template for the selected mode:

- student: `assets/certificate_template.pptx`
  - current SHA-256: `3dfa888b44be1d1219bf07d6600f3f76ef20b13488d6b24ca5c09333102ab4e2`
- faculty: `assets/teacher_certificate_template.pptx`
  - current SHA-256: `c0f315f563e96b4cd9696f8a6d9bd4f61efd5a9c241c34a1a07e880c3c5b47a9`

Current expected placeholder counts:

### Student template
- `{{name}}`: 1
- `{{student_id}}`: 1
- `{{school_name}}`: 2

### Faculty template
- `{{name}}`: 1
- `{{facultyid}}`: 1
- `{{school_name}}`: 2

Only replace the approved placeholders for the selected template. Prefer direct replacement inside PPTX XML so text boxes are not rebuilt.

## 6. PPT format protection

Except for approved placeholder text, preserve the selected template as far as practical, including:

- slide/page size;
- background/images/shapes/theme;
- body font, size, color;
- line/paragraph spacing;
- body text-box size and position;
- dates;
- school/department text;
- specialty/program text;
- all other non-placeholder text;
- overall layout.

Do not rebuild the slide from scratch.

## 7. Natural flow and signature

- The first line containing the name and numeric ID must remain one line.
- Later body text must wrap naturally as a continuous English paragraph.
- If replacement makes later text collapse into one-word-per-line, isolated words/fields, or non-flowing fragments, the PPT fails QA and must be adjusted before delivery.
- Correct behavior: words after the replacement move forward sequentially according to the original paragraph flow, not as one word per line.
- Never insert artificial hard line breaks or hard-split words.
- The bottom-right school-name signature must use the official English full name and stay on one line.
- If necessary for body-flow repair, use the smallest local treatment that restores normal paragraph flow, such as normalizing/merging the body text flow or minimally adjusting body text-box width, character spacing, or paragraph layout. Do not change the overall visual design.
- If necessary, only the bottom-right school-name area may receive the smallest local width/position/character-spacing/font-size adjustment.
- Never replace the official full name with an abbreviation.

## 8. Demo/non-valid markings

If the selected template contains `SAMPLE / NOT VALID`, `仅供演示，不具效力`, or another explicit demo/non-valid marking, preserve it visibly. Do not delete, hide, crop, cover, or weaken it to invisibility.

## 9. Required rendering and visual QA

Every generated PPT must be actually rendered to PNG before delivery. AI-generated images are never a substitute.

Check all applicable items:

1. name + numeric ID stay on the first line;
2. the ID is not stranded on a new line;
3. later body text flows naturally, with no one-word-per-line layout or isolated replacement-created fragments;
4. body school name is the verified official English full name;
5. bottom-right school name is the same full name;
6. bottom-right school name remains one line;
7. non-placeholder content was not unintentionally changed;
8. layout/formatting remains normal;
9. source-template demo/non-valid markings remain visible.

If any check fails, regenerate/fix and render again before delivery.

## 10. Chat delivery order and field schema

Student and faculty modes use the same chat field set and ordering:

1. actual PNG rendered from the PPT;
2. PPTX file;
3. Chinese university name;
4. Official English Name;
5. First name;
6. Last name;
7. Student ID;
8. Address;
9. City;
10. State/Province;
11. Postal/Zip code;
12. coordinates last.

Each form field must be in its own copyable code block. Do not output Country/Region, Address line 2, or VAT/GST ID unless explicitly requested.

## 11. Google Drive archive — mandatory, automatic, separated by mode

Every generation must automatically archive in the same workflow. Do not wait for a second user message.

Permanent paths:

- student: `大学PPT生成记录/学生认证/<中文学校名>/`
- faculty: `大学PPT生成记录/教师认证/<中文学校名>/`

Each run stores exactly three matching files:

- `<record_stem>.md`
- `<record_stem>.pptx`
- `<record_stem>.png`

The PNG must be rendered from the actual final PPT.

### Record naming

Use the local generation date/time precise to one minute:

`YYYY-MM-DD_HH-mm`

If the same school and certification mode receives another record in the same minute, append `_<student_id>` only to prevent collision.

### MD content

The Markdown record must contain at least:

- certification type (`学生认证` or `教师认证`);
- template used;
- Chinese university name;
- official English full name;
- user's original input;
- First name;
- Last name;
- full random pinyin name;
- Student ID (the generated numeric ID used by the selected template);
- Address;
- City;
- State/Province;
- Postal/Zip code;
- selected campus/campuses;
- coordinate pair(s);
- PPT QA result;
- real Google Drive PPT URL;
- real Google Drive PNG URL.

Never fabricate or pre-compose Drive URLs.

### Completion gate

Google Drive archiving is a hard completion gate:

- ensure the correct mode folder exists;
- ensure the school subfolder exists under that mode;
- upload final PPTX;
- upload final rendered PNG;
- create/update MD using the real returned PPT/PNG Drive URLs;
- upload MD;
- read the target school folder back and confirm the expected MD/PPTX/PNG files exist.

Do not consider the run fully complete until all steps succeed. If any external step fails, explicitly state `该步骤当前没有成功完成。` Never claim an upload, render, GitHub write, commit, replacement, or readback succeeded unless it actually did.

## 12. REDO

If any generated record is wrong, perform a complete REDO:

PPT regenerate/fix text flow -> PNG render -> visual QA -> replace/update Drive PPTX -> replace/update Drive PNG -> update Drive MD -> Drive readback verification.

Do not fix only the chat artifact while leaving an incorrect Drive version behind.

## 13. GitHub repository role

GitHub stores the reusable workflow, not per-school generation records. Maintain:

- `SKILL.md`;
- English/Chinese README/docs;
- research/PPT/output/archive rules;
- identity generation code;
- student/faculty PPT generation code;
- archive helper code;
- tests;
- latest user-approved student template;
- latest user-approved faculty template.

Per-school MD/PPTX/PNG records belong only in Google Drive.

## 14. Rule synchronization invariant

When the user changes this workflow permanently, synchronize as applicable:

1. `SKILL.md`;
2. relevant English docs;
3. relevant Chinese docs;
4. related scripts;
5. related tests;
6. student/faculty templates when explicitly replaced.

If any required repository update cannot be completed, explicitly report the unsynchronized part. Never pretend a commit occurred.

## 15. Default end-to-end flow

Identify school -> determine student/faculty mode -> verify official Chinese/English names -> choose representative campus/campuses -> verify address/postal code -> verify coordinates -> generate short random pinyin name -> generate 7–8 digit numeric ID -> select matching latest template -> replace only approved placeholders -> verify first line/body natural flow/signature -> render PNG -> visual QA -> prepare chat artifacts/fields -> automatically archive MD/PPTX/PNG to the correct Drive mode folder -> read back Drive folder -> only then claim the run is fully complete.