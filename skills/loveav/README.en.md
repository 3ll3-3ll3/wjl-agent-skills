# LoveAV

[简体中文](README.md) | [English](README.en.md)

LoveAV is a local-first reusable Skill for Codex Desktop and other compatible AI tools. The Skill itself is the product; this directory does not store Telegram source messages, databases, tokens, sessions, or browser profiles by default.

## Canonical source repository

The canonical GitHub source for this Skill is [`3ll3-3ll3/wjl-agent-skills`](https://github.com/3ll3-3ll3/wjl-agent-skills). `loveav/` is maintained as a Skill directory inside that monorepo. Future versions should use the monorepo as the source of truth instead of the former standalone `loveav` repository.

## Usage

1. Install or upload the entire `loveav` folder as a Skill.
2. Use `$loveav` in a conversation, then upload Telegram Desktop HTML/JSON, TXT/CSV/MD/LOG files, or paste text directly.
3. Specify the tool to run, the time range, whether records already present in the curated library should be excluded, and the desired output. By default, processing is local or conversation-scoped and does not connect to Telegram.
4. After previewing results, select only the records you want to retain permanently. Unselected candidates are not added to the historical deduplication library.

## Documentation language policy

The source documentation for this Skill—including `SKILL.md`, the README, and `references/`—is primarily maintained in Simplified Chinese. English is secondary and is intended for auxiliary reading or machine compatibility. When meanings differ, follow the Chinese source semantics. Commands, state values, field names, code, URLs, catalog identifiers, and filenames should remain unchanged rather than being translated.

To initialize from a legacy v0.5.13 database, run `scripts/migrate_v0513_library.py`. It opens the legacy SQLite database read-only and produces `seen-index.csv`, curated candidates, review candidates, performer-tag candidates, and legacy Raindrop metadata. It does not create an active curated library by default. Only use `--activate-ok` to activate `status=ok` candidates after explicit confirmation.

## v0.5.13-compatible capabilities

- Baseline filters for MissAV, Twitter, Bad.news, and Haijiao, with suspicious-item review and confirmation-based learning for unknown formats.
- MissAV catalog normalization, detail links, browser scripts, reference performer tags, two-level blacklists, and three-folder Raindrop export.
- Unified input support across the four preprocessing tools for Telegram Desktop HTML/JSON, TXT, CSV, MD, LOG, multiple files, and pasted text; includes time filtering, selection, deduplication, and historical semantics.
- Curated result library, deduplication index, rule packs, TXT/CSV/JSON outputs, and the v0.5.13 business-data migration contract.
- Whos.tv solved-answer workflow: console scraper, incremental cutoff state, JSON validation, four Markdown categories, and script-based archiving.
- 123AV catalog parsing, page evidence, and export rules; account actions such as favorites or follows are not enabled.
- Telegram Desktop file parsing, message normalization, and time filtering; personal API access, bots, historical backfill, checkpoints, and mark-as-read actions are not enabled.

Detailed rules live under `references/`. Adaptive rule learning is documented in `references/rule-learning.md`, and the curated-library contract is in `references/curated-library.md`. The Skill defines workflow, rules, and outputs only; this version does not include Telegram, Work/cloud, or remote-account executors.

## Version and boundaries

Rule baseline: Windows `missav-manager` v0.5.13 (stable commit `4e2aad0`). Networked parts of 123AV and Telegram are retained only as compatibility references and are not enabled in the current Skill. The default behavior is offline/local, does not mark messages as read, and does not write directly to Raindrop.

The five current primary functions are: MissAV, Twitter, Bad.news, Haijiao, and Whos.tv solved answers.
