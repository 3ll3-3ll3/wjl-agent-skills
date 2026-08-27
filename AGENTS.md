# AGENTS.md

This repository is a monorepo for personal Codex / agent Skills.

## Repository layout

- Each Skill lives under `skills/<skill-name>/`.
- Each Skill must have its own `SKILL.md` as its operational source of truth.
- Supporting scripts, references, assets, tests, and docs stay inside that Skill unless they are genuinely shared by multiple Skills.

## Editing rules

1. When a task targets one Skill, keep changes inside that Skill unless a root-level change is explicitly required.
2. Do not silently change behavior in unrelated Skills.
3. Preserve existing Skill-specific safety, data, template, and compatibility rules.
4. Do not commit runtime/private data, credentials, tokens, sessions, browser profiles, local databases, Telegram exports, or generated user records.
5. Prefer deterministic scripts for mechanical work and keep `SKILL.md` focused on workflow and decision rules.
6. Add shared code to `shared/` only after at least two Skills actually need the same implementation; avoid premature abstraction.
7. New personal Skills should normally be added to `skills/<skill-name>/` rather than created as standalone repositories.
8. Before declaring a migration or refactor complete, verify every affected Skill still contains its `SKILL.md` and required assets/tests.
9. For every new Skill and every edit to an existing Skill, apply the repository-wide Skill authoring language policy below. This policy also applies to Skills created in nested directories or future Skill collections inside this repository.

## Skill authoring language policy

This is a repository-wide operational convention for all current and future Skills.

### Machine-facing structure: English

Use English for machine-facing, integration-facing, and routing-sensitive content, including:

- Skill `name` and `description` metadata.
- Trigger and routing descriptions.
- Tool names, function names, class names, variable names, file paths, commands, environment variables, JSON keys, API fields, schemas, and code.
- Short structural headings or workflow labels when English improves consistency with agent/tool conventions.

### Business rules: Simplified Chinese

Use Simplified Chinese for nuanced human-authored operational content where precision and maintainability matter most, including:

- Complex business rules and domain-specific constraints.
- Exception handling and edge-case explanations.
- Prohibited actions, safety boundaries, and compatibility caveats.
- Acceptance criteria, final checks, and detailed validation requirements.
- Domain knowledge or instructions that would lose precision if unnecessarily translated into English.

### Examples and mixed-language rules

1. Examples should match the language users are actually expected to use; Chinese examples are preferred for Chinese workflows, while exact technical identifiers remain unchanged.
2. Avoid chaotic Chinese-English mixing inside a single rule. Write the rule as a coherent sentence in one language and preserve only exact technical identifiers, field names, commands, paths, APIs, and code in their original form.
3. Do not translate exact tool names, function names, placeholders, JSON/API fields, commands, environment variables, or file paths merely to make surrounding prose Chinese.
4. A Skill does not need artificial bilingual duplication. Prefer one precise operational source of truth over duplicated Chinese/English rule sets that may drift apart.
5. When an existing Skill uses a different language style, do not perform unrelated mass translation. Apply this policy when that Skill is materially edited, while preserving behavior and minimizing unnecessary diff noise.

### Recommended `SKILL.md` organization

When appropriate, prefer this default organization for new Skills:

1. Metadata — English.
2. Goal / scope — concise English or Chinese according to clarity.
3. Trigger / routing — English.
4. Workflow — English for structural steps; Chinese may be used where the step contains nuanced business logic.
5. Business rules — Simplified Chinese.
6. Edge cases / prohibitions — Simplified Chinese.
7. Final checks / acceptance criteria — Simplified Chinese by default, preserving exact technical identifiers.
8. Examples — match the real user-input language.

This is a default convention rather than a reason to rewrite stable content for style alone. Execution reliability, unambiguous instructions, and maintainability take priority.

## Documentation language policy

1. Simplified Chinese is the default human-facing documentation language for this repository.
2. Root `README.md` must remain Simplified Chinese. The secondary English version is `README.en.md`.
3. For Skill-level human-facing README files, use `README.md` for Simplified Chinese and `README.en.md` for English whenever both versions are maintained.
4. Update Chinese documentation first for important behavior, usage, compatibility, or boundary changes, then keep the English version synchronized.
5. Do not rename the Chinese default README to `README.zh-CN.md`; GitHub's default landing README should stay Chinese.
6. `SKILL.md` is an agent operational document and is exempt from mandatory bilingual duplication; execution reliability takes priority over presentation.
