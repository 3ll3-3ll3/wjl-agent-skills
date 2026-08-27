# LoveAV

[简体中文](README.md) | [English](README.en.md)

LoveAV is a local-first reusable Skill for Codex Desktop and other compatible AI tools. The Skill itself is the product; this directory does not store Telegram source messages, databases, tokens, sessions, or browser profiles by default.

## Canonical source repository

The canonical GitHub source for this Skill is [`3ll3-3ll3/wjl-agent-skills`](https://github.com/3ll3-3ll3/wjl-agent-skills). `loveav/` is maintained as a Skill directory inside that monorepo.

## Usage

1. Install or upload the entire `loveav` folder as a Skill.
2. Use `$loveav` in a conversation, then upload Telegram Desktop HTML/JSON, TXT/CSV/MD/LOG files, or paste text directly.
3. Specify the tool to run, time range, curated-library policy, and desired output. Processing is local/conversation-scoped by default and does not connect to Telegram.
4. After previewing results, select only the records you want to retain permanently. Unselected candidates do not enter the curated historical library.

## Skill language convention

`SKILL.md` follows an **English skeleton + Chinese business rules** convention:

- YAML metadata, `Trigger`, `Workflow`, tool/function names, paths, commands, JSON/API fields, and code remain English or keep their exact technical identifiers.
- Complex business rules, exception handling, prohibitions, acceptance criteria, and ambiguity-prone details are maintained in Simplified Chinese.
- Examples should match the actual user-input language.
- Avoid noisy sentence-level Chinese-English mixing; keep only exact technical identifiers inside an otherwise coherent sentence.

README and `references/` are human-facing business documentation and are Chinese-first. This file exists as a secondary English reading aid.

## v0.5.13 initialization

To initialize from a legacy v0.5.13 database, run `scripts/migrate_v0513_library.py`. It opens the legacy SQLite database read-only and produces `seen-index.csv`, curated candidates, review candidates, performer-tag candidates, and legacy Raindrop metadata. It does not create an active curated library by default. Only use `--activate-ok` after explicit confirmation.

## v0.5.13-compatible capabilities

- Baseline filters for MissAV, Twitter, Bad.news, and Haijiao, with suspicious-item review and confirmation-based learning for unknown formats.
- MissAV catalog normalization, detail links, browser scripts, reference performer tags, two-level blacklists, and three-folder Raindrop export.
- Unified input support for Telegram Desktop HTML/JSON, TXT, CSV, MD, LOG, multiple files, and pasted text.
- Curated result library, deduplication index, rule packs, TXT/CSV/JSON outputs, and the v0.5.13 business-data migration contract.
- Whos.tv solved-answer workflow with scraper generation, incremental cutoff state, JSON validation, four Markdown categories, and script archiving.
- 123AV catalog parsing, page evidence, and export rules; account actions are not enabled.
- Telegram Desktop file parsing, message normalization, and time filtering; personal API access, bots, historical backfill, checkpoints, and mark-as-read actions are not enabled.

Detailed rules live under `references/`. Adaptive rule learning is documented in `references/rule-learning.md`, and the curated-library contract is in `references/curated-library.md`.

## Version and boundaries

Rule baseline: Windows `missav-manager` v0.5.13 (stable commit `4e2aad0`). Networked parts of 123AV and Telegram remain compatibility references only. Default behavior is offline/local, does not mark messages as read, and does not write directly to Raindrop.

The five current primary functions are MissAV, Twitter, Bad.news, Haijiao, and Whos.tv solved answers.