# WJL Agent Skills

[简体中文](README.md) | [English](README.en.md)

This is my unified Codex / Agent Skills repository. It follows a common monorepo layout: multiple independent Skills live in one repository, and each Skill keeps its own `SKILL.md`, scripts, references, assets, tests, and local documentation.

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

Each directory under `skills/` is a relatively self-contained Skill that can be installed or used independently.

## Management conventions

- New personal Skills should normally be added under `skills/<skill-name>/` instead of creating a separate repository for every Skill.
- Each Skill must keep its own `SKILL.md`, together with Skill-specific scripts, references, assets, tests, and documentation.
- Shared code should only be extracted to a future `shared/` directory after two or more Skills genuinely reuse the same implementation.
- Runtime/private data, credentials, tokens, sessions, browser profiles, local databases, Telegram exports, and generated user records must not be committed.
- A Skill should be split back into a standalone repository only when independent releases, issues, distribution, or lifecycle management clearly justify it.

## Documentation language policy

This repository uses the following language order:

1. **Simplified Chinese is the default language.** `README.md` is written in Simplified Chinese and is the primary GitHub landing page.
2. **English is the secondary language.** English documentation uses `README.en.md`.
3. When human-facing documentation needs both languages, prefer the `README.md` + `README.en.md` naming pattern.
4. Chinese and English versions should stay structurally and semantically aligned. Important features, boundaries, and usage notes should be updated in Chinese first, then synchronized to English.
5. `SKILL.md` is an operational instruction file for agents and may use whichever language is most reliable for execution; duplicate translations are not required merely for presentation.

## Current Skills

- `skills/loveav`
- `skills/university-form-ppt-skill`

After migration, this repository is the primary source of truth for these Skills. New Skills should also be added here by default.