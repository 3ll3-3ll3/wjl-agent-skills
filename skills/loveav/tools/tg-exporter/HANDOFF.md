# HANDOFF.md

> LoveAV 内嵌 TG Exporter 当前开发交接快照。任何 Agent 接手前先读 `AGENTS.md`、本文件和 `docs/FORWARD_PROTOCOL.md`；GitHub 当前 branch/PR/CI 事实优先。

更新时间：2026-09-11

# 当前开发真源

- Repository: `3ll3-3ll3/wjl-agent-skills`
- Embedded path: `skills/loveav/tools/tg-exporter/`
- Embedded version: **v0.3.3**
- Active branch: `codex/loveav-tg-photo-forward`
- Branch base: `2a063a8423ed99518789f7deb7de1a3aba6abc98` (`main` at task start)
- Historical standalone repository `3ll3-3ll3/tg-exporter` is out of scope for this work. Do not modify, merge, tag, archive or publish it.
- This branch is Candidate-only. Do not merge `main`, create a tag, or publish a Release without a later explicit user authorization.

The embedded source originally came from standalone post-v0.3.2 state, but LoveAV now treats this directory as the development truth. Historical standalone v0.3.2 remains immutable traceability only.

# Current feature: native photo and album forward

The existing `tgctl forward --from --to --ids ...` CLI is kept compatible. The implementation now plans and executes Telegram-native forwarding for:

- existing text/web-preview messages;
- standalone Telegram photos, with or without caption;
- complete `grouped_id` photo albums;
- mixed standalone photos, text and multiple albums from one source.

The forward write path calls Telegram/Telethon `forward_messages` only. It does not download media, create local image files, or rebuild photos/captions with `send_message`.

## Album invariant

A requested message that belongs to a `grouped_id` album causes a bounded neighboring-ID discovery. The whole observed album is inserted as one atomic forward unit in source order. Album units are never split across Telegram forward batches.

If completeness cannot be established within the bounded scan, or one album member is protected/service/unsupported, the whole album is excluded rather than partially forwarded.

The existing 20-message default / 200-message explicit-large limit applies after album completion. `--allow-large-batch` remains the existing opt-in flag.

## Structured result

The historical `ForwardResult` fields remain. New machine-readable fields include:

```text
requested_count
forwardable_count
photo_count
album_count
planned_ids
expanded_ids
failures[]
albums[]
target_message_ids
forwarded[]
```

`failures[]` is per-message and uses stable codes such as:

```text
MESSAGE_NOT_FOUND
CONTENT_PROTECTED
SERVICE_MESSAGE
UNSUPPORTED_MESSAGE
ALBUM_INCOMPLETE
```

For a source with Telegram `noforwards` / protected content enabled, every requested item is `CONTENT_PROTECTED` and no write is attempted. There is no download-and-reupload bypass.

Dry-run performs the same planning/album expansion but never calls `forward_messages`.

A confirmed real write returns every destination-side generated message ID plus source→target mapping. If the transport/result becomes ambiguous, the command returns existing `WRITE_OUTCOME_UNKNOWN` semantics and never automatically replays the write. FloodWait remains structured and non-retrying.

# forward.capture decision

This Candidate does **not** advertise or implement `forward.capture` yet. Instead it provides a generic reconciliation contract:

1. `forward` returns `target_message_ids` and `forwarded` source→target pairs;
2. LoveAV can immediately call rich `messages get` on those destination IDs;
3. destination message IDs and `forward_origin` can be used for native-forward reconciliation;
4. later bot replies can be read with existing bounded history/search and caller-maintained before/after boundaries.

No PikPak name, group name, bot identity or success phrase is hard-coded in TG Exporter.

Advertised generic capabilities:

```text
forward.photos
forward.albums.atomic
forward.target_message_ids
```

See `docs/FORWARD_PROTOCOL.md` for the protocol contract.

# Privacy and safety

Do not commit or log real Telegram group names, chat IDs, message/caption bodies, URLs, media filenames, API credentials, phone/OTP/2FA, Session contents, access hashes, file references or IPC secrets.

New native-forward logs are aggregate-count only. Tests use synthetic IDs/messages only. No real Telegram write is required or permitted for automated CI.

# Required automated acceptance

Before calling this branch a Candidate, the final PR head must pass:

```text
full embedded TG Exporter pytest
LoveAV tgctl adapter pytest
explicit v0.3.1 baseline regressions
photo/album forward regressions
compileall
git diff --check
GUI + daemon + reader + CLI import check
source search-filter smoke
one-file GUI build
portable GUI build
tgctl.exe build
packaged search-filter smoke
packaged machine-readable version contract
packaged SESSION_BUSY native exit=8
packaged TGExporter/tgctl smoke (including forward planner import/smoke)
clean tracked worktree
Candidate asset generation + SHA-256
```

Feature regressions must cover at least: photo+caption, complete album, multiple albums plus standalone photo, dry-run no write, no `download_media`, protected content, partial missing message, service message exclusion, FloodWait, `WRITE_OUTCOME_UNKNOWN`, target message IDs, and legacy text-forward behavior.

# Current validation status

Implementation is in progress on `codex/loveav-tg-photo-forward`. Do not copy transient intermediate commit hashes into downstream tooling. The PR body should be updated with the final green head, workflow run, Candidate artifact ID and SHA-256 after CI is complete.

# Resume order

1. Verify `wjl-agent-skills/main` and branch head.
2. Read `AGENTS.md`, this file, and `docs/FORWARD_PROTOCOL.md`.
3. Inspect the latest PR CI rather than old standalone release CI.
4. Keep all work inside the LoveAV embedded TG Exporter unless a narrowly necessary LoveAV adapter compatibility change is separately justified.
5. Do not merge/tag/release this branch during the current task.
