# Template assets

The workflow uses two current user-approved templates.

## Student

Path: `assets/certificate_template.pptx`

Expected SHA-256:
`3dfa888b44be1d1219bf07d6600f3f76ef20b13488d6b24ca5c09333102ab4e2`

Expected placeholders: one `{{name}}`, one `{{student_id}}`, two `{{school_name}}`.

## Faculty

Path: `assets/teacher_certificate_template.pptx`

Expected SHA-256:
`c0f315f563e96b4cd9696f8a6d9bd4f61efd5a9c241c34a1a07e880c3c5b47a9`

Expected placeholders: one `{{name}}`, one `{{facultyid}}`, two `{{school_name}}`.

If either template is replaced by the user, update the matching SHA, scripts/tests, and workflow docs in the same change. Any demo/non-valid markings present in the source template must remain visible.

If the repository binary does not match the expected SHA, template synchronization is incomplete and must not be reported as complete.
