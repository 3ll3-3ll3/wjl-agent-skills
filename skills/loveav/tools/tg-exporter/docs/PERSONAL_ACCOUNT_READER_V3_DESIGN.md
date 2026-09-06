# TG Exporter v0.3.0 — Personal Account Reader 设计

> 第三代产品设计。本文只定义架构、CLI/RPC 契约、安全边界、分页语义和验收标准；当前分支不实现运行代码、不发布 Release。

## 0. 版本映射与基线

本项目后续统一使用仓库 SemVer，避免“第几代”和历史提示词版本号冲突：

| 产品代际 | 仓库版本 | 含义 |
| --- | --- | --- |
| 第一代 | `v0.1.x` | GUI exporter + direct `tgctl`；当前正式线已到 v0.1.10 hotfix |
| 第二代 | `v0.2.0` | single daemon + Named Pipe IPC；现有分支 `codex/single-daemon-v0.2.0` |
| 第三代 | `v0.3.0` | v0.2.0 daemon 架构 + Personal Account Reader |

用户新提示词里写的“从 v0.1.9 扩展到 v0.2.0”，在本仓库中解释为：

```text
现有 v0.2.0 daemon 基线
        +
个人 Telegram 账号综合只读访问能力
        =
新 v0.3.0
```

v0.3.0 必须从现有 v0.2.0 架构继续演进，不另起一套 direct-Session reader，也不得覆盖/改名 v0.2.0。

此外，v0.1.10 已修复 packaged `tgctl` 在 legacy Windows console 编码下输出中文 JSON 时可能 `UnicodeEncodeError`、导致 `SESSION_BUSY` native exit code 从 8 变 1 的问题。v0.3.0 实施时必须 forward-port 该 UTF-8 console fix 与 packaged regression gate。

---

## 1. 产品目标

v0.3.0 不是 Telegram Desktop 替代品，也不是自动化机器人。

唯一目标：

> 让本地 Codex 通过 `tgctl` 可靠、分页、安全地读取当前个人 Telegram 账号本身有权访问的信息，并能在不依赖 GUI 导出文件的情况下回答账号、会话、成员、管理员、消息、Forum Topic、Saved Messages 等问题。

目标体验：

```text
用户自然语言
   ↓
Codex
   ↓
tgctl.exe
   ↓
本机 Named Pipe
   ↓
TG daemon（唯一 Telegram Session / Telethon owner）
   ↓
Telegram
```

GUI 仍是人类可视化导出工具；`tgctl` 是 Codex 的机器接口。两者必须共享同一个 daemon-side Core，避免“GUI 能读、Codex 读不到”或两套语义漂移。

---

## 2. 明确非目标

v0.3.0 不做：

- Telegram Secret Chat；
- 已删除内容恢复；
- 绕过账号权限读取不可访问内容；
- Bot API；
- 24/7 Telegram update listener；
- 自动转发规则；
- AI 自动分类器；
- 联系人/群管理；
- 删除消息、退群、修改 Chat Folder；
- 自动标记已读；
- 自动下载聊天媒体；
- 为“完整”而把 access hash / file reference / Session credential 暴露给 stdout。

---

## 3. v0.2.0 架构必须保留

v0.3.0 不回退到 v0.1.x 的“GUI/tgctl 各自打开 SQLiteSession”。

仍然是：

```text
TG daemon
  ├─ 唯一持有 TelegramService / Telethon / telegram.session
  ├─ GUI IPC client
  ├─ tgctl IPC client
  └─ future MCP client（v0.3.0 仍不实现 MCP）
```

关键不变量：

1. 只有 daemon 可以创建 `TelegramClient`。
2. GUI/tgctl 不得在 daemon 不可用时 fallback direct Session。
3. `SessionLease` 继续由 daemon 获取，用于阻止旧 v0.1.x 二进制同时打开 Session。
4. IPC 继续使用 Windows Named Pipe / AF_PIPE + UTF-8 JSON bytes，禁止 pickle transport。
5. 登录仍只允许 GUI；Codex/tgctl 不接触 phone / OTP / 2FA。
6. v0.2.0 的托盘、GUI lease、后台 export job、idle shutdown、write unknown outcome 规则继续生效。

### 3.1 SESSION_BUSY 的 v0.3.0 语义

旧提示词中的以下测试：

```text
GUI 占 Session → tgctl SESSION_BUSY
tgctl 占 Session → GUI SESSION_BUSY
```

与 v0.2.0 single-daemon 目标冲突，因此 **v0.3.0 不保留这种旧体验**。

v0.3.0 正确验收应是：

```text
v0.3 GUI 正常打开
+
v0.3 tgctl/Codex 同时读取
→ 都经同一个 daemon
→ 不产生 SESSION_BUSY
```

`SESSION_BUSY` 只用于兼容边界：

```text
旧 v0.1.x direct binary / 其它旧进程已经 OS-lock telegram.session
→ v0.3 daemon 无法获得 SessionLease
→ tgctl 返回 SESSION_BUSY
→ native exit code 必须严格为 8
```

不得为了满足旧提示词重新制造 GUI↔tgctl Session 竞争。

---

## 4. 默认只读安全模型

### 4.1 命令分类

v0.3.0 daemon 将 RPC 按副作用分类，而不是仅靠 CLI 名称判断：

```text
LOCAL
  system.status / job status / heartbeat / cursor validation

TELEGRAM_READ
  account/dialogs/chats/members/messages/topics/media metadata

LOCAL_DISK_WRITE
  explicit media download / existing GUI JSON export

TELEGRAM_WRITE
  existing send / forward / GUI optional read-ack

GUI_AUTH
  configure API / phone / OTP / 2FA / reset local Session
```

新增 Personal Reader 命令全部属于 `TELEGRAM_READ`，只有 `media download` 属于显式 `LOCAL_DISK_WRITE`。

### 4.2 现有写能力不扩权

- 保留现有 `send` / `forward` 兼容命令，不删除、不改成默认执行；
- v0.3 reader 命令不得内部调用 send/forward/mark-read；
- GUI 的 Option B read-ack 仍只按已有 GUI 明确设置执行；
- 不新增 Codex 隐式 mark-read；
- export 活跃时真实 send/forward 继续按 v0.2.0 规则返回 `EXPORT_IN_PROGRESS`；
- transport outcome unknown 继续不得自动 retry。

### 4.3 敏感数据边界

任何新增 RPC / JSON / JSONL / cursor / log 均不得输出或记录：

- `api_id` / `api_hash`；
- 手机号；
- OTP / 2FA；
- Session 文件内容；
- credentials 原文；
- Telegram `access_hash`；
- Telegram `file_reference` bytes；
- IPC auth secret。

消息正文可以出现在用户明确请求的 stdout JSON/JSONL 中，但普通运行日志默认不得记录正文、caption、URL 文本或媒体文件名。

---

## 5. 新数据模型：不要把私聊硬塞进 GUI GroupInfo

GUI `GroupInfo` 继续只服务现有导出器语义，避免机械重写 GUI。

v0.3.0 新增 reader-only 模型：

```text
AccountProfile
DialogInfo
ChatDetails
ParticipantInfo
SenderInfo
MessageInfoV3
ForumTopicInfo
MediaMetadata
Page[T]
```

GUI 的 `chats.catalogue` 保持现有 group/channel catalogue；新增全账号接口使用 `dialogs.*`，两者不能混成一个破坏 GUI 假设的大模型。

---

## 6. 通用分页契约

### 6.1 默认与上限

除特别说明：

```text
default limit = 100
max limit = 500
```

任何全历史 reader 命令都不允许 `limit=None` 或静默无限读取。

### 6.2 Page envelope

`--json` 成功页统一：

```json
{
  "ok": true,
  "data": {
    "items": [],
    "next_cursor": null,
    "has_more": false,
    "count": 0,
    "timing": {
      "network_ms": 0,
      "local_filter_ms": 0,
      "serialization_ms": 0
    }
  }
}
```

### 6.3 Cursor 设计

新增 `cursor_codec.py`：

- cursor 是 opaque base64url token；
- payload 只包含安全 offset / peer id / segment / query fingerprint；
- **绝不包含 access_hash**；
- 使用现有持久化 IPC identity secret 做 HMAC-SHA256 integrity；
- cursor 绑定 method + query fingerprint，不允许拿 A 查询 cursor 去跑 B 查询；
- cursor versioned；
- tamper / wrong query → `INVALID_CURSOR`；
- 若 Telegram entity cache 无法恢复服务器 offset peer → `CURSOR_STALE`，不得猜。

因为 v0.2.0 IPC identity 是持久化本地 identity，cursor 可以跨 tgctl 进程和 daemon idle restart 继续使用。

---

## 7. 账号信息

新增：

```text
tgctl account get --json
```

RPC：

```text
account.get
```

只返回：

```json
{
  "user_id": 123,
  "display_name": "...",
  "username": "...",
  "premium": true,
  "bot": false,
  "language_code": "zh-hans"
}
```

`language_code` Telegram 未提供时返回 `null`；不得用系统语言伪造。

---

## 8. 完整会话目录 dialogs.list

新增：

```text
tgctl dialogs list \
  [--type group|supergroup|channel|private|bot|saved] \
  [--folder <name|id>] \
  [--archived yes|no|all] \
  [--search <text>] \
  [--unread yes|no|all] \
  [--pinned yes|no|all] \
  [--cursor <token>] \
  [--limit 100] \
  [--json|--jsonl]
```

必须覆盖：

- Basic Group；
- Supergroup；
- broadcast Channel；
- 私聊；
- Bot 对话；
- Saved Messages；
- archived；
- Telegram Chat Folder；
- forum 标记；
- unread_count；
- pinned；
- muted；
- migrated_to / migrated_from 安全 peer id。

### 8.1 稳定目录分页

会话数量通常远小于消息历史。为避免 Telegram activity order 在分页过程中因新消息不断变化，v0.3.0 的完整目录默认采用 **canonical stable order**：

```text
(dialog_type_rank, marked_chat_id)
```

每次读取当前完整 dialog catalogue，应用 filter 后按 canonical key 排序，再从 cursor 的 last key 继续。

这样：

- 不需要在 cursor 暴露 access_hash；
- 新消息不会导致旧会话因“活跃度重排”而重复/漏页；
- `last_message_date` 仍作为字段返回，但不是默认分页 key。

未来如要 Telegram UI activity order，可另加显式 `--order activity`，但不得冒充同等级稳定 snapshot。

### 8.2 Saved Messages

若 Telegram dialog list 未自然返回 self peer，reader 仍必须提供一个唯一 synthetic self row：

```text
type = saved
reference = me
```

不得重复出现 self 私聊和 Saved Messages 两行。

---

## 9. 会话详情 chats get

新增：

```text
tgctl chats get --chat <ref> --json
```

`<ref>` 支持：

- marked numeric chat id；
- exact `@username`；
- exact title/display name；
- `me`；
- 同名必须 `AMBIGUOUS_CHAT` + safe candidates，绝不 first-match。

返回至少：

```text
chat_id
title
username
type
description/about
member_count
owner (if Telegram allows reliable resolution)
current_account_rights
forum
migrated_from_chat_id
migrated_to_chat_id
linked_chat
available_min_id
pinned_message_id
```

不得返回 `access_hash`。

### 9.1 Owner 信息不猜

如果 Telegram 当前账号权限/接口无法可靠取得 owner：

```json
{
  "owner": null,
  "owner_visibility": "unavailable"
}
```

不能从显示名、置顶消息、常发言者推断 owner。

---

## 10. 成员、群主和管理员

新增：

```text
tgctl chats members --chat <ref> \
  --role owner|admin|member \
  --cursor <token> \
  --limit <n> \
  --json|--jsonl
```

`--role` 可省略表示所有当前可枚举 participant。

每条至少：

```json
{
  "user_id": 1,
  "display_name": "...",
  "username": "...",
  "role": "owner",
  "is_creator": true,
  "is_admin": true,
  "admin_title": "...",
  "bot": false,
  "deleted_account": false
}
```

### 10.1 角色语义

`owner/admin/member` 默认表示 **查询时当前角色**，不是历史某条消息发送当时的角色。

Telegram 不提供完整历史管理员任期，因此：

- 当前是 admin → 可判定 `is_admin=true`；
- 当前已不是 admin → 不得声称其过去发消息时一定不是 admin；
- 匿名管理员消息如果 Telegram message metadata 能证明 anonymous send-as，则按消息事实标识，不映射到个人。

### 10.2 权限不足

某些频道/群成员列表对当前账号不可见时：

- `member_count` 可在可得时返回；
- participant 枚举返回 `MEMBERS_UNAVAILABLE` / `ACCESS_DENIED`；
- 不使用搜索结果、消息作者集合冒充“完整成员表”。

### 10.3 Role cache

为了支持“最近 500 条中哪些由 owner/admin 发送”，daemon 可维护短 TTL 内存 role cache：

```text
chat_id -> owner/admin safe IDs + title
```

不持久化成员正文，不记录手机号。

---

## 11. 完整消息历史分页

新增：

```text
tgctl messages history --chat <ref> \
  [--cursor <token>] \
  [--limit 100] \
  [--since <iso>] \
  [--until <iso>] \
  [--json|--jsonl]
```

语义：

- 默认从最新向旧读取；
- default 100 / max 500；
- `since` inclusive；
- `until` exclusive；
- 不推进 Telegram read marker；
- 不下载 media；
- 单页 bounded memory；
- FloodWait 结构化返回，不 retry storm。

### 11.1 History cursor

单会话 history 使用 message id 作为主要稳定边界：

```text
before_message_id = 当前页最老 message id
```

下一页只读取更老 ID。新消息到达不会把旧页重新插回来，因此连续向历史翻页无重复。

### 11.2 Basic Group → Supergroup migration

为覆盖 GUI 已有 migration history 能力，v0.3.0 history 默认把已确认迁移关系视为一个 logical chat：

```text
current supergroup segment
→ exhausted
→ legacy basic-group segment
```

cursor 内包含：

```text
logical_chat_id
source_segment=current|legacy
source_chat_id
before_message_id
```

因为 old/new peer 的 message id 可能重叠，消息结果新增：

```text
chat_id         = logical current chat id
source_chat_id  = 实际消息来源 peer id
message_id
```

唯一定位键为 `(source_chat_id, message_id)`，不得只用 message_id 去重。

---

## 12. messages search 扩展

保留现有 `messages search` 兼容参数并扩展：

```text
tgctl messages search \
  [--chat <ref>] \
  [--contains <text>] \
  [--sender-id <id>] \
  [--sender-role owner|admin|member] \
  [--since <iso>] \
  [--until <iso>] \
  [--message-type <type>] \
  [--topic <id>] \
  [--has-link yes|no] \
  [--url-domain <domain>] \
  [--cursor <token>] \
  [--limit <n>] \
  [--case-sensitive] \
  [--json|--jsonl]
```

没有 `--chat` 时为全局搜索。

### 12.1 搜索执行策略

优先服务器缩小候选，再本地精确过滤：

```text
Telegram server search
→ bounded candidate page
→ sender/role/topic/link/domain/type local filters
→ 返回匹配项 + next_cursor
```

必须返回：

```text
scanned_count
matched_count
next_cursor
has_more
network_ms
local_filter_ms
```

不能为了凑满 `limit` 无限扫描。每次 RPC 另有 `candidate_scan_cap`（初始建议 5000），达到 cap 但仍可能有后续候选时返回 `has_more=true` + cursor，让 Codex 显式续页。

### 12.2 sender-role

单 chat：先构建当前 owner/admin role snapshot，再精确过滤。

全局：role 是 chat-relative，daemon 对每个命中 chat 按需解析/缓存 role；若某 chat role data 不可见，该消息的 role 为 `unknown`，不得把 unknown 当 member。

### 12.3 URL 域名匹配

`--url-domain mypikpak.com` 不做字符串 contains。

规则：

1. 从 Telegram URL/TextUrl entities 与安全文本 URL parser 提取 URL；
2. `urllib.parse` 解析 hostname；
3. lowercase + IDNA normalization；
4. 匹配 exact host `mypikpak.com` 或其真实 subdomain `*.mypikpak.com`；
5. `mypikpak.com.evil.example` 不匹配；
6. 不主动访问 URL、不 follow redirect。

这样 Codex 可以可靠回答“谁发过真实 mypikpak.com 链接”。

---

## 13. 结构化 SenderInfo

不再只返回一个显示名字符串。

统一 sender：

```json
{
  "sender_id": 123,
  "sender_type": "user",
  "display_name": "...",
  "username": "...",
  "posted_as_chat_id": null,
  "is_creator": false,
  "is_admin": true,
  "admin_title": "Moderator",
  "anonymous_admin": false,
  "via_bot_id": null,
  "role_basis": "current_snapshot"
}
```

`sender_type`：

```text
user
chat
channel
anonymous_admin
unknown
```

### 13.1 匿名管理员 / send-as

若消息以群/频道身份发布：

- `posted_as_chat_id=<peer id>`；
- 能可靠判断 anonymous admin 时 `sender_type=anonymous_admin`、`anonymous_admin=true`；
- **不得**根据 `post_author` 字符串、显示名或管理员列表猜出背后的具体 user id；
- 如果只能确认“以某 channel/chat 身份发言”，则返回 `sender_type=chat|channel`，不要强行 anonymous_admin。

---

## 14. MessageInfoV3 统一结构

`messages history/search/get` 与 topic history 统一返回同一个 schema：

```text
chat_id
source_chat_id
message_id
date
edit_date
sender
text
caption
entities
reply_to_message_id
reply_to_top_id
forum_topic_id
forward_origin
grouped_id
views
forwards
reactions
poll
service_action
pinned
media
availability
```

### 14.1 text / caption

Telegram 的 message text/caption 底层常使用同一 `message` 字段。v0.3 schema 明确区分：

- 无 media → `text`；
- 有 media → 同一字符串规范化到 `caption`；
- 兼容字段如有需要可保留 `content_text`，但不能让消费者猜。

### 14.2 entities

仅输出安全、结构化字段：

```text
type
offset
length
url
user_id
language
custom_emoji_id
```

不输出 raw TL repr。

### 14.3 forward_origin

规范化：

```text
origin_type=user|chat|channel|hidden_user|unknown
origin_id
date
post_author
source_message_id
saved_from_chat_id
```

只返回 Telegram 提供且安全的字段，不尝试反查隐藏来源。

### 14.4 reactions

返回 reaction counts 与 Telegram 已提供的安全 recent reactor ids；不额外枚举未返回的人员。

### 14.5 poll

返回 poll id、question、options、closed/quiz/public-voters/multiple-choice 与可得 vote counts；不主动投票。

### 14.6 service_action

把已知 service message 转成白名单结构化 action type + safe IDs，不输出 raw object repr。

### 14.7 deleted / available 语义

Telegram 不会把已经彻底删除的历史消息作为普通 history row 返回，因此 v0.3 **不能可靠声称 `deleted=true`**。

返回消息：

```json
{"availability":"available"}
```

按 ID 查询缺失：继续 `MESSAGE_NOT_FOUND`，details 可写：

```text
not_found_or_unavailable
```

不得把“查不到”武断解释为“已删除”。

---

## 15. Forum Topic

新增：

```text
tgctl topics list --chat <ref> [--cursor ...] [--limit ...] --json|--jsonl

tgctl topics history --chat <ref> --topic <id> \
  [--cursor ...] [--limit ...] [--since ...] [--until ...] \
  --json|--jsonl
```

TopicInfo 至少：

```text
topic_id
title
icon_color
icon_custom_emoji_id
top_message_id
unread_count
pinned
closed
hidden
```

非 forum chat 调 topics 命令返回明确 `NOT_A_FORUM`。

Topic history 使用与 messages history 相同 MessageInfoV3 schema，并保证 `forum_topic_id`。

---

## 16. 媒体：默认 metadata-only

消息 media 默认只返回元数据，不下载：

```text
media_type
filename
mime_type
size
width
height
duration
document_id
photo_id
spoiler
```

永远不返回 `file_reference` bytes。

### 16.1 显式下载命令

新增：

```text
tgctl media download \
  --chat <ref> \
  --ids <message ids...> \
  --output <directory> \
  [--confirm <token>] \
  [--allow-large-download] \
  --json
```

即使是单文件，第一次调用 **不下载**，而是 plan：

```json
{
  "ok": false,
  "error": {
    "code": "DOWNLOAD_CONFIRMATION_REQUIRED",
    "details": {
      "file_count": 3,
      "estimated_bytes": 123456,
      "unknown_size_count": 0,
      "confirmation_token": "..."
    }
  }
}
```

第二次带同一 plan 的 `--confirm <token>` 才允许 daemon 下载到用户指定目录。

建议阈值：

```text
普通确认上限：20 files 或 500 MiB
显式 --allow-large-download：最多 200 files / 5 GiB
hard cap 超过仍拒绝
```

任一 size unknown 且批量较大时必须在 plan 明示，不能把未知当 0。

`media download` 是本地磁盘副作用，但不产生 Telegram write/read-ack。

---

## 17. JSONL

大量 reader 命令支持 `--jsonl`，但 **不修改 Named Pipe 为任意长流协议**。

原因：单页最大 500，daemon 仍返回 bounded page；tgctl 再逐行输出。

JSONL 契约：

```json
{"type":"meta","ok":true,"data":{"schema":"tgctl.reader.v1"}}
{"type":"item","data":{}}
{"type":"item","data":{}}
{"type":"end","data":{"count":2,"next_cursor":"...","has_more":true,"timing":{}}}
```

失败时输出单行：

```json
{"type":"error","ok":false,"error":{"code":"...","message":"...","details":{}}}
```

stdout 不混 logging 前缀。

---

## 18. 性能与取消

### 18.1 性能目标

对已经从 Telegram 取到内存的 500 条纯文本候选：

```text
sender/link/domain/type 本地过滤目标 < 1s
```

网络时间单独计，不把 Telegram latency 算进本地过滤 SLA。

测试输出/内部 metrics 区分：

```text
network_ms
local_filter_ms
serialization_ms
```

### 18.2 Ctrl+C

v0.3 daemon 唯一持有 Session，因此 `tgctl` Ctrl+C 不会直接杀 TelegramClient/SQLiteSession。

CLI 规则：

- Ctrl+C → 关闭当前 pipe client，exit 130；
- 不删除 lock/session；
- bounded read RPC 即使 daemon 已接收，也只能完成当前有限页，不会无限读历史；
- media download 采用 daemon-side job/cancellable task，Ctrl+C 必须请求 cancel 或安全 detach，不允许留下半写最终文件；下载使用 `.part` 临时文件，成功后 rename。

---

## 19. OperationCoordinator 集成

延续用户已选择的 v0.2.0 3B/4B：

### export 活跃时

```text
account/dialogs/chats/members/messages/topics/media metadata read
→ 等待 export 完成

真实 send/forward
→ EXPORT_IN_PROGRESS，立即拒绝

local status/job/heartbeat
→ 立即可用
```

媒体真实下载属于长 Telegram read + local disk write，默认也等待 export 完成，不与 GUI export 抢 Telegram。

### 非 export 时

Telegram reader RPC 仍通过 daemon operation queue 串行执行第一版，以稳定优先；v0.3 不因为 reader 功能多就引入 Telethon 多 client 并发。

---

## 20. 新错误码

保留 v0.1.x/v0.2.0 既有 code/exit mapping，不改旧数字。

新增建议：

```text
INVALID_CURSOR                exit 12
CURSOR_STALE                  exit 12
ACCESS_DENIED                 exit 13
MEMBERS_UNAVAILABLE           exit 13
NOT_A_FORUM                   exit 14
DOWNLOAD_CONFIRMATION_REQUIRED exit 15
DOWNLOAD_LIMIT_EXCEEDED       exit 16
```

`SESSION_BUSY` 必须继续 exit 8。

所有错误 JSON 继续：

```json
{
  "ok": false,
  "error": {
    "code": "...",
    "message": "...",
    "details": {}
  }
}
```

---

## 21. CLI 兼容策略

现有命令必须继续工作：

```text
tgctl status
tgctl chats list
tgctl messages search
tgctl messages get
tgctl forward
tgctl send
```

兼容原则：

- 不删除旧参数；
- `messages search` 扩展，不换名；
- 新 `dialogs list` 不替换 GUI-oriented `chats list`；
- 旧 `messages get` 输出若无法原地升级而不破坏消费者，则 `--json` 可在 v0.3 统一为 MessageInfoV3，但必须在 release notes 明确 schema version；必要时提供 `--legacy-schema` 一次过渡；
- send/forward safety 不因 reader 扩展而放松。

---

## 22. 真实账号只读 E2E（v0.3 修正版）

真实账号测试默认只读，不执行 send/forward/mark-read/media download。

必须验证：

1. `dialogs list` 能覆盖 group/supergroup/channel/private/bot/Saved Messages/archive。
2. Telegram Chat Folder 对这些 dialog type 的 membership 正确。
3. 指定真实群最近 500 条 history 可读。
4. owner/admin 清单可可靠取得；权限不足时结构化说明，不猜。
5. 最近 500 条中能回答：
   - 谁发了包含 `pikpak` 的消息；
   - 谁发了真实 `mypikpak.com` 链接；
   - 当前 owner/admin snapshot 是否匹配发送者。
6. sender 为结构化对象，不再只是显示名。
7. anonymous admin / send-as 不错误归属个人。
8. history 连续翻页按 `(source_chat_id,message_id)` 无重复、无遗漏。
9. since inclusive / until exclusive 正确。
10. Saved Messages 可作为 history/search 来源。
11. `MESSAGE_NOT_FOUND` 正确。
12. 同名 dialog → `AMBIGUOUS_CHAT` + candidate IDs。
13. v0.3 GUI 与 v0.3 tgctl **可以同时工作，不应 SESSION_BUSY**。
14. 用 legacy lock holder 占 Session 时，daemon/tgctl → `SESSION_BUSY` 且 packaged native exit 8。
15. legacy tgctl/direct process 占 Session 时，v0.3 GUI 得到安全 busy 诊断，不出现 `database is locked`。
16. FloodWait mock/自然出现时 → `FLOOD_WAIT` + `retry_after_seconds`，不故意触发。
17. logs 无 message body / credentials / access_hash / file_reference。
18. stdout JSON/JSONL 的消息正文只来自用户明确 read 命令。
19. forum 账号中有真实 forum 时验证 topics list/history；没有则标 condition unavailable。
20. media metadata-only 不产生下载文件。

注意：旧提示词“GUI 占 Session → tgctl SESSION_BUSY”被第 13/14 条取代，因为 v0.3 继承 v0.2 single-daemon。

---

## 23. 自动化测试矩阵

至少新增：

### 数据/协议

- AccountProfile JSON contract；
- DialogInfo types；
- ChatDetails safe-field allowlist；
- ParticipantInfo owner/admin/member；
- SenderInfo anonymous/send-as；
- MessageInfoV3 reply/forward/entities/reaction/poll/service/media；
- access_hash/file_reference never serialized。

### Cursor

- cursor sign/verify；
- method/query mismatch；
- tamper；
- history 2+ pages no duplicate/gap；
- migration segment transition；
- dialog canonical pagination；
- global search continuation。

### Reader semantics

- private/bot/Saved dialog；
- owner/admin current-role filtering；
- unknown role not coerced to member；
- real domain matcher vs lookalike domain；
- forum topic；
- since/until boundaries；
- missing message。

### Streaming/performance

- JSONL meta/item/end；
- 500-row local filter benchmark target；
- bounded max 500；
- Ctrl+C / client disconnect no Session corruption。

### Security/package

- no body in logs；
- no credentials/access hash/file_reference in outputs/cursors；
- packaged UTF-8 stdout；
- legacy OS Session lock → packaged `SESSION_BUSY` + native exit 8；
- GUI + tgctl coexist via daemon；
- PyInstaller one-file/portable smoke。

Mock tests 不能代替真实账号 E2E。

---

## 24. 实施阶段

v0.3 实施分支建议：

```text
codex/personal-account-reader-v0.3.0
```

从 **完成且保留的 v0.2.0 daemon line** 开发，而不是从 v0.1.x main 重新实现。

### Phase A — shared reader models + cursor

- safe models；
- cursor codec；
- JSON/JSONL contract；
- safe serializer；
- v0.1.10 console UTF-8 hotfix forward-port。

### Phase B — account + dialogs + generic resolution

- account.get；
- all dialog types；
- Saved Messages；
- Chat Folder across generic dialogs；
- generic `resolve_dialog`，GUI `resolve_group` 不破坏。

### Phase C — chat details + participants + role cache

- FullChannel/FullChat safe mapper；
- owner/admin/member；
- current-account rights；
- permission-unavailable semantics。

### Phase D — MessageInfoV3 + history

- bounded history；
- stable cursor；
- sender identity；
- reply/forward/entities/reactions/poll/service/media metadata；
- migration stitched cursor。

### Phase E — advanced search + topics

- global/single search；
- sender id/role；
- domain filter；
- topic list/history。

### Phase F — explicit media download

- plan/confirmation token；
- limits；
- `.part` atomic local write；
- cancellation。

### Phase G — package + real read-only E2E

- Windows CI；
- packaged smoke；
- real account read-only matrix；
- SHA-256 for candidate EXEs。

完成 Phase G 后 **停止**：

- 不 merge Release commit；
- 不创建/覆盖 `v0.3.0` GitHub Release；
- 等用户本地验收与明确发布授权。

---

## 25. 文档交付

实施完成时更新：

```text
README.md
AGENTS.md
HANDOFF.md
docs/CODEX_TGCTL.md
docs/ARCHITECTURE.md
docs/DECISIONS.md
SECURITY.md 或 docs/SECURITY.md
docs/TESTING.md
docs/releases/v0.3.0.md
```

交付报告必须包含：

- 分支/head SHA；
- 修改文件；
- 命令/RPC 契约；
- unit/CI 测试数量和结果；
- 真实账号只读 E2E；
- Telegram API 本身不可读取/不可证明的内容；
- candidate EXE 路径/hash；
- 与 v0.2.0 / v0.1.x 兼容性；
- 仍需用户视觉确认的项目。

---

## 26. 完成标准

Codex 只通过 tgctl，能够可靠回答：

```text
我的账号加入了哪些会话？
某群群主和管理员是谁？
某人或当前某角色在指定时间内发过什么？
最近 500 条中谁发过 PikPak / mypikpak.com 链接？
某条消息回复了谁、转发自哪里？
某个 Forum Topic 中有哪些消息？
我的 Saved Messages 中有哪些匹配内容？
```

同时满足：

```text
默认不产生 Telegram 写入
不推进 read marker
不自动下载媒体
不暴露 credential/access_hash/file_reference
分页 bounded、可续跑
GUI 与 tgctl 共用 daemon，不重新制造 SESSION_BUSY
旧 direct Session 冲突仍安全返回 SESSION_BUSY exit 8
```

这才是 v0.3.0 的完成定义。