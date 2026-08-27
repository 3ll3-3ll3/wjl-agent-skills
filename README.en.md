# WJL Agent Skills

[简体中文](README.md) | [English](README.en.md)

This is my unified Codex / Agent Skills monorepo. Multiple relatively independent Skills live under one repository, and each Skill keeps its own `SKILL.md`, scripts, references, assets, tests, and local documentation.

## Repository structure

```text
wjl-agent-skills/
├── skills/
│   ├── loveav/
│   └── university-form-ppt-skill/
├── AGENTS.md
├── README.md
└── README.en.md
```

## Management conventions

- New personal Skills normally go under `skills/<skill-name>/` rather than getting a separate repository.
- Each Skill owns its own `SKILL.md` and Skill-specific support files.
- Shared code should only be extracted after two or more Skills genuinely reuse the same implementation.
- Runtime/private data, credentials, tokens, sessions, browser profiles, local databases, Telegram exports, and generated user records must not be committed.
- Split a Skill into a standalone repository only when independent releases, issues, distribution, or lifecycle management clearly justify it.

## Skill language convention

`SKILL.md` files use an **English skeleton + Chinese business rules** convention.

Use English for machine-facing or routing-sensitive content such as:

- YAML metadata: `name`, `description`
- `Trigger` and `Workflow` structure
- tool/function/class/variable names
- file paths, commands, environment variables
- JSON keys, API fields, schemas, and code

Use Simplified Chinese for nuanced operational content such as:

- business rules and domain constraints
- exception handling and edge cases
- prohibited actions and safety boundaries
- acceptance criteria and final checks
- details that are easier to maintain precisely in Chinese

Examples should match the actual expected user language. Exact technical identifiers should remain unchanged instead of being translated for appearance.

Avoid noisy sentence-level Chinese-English mixing. Prefer a coherent sentence in one language while preserving only exact identifiers such as `school_name`, commands, paths, API fields, and placeholders.

## README language

Human-facing documentation remains Chinese-first:

- `README.md`: Simplified Chinese and the default GitHub landing page
- `README.en.md`: secondary English documentation

This is separate from the mixed-language convention used inside operational `SKILL.md` files.

## Current Skills

- `skills/loveav`
- `skills/university-form-ppt-skill`

This repository is the primary source of truth for these Skills.