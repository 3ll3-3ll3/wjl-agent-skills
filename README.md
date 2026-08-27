# WJL Agent Skills

Personal Codex / agent Skill monorepo.

## Structure

```text
wjl-agent-skills/
├── skills/
│   ├── loveav/
│   └── university-form-ppt-skill/
└── README.md
```

Each directory under `skills/` is a self-contained Skill and should keep its own `SKILL.md`, scripts, references/assets, tests, and documentation as needed.

## Management convention

- New personal Skills are added under `skills/<skill-name>/` instead of creating a new repository for every Skill.
- Each Skill owns its own `SKILL.md` and local supporting files.
- Shared code should only be extracted to a future `shared/` directory when two or more Skills genuinely reuse it.
- Runtime/private data, credentials, tokens, sessions, local databases, and user exports must not be committed.
- Mature Skills may be split into standalone repositories later only when independent releases, issues, or distribution justify it.

## Current Skills

- `skills/loveav`
- `skills/university-form-ppt-skill`

This repository is intended to be the primary source of truth for these Skills after migration.