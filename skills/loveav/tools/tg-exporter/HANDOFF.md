# HANDOFF.md

> 当前开发/发布交接快照。任何 Agent 接手前先读 `AGENTS.md`，再读本文件；GitHub 当前事实优先。

更新时间：2026-09-08

# LoveAV 内嵌开发状态

- 本目录已完整迁入 `3ll3-3ll3/wjl-agent-skills/skills/loveav/tools/tg-exporter`，后续以此处为开发真源。
- 迁入来源提交：`4af25ad5e35d671cd6401a534767b1656c43944d`。
- 原独立仓库正式 v0.3.2、历史 Tag 与 Release 保持不变，不做归档或反向修改。
- 当前内嵌开发版本：v0.3.3，新增 `tgctl version --json` 与增强的 `tgctl status --json`，供 LoveAV 自动适配器检查版本、Schema、IPC 和能力。
- LoveAV 自动定位和多页读取逻辑位于上级 `scripts/tg_exporter_adapter.py`；TG Exporter 仍保持通用 Telegram 层，不内置 LoveAV/PikPak 业务分类。
- v0.3.3 当前是 LoveAV 仓库 PR #1 的 Candidate，不是正式 Release；不得修改或覆盖独立仓库的 v0.3.2 Release。

## 2026-09-08 LoveAV 第七功能执行层

当前开发分支：`codex/loveav-pikpak-redeem-executor`。尚未合并、未发布 Release、未对真实 Telegram 账号执行写入 E2E。

已实现：

1. `messages unread`：冻结 current-unread `lower/upper`，后续页复用 HMAC/query-bound cursor 和 snapshot token；
2. `send-capture`：在同一 daemon 请求内先订阅、再发送，有界等待并可选按 URL domain 过滤；
3. `messages mark-read`：只接受与会话及冻结边界绑定的签名 token，不允许越界 max-id；
4. 上级 LoveAV `run_pikpak_notification_redeem.py`：双来源冻结、关键词交集去重、即时兑换、URL+密码去重、收藏查重/写入、失败安全已读；
5. 第七功能默认只 dry-run，真实运行要求 `RUN_PIKPAK_REDEEM`；`WRITE_OUTCOME_UNKNOWN` 立即停止且不确认已读；
6. 测试环境的 daemon 任务与检查点被强制隔离到 `tmp_path`，不再触及用户真实 APPDATA。

本地自动化结果：

```text
LoveAV tests: 61 passed
embedded TG Exporter tests: 155 passed
compileall: PASS
git diff --check: PASS
real Telegram E2E: PASS (9/9 keyword jobs; 1 new resource saved; 9 already present; 0 review; 0 unknown write outcome)
read acknowledgement: one frozen source explicitly acknowledged; the other was deliberately not acknowledged because its frozen count proof was incomplete
Windows packaged build/smoke: PASS
GitHub Actions push run: 34226158199 = SUCCESS
GitHub Actions PR run: 34226163539 = SUCCESS
candidate code head: da4e5430634bc298d64123c2dcb8f4b26ae5c846
```

After the real E2E, a separate read-only snapshot reported zero current unread in both sources. Do not infer that LoveAV acknowledged the second source: the executor report explicitly says it did not; another Telegram client/state transition may have changed that source afterwards.

# Current Project State

- Repository: `3ll3-3ll3/tg-exporter`
- Current Production: **v0.3.2**
- Production release commit/tag: `79649668b9b45fad2783a0f8c6cc673205a9266a` / `v0.3.2`
- Formal Release: `https://github.com/3ll3-3ll3/tg-exporter/releases/tag/v0.3.2`
- Release PR: `#26` / source branch `codex/v0.3.2-sender-role-fix` / **merged**
- Current active candidate: **none for v0.3.2**
- Historical `v0.3.1` tag/Release remains immutable and was not moved or overwritten.
- A post-release docs-only main commit may sit after the release commit; Production binaries and the `v0.3.2` tag stay anchored to `79649668...`.

# What v0.3.2 shipped

v0.3.2 is a narrow sender-identification / `--sender-role` filtering patch on top of v0.3.1. It is **not** a broad reader redesign and is not LoveAV/PikPak-specific.

The shipped behavior:

1. before returning `unknown`, use Telegram-structured sender evidence including raw peer fields;
2. only a `messages.search` request with `--sender-role` may enable bounded sender-entity recovery;
3. cache sender resolution per request, including failed lookups, so one peer is not fetched once per message;
4. Telegram-explicit anonymous administrator → `sender_type=anonymous_admin`, `anonymous_admin=true`, `is_admin=true`, without guessing a user id;
5. Telegram-explicit current-chat send-as records the chat identity and can match admin role without claiming a specific individual;
6. current admin/owner matching still uses Telegram participant/admin truth;
7. `forward_origin` stays separate and cannot make the actual sender an admin;
8. textual `post_author` alone is not identity evidence;
9. no sender evidence still returns `unknown`;
10. ordinary GUI/manual export, ordinary history, and searches without `--sender-role` do not enable the patch's additional sender resolver.

Current-unread, Session ownership, IPC, daemon lifecycle, GUI export format/directories and media behavior are unchanged.

# Final PR validation

Final release-ready PR head:

```text
head: b86966544daf6be8b10a5324af2f6368b722d211
Windows PR run: 33396287090 = SUCCESS
full pytest: 147 passed in 2.07s
focused v0.3.1 baseline regressions: 45 passed in 0.65s
compileall: PASS
git diff --check: PASS
imports: PASS
source search-filter smoke: PASS
one-file GUI build: PASS
portable GUI build: PASS
tgctl build: PASS
packaged search-filter smoke: PASS
packaged SESSION_BUSY JSON/native exit=8: PASS
packaged GUI/tgctl smoke: PASS
tracked-worktree clean: PASS
```

Final v0.3.2 Candidate from that head:

```text
artifact: 9759610996
outer artifact ZIP SHA-256: ec8defa8bc69168283b47b6846fda8b4645e35585d04046bc70c13653773ff10
TGExporter-v0.3.2-windows-x64.exe: 3a50b5f4523d3dde15ecf05c7c1778cacdeb71e3c031fb4cfe25c6478fed551a
TGExporter-v0.3.2-windows-x64-portable.zip: 526b21a6c676f989d889b03078a6bc7ef05c21e14864cd97d326d1bcea882cf6
tgctl.exe: 98c92eeb0638537198b79f61b3941c1a3cff308a8a60025eba59ac5299d0da40
```

Candidate hashes are traceability only; Production was rebuilt from merged main.

# Formal v0.3.2 Release evidence

```text
merge/release commit: 79649668b9b45fad2783a0f8c6cc673205a9266a
Release workflow: 33396907992 = SUCCESS
tag: v0.3.2 -> 79649668b9b45fad2783a0f8c6cc673205a9266a
Release id: 379778987
draft: false
prerelease: false
```

Formal Release assets and GitHub-reported SHA-256 digests:

```text
TGExporter-v0.3.2-windows-x64.exe
  4a7809b706ad3ce4e6f4acb0f635cda811e34cdac651bd8268c90102e85a9c03
TGExporter-v0.3.2-windows-x64-portable.zip
  61017e8ef0a90c6bf17cdbd54bec9f10238fb29bb062ec6eed06a748e582935f
tgctl.exe
  28518a3cf15cc7751cafdfa058d2674e25b36d44c65b873c6bdc32bcf3264745
SHA256SUMS.txt asset digest
  f4597564152631d706aeb2f226cc3dd8e3e357f327926fde4515b5f9fd21301e
```

The formal Release workflow rebuilt one-file GUI, portable GUI and tgctl from merged main, re-ran full pytest, import/source search-filter checks, packaged search-filter regression, packaged `SESSION_BUSY` native exit=8, packaged smoke tests, prepared `SHA256SUMS.txt`, and created the Release while refusing to overwrite an existing historical tag/Release.

# Real Telegram status

A bounded read-only live Svip aggregate re-test was recommended but was **not executed** from the build environment. On 2026-08-31 the user explicitly authorized merging PR #26 and publishing v0.3.2 without waiting for that aggregate check. This is not a claim that the live Svip check passed.

Optional post-release read-only comparison:

```powershell
tgctl messages search --chat <Svip-ref> --sender-role admin --url-domain mypikpak.com --limit 500 --json
```

Only compare aggregate counts; do not publish real message bodies, URLs or media names. No send/forward/read-ack/media download/group mutation/Session reset is needed.

# Resume order

Read `AGENTS.md` → `HANDOFF.md` → `docs/CODEX_TGCTL.md` → verify GitHub `main`, latest Release and latest workflow. GitHub facts override this snapshot.
