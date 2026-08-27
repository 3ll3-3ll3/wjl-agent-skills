# PPT rules

## Templates and allowed replacements

Student template: `assets/certificate_template.pptx`
- `{{name}}` x1
- `{{student_id}}` x1
- `{{school_name}}` x2

Faculty template: `assets/teacher_certificate_template.pptx`
- `{{name}}` x1
- `{{facultyid}}` x1
- `{{school_name}}` x2

Only approved placeholders for the selected template may change.

## Shared visual invariants

Both modes follow the same rules: preserve slide size, background, theme, shapes, fonts, font sizes, colors, body text-box geometry, line/paragraph spacing, dates, department/specialty text, all other non-placeholder text, and overall layout. Prefer direct PPTX XML replacement rather than rebuilding text boxes.

The first body line containing name + numeric ID must remain one line. If it wraps, use a shorter random name, then a shorter 7–8 digit numeric ID. Do not alter body typography or geometry to make it fit.

Later body text must wrap naturally without hard line breaks or hard-split words. If replacement creates one-word-per-line wrapping, isolated words/fields, or fragments that no longer flow as a normal English paragraph, the output fails QA. The correct behavior is for all following words to move forward sequentially according to the original paragraph flow. Use only the smallest necessary local text-flow adjustment to restore that behavior.

The bottom-right official English school name must remain one line. Only this local area may receive the smallest necessary adaptation; never abbreviate the official school name.

Any demo/non-valid markings present in the selected source template must remain visible.

Every output must be rendered to PNG and visually inspected before delivery.
