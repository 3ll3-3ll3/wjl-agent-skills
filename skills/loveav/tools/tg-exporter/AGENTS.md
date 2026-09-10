# AGENTS.md

本文件是后续 Agent / Codex / 自动化开发者进入本仓库后的**第一阅读入口**。除非用户明确改变产品方向，否则以下规则视为长期不变量。

## 1. 接手阅读顺序

1. `AGENTS.md`
2. `HANDOFF.md`
3. `README.md`
4. `docs/KNOWN_ISSUES.md`
5. `docs/PERSONAL_ACCOUNT_READER_V3_DESIGN.md`
6. `docs/ARCHITECTURE.md`
7. `docs/DECISIONS.md`
8. `docs/decisions/README.md` 与相关 ADR
9. `docs/SECURITY_MODEL.md`
10. `SECURITY.md`
11. `docs/TESTING.md`
12. `docs/DEPLOYMENT.md`
13. `docs/RELEASE_PROCESS.md`
14. `docs/CODEX_TGCTL.md`
15. 涉及 GUI JSON 时读 `docs/JSON_COMPATIBILITY.md`

不要只凭 README 或旧 PR 推断当前状态；`HANDOFF.md` + GitHub 当前 main/PR/Release/CI 才是当前事实。

## 2. 当前版本事实

```text
第一代 v0.1.x = GUI exporter + direct-session tgctl（历史兼容）
第二代 v0.2.0 = single daemon + Windows Named Pipe IPC
第三代 v0.3.0 = v0.2 daemon + Personal Account Reader
```

原独立仓库当前正式 Production：

```text
v0.3.2
commit: 79649668b9b45fad2783a0f8c6cc673205a9266a
PR: #26
```

LoveAV 内嵌开发版本：

```text
v0.3.3
位置：skills/loveav/tools/tg-exporter
开发真源：3ll3-3ll3/wjl-agent-skills
```

本目录由独立仓库提交 `4af25ad5e35d671cd6401a534767b1656c43944d` 完整迁入。以后只在 LoveAV 内嵌目录继续开发；不得反向修改、归档或删除原独立仓库。来源细节见 `SOURCE_SNAPSHOT.md`。

PR #26 / `codex/v0.3.2-sender-role-fix` 已合并并发布；当前没有仍待合并的 v0.3.2 candidate。该补丁仅增强 sender-role 身份恢复与筛选，不是 LoveAV 或 PikPak 专用功能，也不引入任何业务分类。

`v0.3.2` tag/Release 已正式发布，**不得移动、覆盖、删除或原地重建**。历史 `v0.3.1` tag/Release 同样不得修改。新的功能或修复必须从最新 main 另开分支，经 PR/CI/必要验收/明确授权后进入后续版本。

旧 PR #21 / #24 是历史 handoff/修复分支；PR #26 是已发布的 v0.3.2 release PR。它们的旧开发状态不得作为当前事实。

## 3. Session / daemon 所有权

必须保持：

```text
TG daemon（唯一 Telegram Session / Telethon owner）
├─ TG Exporter GUI IPC client
├─ tgctl IPC client
└─ future MCP client（当前不实现）
```

- 只有 daemon 正常打开 `%APPDATA%\TelegramMultiChatExporter\telegram.session`。
- GUI/tgctl 不得 fallback direct SQLiteSession，不复制 Session，不创建隐藏第二 Session。
- IPC 使用 authenticated Windows Named Pipe / `AF_PIPE` + UTF-8 JSON bytes；禁止 pickle；不开 TCP/HTTP。
- 同代 GUI 与 tgctl 正常共存，不应互相 `SESSION_BUSY`。
- `SESSION_BUSY` 仅用于 legacy/direct 进程已占用 Session 的兼容边界；packaged native exit code 必须保持 8。
- phone/OTP/2FA/API 登录交互仅 GUI。

## 4. GUI / daemon 生命周期不变量

- GUI 关闭时，daemon-side export job 继续完成；GUI 只 detach 自己的 lease。
- GUI 正常关闭必须先完成 async cleanup，再结束 Qt/qasync event loop；不得用 `loop.stop()` 掩盖未完成任务。
- GUI 初始化/job monitor/heartbeat 等本地任务必须 cancel + await，避免 `Task was destroyed` / un-awaited coroutine。
- GUI 没开时 tgctl/Codex 可按需唤醒 daemon。
- export 活跃时 Telegram reader 等待；真实 send/forward/send-capture/mark-read 立即 `EXPORT_IN_PROGRESS`，绝不排队后偷偷发送。
- daemon 为用户态按需进程，不注册 Windows Service；无 lease/job/request/queued read 后可按既定 idle timeout 退出。

## 5. GUI 导出不变量

- 每群每次导出独立 JSON；历史 JSON 不读取、不合并、不覆盖。
- 输出：`总输出目录 / Export Category / 群组 / YYYY-MM-DD_HH-mm-ss.json`，同秒冲突 `_2/_3/...`。
- Export Category 是本地分类，不是 Telegram Chat Folder。
- 每群独立 date range / current unread / since last successful export。
- 默认聊天导出只保留文字/caption，不下载聊天媒体；头像仅 UI cache。
- Basic Group→Supergroup 只显示当前 logical chat；历史可按 Telegram 显式 migration 关系读取 legacy + current。

### Current unread

每个群在**该群真正开始执行**时单独冻结：

```text
lower = read_inbox_max_id_at_group_start
upper = latest_message_id_at_group_start
export only lower < id <= upper
```

不得使用 catalogue refresh 时旧 snapshot；不得移除 upper bound；snapshot 后新到消息留到下一轮。可选 read-ack 默认 OFF，严格：

```text
JSON atomic success → checkpoint → optional read acknowledgement
```

export 与 read-ack 必须使用同一 frozen upper；migrated current-unread 只看 current Supergroup，不看 legacy Basic Group。

## 6. Reader 边界

默认 Telegram read-only：

```text
account.get
dialogs.list
chats.get
chats.members
messages.history
messages.replies
messages.search
messages.get
topics.list
topics.history
media metadata
```

读取不得 send/forward/delete/leave/change-folder/vote/mark-read/自动下载媒体。

频道评论必须使用 `messages.replies --chat <频道> --message-id <频道帖子>`。它与 Forum 的 `topics.history` 是两套语义：不得要求频道开启 Forum，也不得为了读取评论直接打开或复制第二份 Session。结构化消息可包含公开 URL 按钮的 `text/url/type`，但不得暴露 callback data。

Reader 独立模型，不机械扩大 GUI `GroupInfo`。分页 default 100 / max 500；全局候选 scan 受现有 cap 限制；cursor 必须 opaque/HMAC/query-bound，不含 `access_hash`、`file_reference`、Session/credential。

## 7. Search / identity truthfulness

- `--url-domain` 只做离线 hostname/IDNA parsing；exact/subdomain 匹配；绝不访问 URL/follow redirect。
- v0.3.1 引入的 `--regex` 是本地 bounded filter；默认忽略大小写，`--case-sensitive` 可切换；pattern max 512；非法/空 pattern 在 Telegram 请求前 `INVALID_ARGUMENT`；regex 与 case state 必须进入 cursor fingerprint。
- sender/owner/admin 只能依据 Telegram 提供的 peer/participant/admin 数据。
- 不从正文、链接、昵称、群名、`post_author` 猜具体个人。
- actual sender 与 `forward_origin` 分开。
- 无法确认时保留 `sender_type=unknown` + `unknown_reason`，不要伪造身份。
- role 是查询时 current snapshot，不伪造历史管理员任期。
- v0.3.2 只有在显式 `--sender-role` 搜索时才允许一次 current admin snapshot 与受限、请求级缓存的 sender entity recovery；普通 GUI/manual export、普通 history、普通 search 不因此增加身份网络请求。
- Telegram 明确匿名管理员可认定 admin source，但不得猜具体用户；明确以当前群身份 send-as 时记录 chat identity，可匹配 admin role，但不得反推具体管理员。
- `forward_origin` 中的管理员、仅有 `post_author` 文字、普通成员和完全无身份依据的 unknown 不得误判为 admin sender。
- `MESSAGE_NOT_FOUND` 只表示 not found/unavailable，不能武断声称“已删除”。

## 8. Media 与 Telegram 写安全

普通 reader media metadata-only。

显式 `media download` 为本地磁盘副作用，必须：plan → confirmation token → download；normal 20 files / 500 MiB；explicit large hard cap 200 files / 5 GiB；`.part` 成功后原子 rename；confirmed outcome unknown 不自动 retry。

现有 Telegram write 只有已批准边界：

- `forward`：Telegram true forward；dry-run；默认 20，explicit large hard cap 200；
- `send`：纯文本，`parse_mode=None`；dry-run；
- GUI optional read-ack：仅 current-unread Option B。
- `send.capture`：同 daemon 请求内先订阅、后发送、有界捕获；不是后台 listener；
- `messages.mark_read`：只能使用与会话及冻结 `lower/upper` 绑定的签名 token，且要求精确确认词。

`AMBIGUOUS_CHAT` 不 first-match；FloodWait structured stop；write transport outcome unknown → `WRITE_OUTCOME_UNKNOWN`，绝不自动 replay。

## 9. Secret / 日志

严禁进入 GitHub、Issue、PR、CI log、普通 app.log：api_id/api_hash、phone、OTP、2FA、Session 内容、credentials 原文、IPC auth secret、access_hash、file_reference、真实聊天正文/URL/media filename、真实导出文件/头像二进制。

用户明确 reader 命令时正文可出现在该命令 stdout JSON/JSONL；普通日志仍不得记录正文。

Windows ProxyServer 只接受安全 endpoint metadata；携带 auth/query 的输入应拒绝，不得把用户名、密码、query 写入 safe label/log。

## 10. CI / Candidate / Release

v0.3.x 当前自动化 gate 至少包括：

```text
full pytest
focused v0.3.1 baseline regressions
compileall
git diff --check
GUI + daemon + reader + CLI imports
source search-filter smoke
TGExporter one-file build
TGExporter portable build
tgctl one-file build
standalone + portable packaged domain+regex smoke
standalone + portable SESSION_BUSY JSON/native exit=8
packaged GUI/tgctl smoke
tracked-worktree clean
candidate SHA-256 + Actions artifact
```

Candidate asset naming读取根目录 `VERSION`，不得把新 patch 的 Candidate 继续硬编码成旧版本号。Mock/CI 不能代替真实 Windows `%APPDATA%` / Telegram 账号 E2E。Candidate artifact 不是 Production。

正式 Release 流程：Issue/branch → PR → CI → local human acceptance（或用户对特定未执行真人项明确豁免）→ 用户明确授权 → merge → Release workflow → 核验 tag/target/assets/SHA。禁止直接 push/force-push main；禁止覆盖历史 Release/tag。

## 11. 明确非目标

除非用户重新明确授权并重新评估安全设计，不新增：Secret Chat、已删除内容恢复、绕权读取、Bot API、24/7 listener、超出明确调用的自动转发规则、AI 自主分类、联系人/群/管理员管理、删除消息、退群、修改 Chat Folder、媒体发送/媒体转发、MCP Server、Web/TCP/cloud server。

## 12. 交接纪律

任何用户可见功能、关键 bug、架构、安全策略、Candidate/Release 或真人 E2E 状态变化后更新 `HANDOFF.md`。长期设计决定同步 `docs/DECISIONS.md` / ADR；已知问题同步 `docs/KNOWN_ISSUES.md`。

交接必须明确：正式最新版、开发 head、CI 状态、哪些是自动化、哪些是真人验证、未完成事项和下一步。
