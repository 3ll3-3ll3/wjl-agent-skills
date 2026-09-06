# Testing Guide — v0.3.1 Candidate

本项目测试分四层：

1. unit/mock：模型、cursor、reader/filter、daemon scheduling、GUI 行为、安全边界；
2. Windows package CI：TGExporter/tgctl PyInstaller、真实 OS Session lock、native exit code、最终 EXE smoke；
3. Candidate artifact：one-file + portable + tgctl + SHA-256；
4. 用户真实 Telegram E2E。

**CI green 不等于真实账号 E2E。**

## 1. CI 基线

使用项目独立虚拟环境：

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m compileall src
git diff --check
```

v0.3.1 Candidate gate 至少要求：

```text
full pytest
v0.3.1 domain / regex / GUI-shutdown / sender focused regressions
compileall
git diff --check
GUI + daemon + reader + CLI import
source search-filter offline smoke
TGExporter one-file PyInstaller
TGExporter portable onedir PyInstaller
tgctl one-file PyInstaller
standalone + portable packaged domain+regex search-filter smoke
standalone + portable legacy OS Session lock → packaged SESSION_BUSY JSON + native exit 8
one-file + portable GUI smoke
standalone + portable tgctl smoke
repository worktree clean gate
candidate SHA-256 generation
artifact upload
```

The earlier fully green runtime head `9496416e081178d87e2fed3ccda0c248c3c18c40` / run `33302689526` predates the required regex implementation. Its 125-pass result and hashes remain traceability only; the final candidate must come from the current PR head after regex was added.

## 2. GUI / daemon regression

不得因 v0.3.1 修改破坏：focused workspace、Telegram Chat Folder、avatar lazy load、Export Category、category/group/timestamp JSON、same-second no overwrite、migration collapse/date-range history、since-last checkpoint、current-unread snapshot、single daemon coexistence。

正常 GUI close 的新长期 gate：

```text
last window closes
→ Qt/qasync stays alive
→ cancel + await GUI-local init/monitor tasks
→ cancel + await heartbeat
→ detach GUI lease
→ async app finishes
→ event loop ends normally
```

禁止在 `run_until_complete` 未完成时直接 `loop.stop()`。正常关闭不得请求 shared daemon shutdown；真正 shutdown exception 仍应记录。

自动测试至少验证退出协调、local task cancellation、heartbeat cancellation、client.detach 和 no `system.shutdown`。真实 Alt+F4、多 GUI 与日志计数仍是人工 E2E。

## 3. Current-unread export-start snapshot regression

这是 Issue #22 的长期 correctness gate，后续 Agent 不得删除或弱化。

正确语义：

```text
lower = read_inbox_max_id when this group starts execution
upper = latest_message_id when this group starts execution
export lower < id <= upper
```

必须测试：

- catalogue 中 stale snapshot 与 export-start 新状态不同 → 使用 export-start snapshot；
- upper frozen 之后到达的新消息 → 本次不导出；
- multi-group batch → 每个群轮到执行时分别 snapshot；
- export 与 optional read-ack 使用同一 frozen lower/upper；
- export failure → 不 read-ack；
- JSON success + read-ack failure → JSON 保留；
- migrated Basic Group 不参与 current-unread；
- catalogue/workspace GroupInfo 不因 execution snapshot 被原地修改。

## 4. Cursor / page

覆盖 default 100/max 500、HMAC sign/verify、method/query mismatch、tamper、不含 access_hash/file_reference/credential、dialogs stable pagination、history 2+ pages no overlap/gap、migration current→legacy、search continuation、`INVALID_CURSOR`、`CURSOR_STALE`。

v0.3.1：

- url-domain cursor query 绑定规范化后的 hostname；等价大小写/完整 URL 可续页，不同域名必须 `INVALID_CURSOR`；
- regex 原文 + case-sensitive 状态进入 query fingerprint；换 regex 或大小写语义后旧 cursor 不得复用。

## 5. Dialogs/account

覆盖 group/supergroup/channel/private/bot/Saved Messages/archive/forum/unread/pinned/muted/folder/migration safe metadata。Saved Messages 只能一个 `reference=me` row。`account get` 不输出 phone/credentials。

## 6. Chat details / participant roles

测试 owner/admin/member、admin title、bot/deleted account、权限不可枚举、current role semantics、unknown role 不强制 member、Basic Group 与 Channel/Supergroup API 路径。禁止显示名推断 owner/admin。

v0.3.1 owner diagnostics 至少区分：

```text
available
insufficient_permissions
participants_unavailable
creator_not_in_returned_page
telegram_not_returned
not_found (only where returned data supports that conclusion)
```

## 7. Structured sender / Rich MessageInfoV3

至少：user sender、channel/chat send-as、broadcast channel post、anonymous admin、deleted user with Telegram peer、reply/reply_top、forum_topic_id、forward origin、entities、views/forwards、reactions、poll、service action、media metadata、caption/text、MESSAGE_NOT_FOUND。

v0.3.1 不得根据正文、链接或昵称猜 sender。实际 sender 与 `forward_origin` 必须分开。

无法恢复 sender 时保持 `sender_type=unknown`，并用脱敏 fixture 覆盖 `unknown_reason`：

```text
service_message_without_sender
forwarded_message_without_actual_sender
post_author_without_sender_peer
unsupported_or_unavailable_sender_peer
telegram_sender_not_provided
```

## 8. History / migration

`messages history`：newest→older、since inclusive、until exclusive、bounded memory、max500、不推进 read marker、不自动下载媒体。

Migration history 唯一键 `(source_chat_id,message_id)`，不能只按 message id 去重。legacy source 的 logical `chat_id` 仍是 current Supergroup，`source_chat_id` 指 legacy Basic Group。

## 9. Advanced search / regex / url-domain

测试 single/global、contains、regex、sender-id、current sender-role、since/until、message type、topic、has-link、url-domain、cursor。

Regex 长期 gate：

```text
default case-insensitive              match
--case-sensitive                      exact case
invalid / empty regex                 INVALID_ARGUMENT before Telegram work
pattern length > 512                  INVALID_ARGUMENT
same regex + same semantics cursor    continue without overlap
changed regex with old cursor         INVALID_CURSOR
regex + domain + sender-role          compose as AND filters
legacy schema + regex                 INVALID_ARGUMENT
```

Regex 只做本地 bounded filtering，不能把 scan cap 取消成全账号无限扫描。

Domain cases：

```text
mypikpak.com                         canonical/match
www.mypikpak.com                     canonical
MYPiKPAK.CoM                         canonical
https://mypikpak.com/path?q=1        canonical
cdn.mypikpak.com                     match as subdomain
surrounding whitespace               canonical
mypikpak.com.evil.com                reject
notmypikpak.com                      reject
malformed host                       INVALID_ARGUMENT
no match                              empty valid page
```

域名规范化必须离线，不依赖 PSL/network。CI 必须直接运行最终 standalone 和 portable `tgctl.exe --smoke-test-search-filters`，同时覆盖 domain 与 regex 的 frozen runtime 路径，不能只测源码。

## 10. Forum

Telethon 1.44：`functions.messages.GetForumTopicsRequest(peer=...)`。测试 bounded topics pagination/cursor、TopicInfo、topic history rich schema、非 forum → `NOT_A_FORUM`。

## 11. Media metadata / explicit download

普通 history/search/get metadata-only，不能产生下载文件。

`media download` 测试：plan 第一次 `DOWNLOAD_CONFIRMATION_REQUIRED` 且不创建 output dir/不调用 download_media；token 绑定 chat/ids/output/allow-large+digest；token mismatch/过期拒绝；normal 20/500MiB、large hard 200/5GiB；filename/path safety；`.part`→atomic final；error/cancel 无半写最终文件；confirmed transport outcome 不自动 retry。

真实媒体下载不是默认 E2E，只有用户明确选择才产生本地文件。

## 12. JSON / JSONL / exit codes

JSON stdout 是单一 envelope，不混日志。JSONL = `meta → item* → end`，错误单行。

```text
2 INVALID_ARGUMENT
3 NOT_AUTHORIZED/AUTH_GUI_ONLY
4 CHAT_NOT_FOUND/MESSAGE_NOT_FOUND
5 AMBIGUOUS_CHAT
6 FLOOD_WAIT
7 WRITE_FAILED
8 SESSION_BUSY
9 EXPORT_IN_PROGRESS
10 WRITE_OUTCOME_UNKNOWN
11 DAEMON_UNAVAILABLE
12 INVALID_CURSOR/CURSOR_STALE
13 ACCESS_DENIED/MEMBERS_UNAVAILABLE
14 NOT_A_FORUM
15 DOWNLOAD_CONFIRMATION_REQUIRED
16 DOWNLOAD_LIMIT_EXCEEDED
130 Ctrl+C
```

Windows package test 必须检查 native Process ExitCode，不只看 PowerShell `$?`。

## 13. Security / privacy regression

普通日志不得包含：api_id/api_hash、phone/OTP/2FA、Session/credentials、IPC secret、access_hash/file_reference、message body/caption/URL text/media filename、send/forward dry-run body。

用户明确调用 history/search/get 时正文可在 stdout JSON/JSONL，但不能进入 app.log。代理只允许记录脱敏后的类型/endpoint；带认证信息的 proxy URL 不得记录用户名、密码、query。

真实日志审计只报告匹配计数，禁止把日志正文复制到 Issue/PR/聊天。

正常 GUI 关闭的新日志段还必须满足：

```text
Fatal application error = 0
Traceback = 0
un-awaited coroutine = 0
Task was destroyed = 0
SESSION_BUSY caused by same-generation GUI/tgctl = 0
```

## 14. FloodWait

Mock → `FLOOD_WAIT + retry_after_seconds`，不 retry storm。真人测试不故意制造 FloodWait。

## 15. v0.3.1 真人只读 E2E

默认不执行 send/forward/mark-read/media confirm download。用户本机验证：

1. `account get`；
2. dialogs 覆盖 group/supergroup/channel/private/bot/Saved/archive；
3. `chats get`、members admin/owner；
4. 最近 500 history；
5. search contains/regex/url-domain/sender/sender-role；
6. two-page cursor no overlap，跨查询 → `INVALID_CURSOR`；
7. since/until 时区边界；
8. Saved Messages `me`；
9. replies/entities/forward_origin/reactions/service_action/media metadata；
10. Forum topics/history，非 forum → `NOT_A_FORUM`；
11. `MESSAGE_NOT_FOUND`、`AMBIGUOUS_CHAT`；
12. media plan → `DOWNLOAD_CONFIRMATION_REQUIRED`，不确认下载；
13. send/forward only `--dry-run`；
14. GUI + tgctl coexist；
15. two GUI + tgctl coexist；
16. 0 条 current-unread export 生成合法 JSON且 mark-read disabled；
17. normal reads do not download media；
18. idle GUI close；
19. refresh groups then close；
20. zero-unread export then close；
21. two GUIs sequential close；
22. each close 后 `tgctl status` still works；
23. normal-close log counts all zero as above；
24. same bounded sender sample before/after unknown classification statistics；
25. privacy log scan reports counts only。

真实账号测试默认只读；任何 real send/forward/read-ack/media download/group mutation/FloodWait stress/Session reset 都需要用户单独确认。

## 16. Candidate / Release gate

记录 branch/runtime head、final PR head、pytest 数量、Windows run、artifact、one-file/portable/tgctl SHA-256、CI 无法验证的真实 Telegram 项。

v0.3.1 Candidate 完成后：

- PR 在真人验收前保持 Draft；
- 不修改 `v0.3.0` tag/Release；
- 不创建 `v0.3.1` Release；
- 等待真人 E2E PASS 与用户明确 merge/release 授权。
