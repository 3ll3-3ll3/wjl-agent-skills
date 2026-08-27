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
