# Codex + tgctl — v0.3.x Personal Account Reader

## 1. 架构

```text
用户自然语言
→ Codex
→ tgctl.exe
→ Windows Named Pipe / UTF-8 JSON
→ TG daemon（唯一 Telegram Session / Telethon owner）
→ Telegram
```

v0.3.x 不使用 Bot API，不复制 Session，不在 tgctl 重新做 phone/OTP/2FA 登录。登录仍只在 TG Exporter GUI。

LoveAV 内嵌 v0.3.3 可在不启动 daemon 时读取版本契约：

```powershell
tgctl version --json
```

返回 `tgctl_version`、`reader_schema` 和 `ipc_protocol`。`tgctl status --json` 在既有运行状态外还返回 daemon 版本、兼容性、同版本状态和能力列表，供 LoveAV 在读取消息前做机器判断。

正常情况下 GUI 和 tgctl 可以同时存在；只有旧 direct-session 进程已经锁住 Session 时才返回 `SESSION_BUSY`，packaged native exit code 必须是 8。

## 2. JSON / JSONL

成功：

```json
{"ok":true,"data":{}}
```

失败：

```json
{"ok":false,"error":{"code":"...","message":"...","details":{}}}
```

Reader page 支持 `--jsonl`：

```json
{"type":"meta","ok":true,"data":{"schema":"tgctl.reader.v1"}}
{"type":"item","data":{}}
{"type":"end","data":{"count":1,"next_cursor":"...","has_more":true}}
```

默认 page=100，max=500；无提示无限 history 被禁止。

## 3. 账号

```powershell
tgctl account get --json
```

只返回 safe fields：`user_id/display_name/username/premium/bot/language_code`。不返回手机号、credentials、access hash。

## 4. 完整 dialogs

```powershell
tgctl dialogs list --limit 100 --json
tgctl dialogs list --type private --jsonl
tgctl dialogs list --folder "保研" --archived all --json
tgctl dialogs list --cursor <token> --json
```

覆盖：group/supergroup/channel/private/bot/Saved Messages/archive/forum/unread/pinned/muted/folder/migration metadata。

Cursor 是 opaque HMAC token，绑定 method/query，不携带 `access_hash/file_reference`。

## 5. Chat 详情 / members

```powershell
tgctl chats get --chat <ref> --json
tgctl chats members --chat <ref> --role owner --json
tgctl chats members --chat <ref> --role admin --limit 100 --jsonl
```

`<ref>` 支持 marked chat id、精确 `@username`、精确 title/display name、`me`。同名 → `AMBIGUOUS_CHAT` + candidate IDs。

owner/admin/member 来自 Telegram participant/admin data，不通过显示名猜。角色语义是**查询时 current snapshot**，不是历史管理员任期。

v0.3.1 在 owner 缺失时把 `owner_visibility` 细分为可解释状态，包括 `available`、`insufficient_permissions`、`participants_unavailable`、`creator_not_in_returned_page`、`telegram_not_returned` 和数据真正支持时的 `not_found`，不再把不同原因都压成 `not_found`。

## 6. Message history

```powershell
tgctl messages history --chat <ref> --limit 100 --json
tgctl messages history --chat <ref> --cursor <token> --json
tgctl messages history --chat me --since 2026-08-01 --until 2026-09-01 --jsonl
```

- newest → older；
- since inclusive / until exclusive；
- 不推进 read marker；
- 默认不下载 media；
- Basic Group→Supergroup logical history 使用 current→legacy composite cursor；唯一定位键 `(source_chat_id,message_id)`。

Rich schema 包含：structured sender、text/caption、entities、reply、forum topic、forward origin、grouped id、views/forwards、reactions、poll、service action、pinned、media metadata、availability。

## 7. Message get

```powershell
tgctl messages get --chat <ref> --ids 123 456 --json
```

默认 v0.3 rich schema。旧简化 schema 临时兼容：

```powershell
tgctl messages get --chat <ref> --ids 123 --legacy-schema --json
```

缺失 → `MESSAGE_NOT_FOUND`；不能把“查不到”直接声称为“已删除”。

## 8. Advanced search

```powershell
tgctl messages search --chat <ref> --contains "pikpak" --limit 500 --json
tgctl messages search --chat <ref> --regex "release-\d+" --json
tgctl messages search --chat <ref> --sender-role admin --contains "pikpak" --json
tgctl messages search --chat <ref> --sender-id 123456 --since 2026-08-01 --json
tgctl messages search --chat <ref> --url-domain mypikpak.com --json
tgctl messages search --contains "预推免" --limit 100 --jsonl
```

支持 single/global、contains、regex、sender-id、sender-role、since/until、message-type、topic、has-link、url-domain、cursor、limit。

`--sender-role` 的角色判断基于**查询时 current admin/member snapshot**。当前 sender-role 补丁把 admin 匹配扩展到：当前管理员、当前群主、Telegram 明确标记的匿名管理员，以及 Telegram 明确以当前群组身份发布的消息。它不会把普通成员、`forward_origin` 中的管理员、只有 `post_author` 文字署名的消息或完全无身份依据的 unknown 当成管理员。

性能边界：只有请求显式带 `--sender-role` 时，reader 才允许读取当前管理员快照并启用受限 sender peer 解析。sender entity 解析使用**单次 search 请求内缓存**，同一 peer 最多解析一次，失败也缓存；普通 history、普通 GUI 手动导出、普通域名/contains/regex search 不因这个补丁增加 sender 身份网络请求。

`--regex` 是 Python regex 的本地 bounded filter。默认忽略大小写，`--case-sensitive` 同时控制 contains/regex 的大小写语义。空、非法或超过 512 字符的 regex 返回 `INVALID_ARGUMENT`，并且在 Telegram 请求开始前失败。regex 与 case-sensitive 状态属于 cursor query fingerprint；换 regex 后继续使用旧 cursor 返回 `INVALID_CURSOR`。regex 可与其他筛选组合；legacy schema 不支持 regex。

`--url-domain` 解析真实 hostname；`mypikpak.com.evil.com` 不匹配 `mypikpak.com`。不会访问 URL 或 follow redirect。

v0.3.1 的 hostname/IDNA 规范化完全离线，不依赖网络或公共后缀数据；裸域名、完整 URL、大小写和首尾空格会规范到稳定 hostname。非法域名返回 `INVALID_ARGUMENT`，不会退化成 `TELEGRAM_ERROR`。规范值参与 cursor query fingerprint，因此等价写法可续页，不同域名的 cursor 返回 `INVALID_CURSOR`。

全局搜索为 bounded candidate scan；不会为了凑满 limit 无限扫整个账号。返回 `scanned_count/matched_count/next_cursor/has_more/timing`。

## 9. Sender identity

统一 sender 尽量返回：

```text
sender_id
sender_type=user|chat|channel|anonymous_admin|unknown
display_name
username
posted_as_chat_id
is_creator
is_admin
admin_title
anonymous_admin
via_bot_id
role_basis
unknown_reason
```

身份判断只依据 Telegram 提供的结构化 sender 信息：`sender`、`sender_id`、`from_id`、`peer_id`、`sender_chat`、`post_author`、`via_bot_id` 以及 Telegram 暴露的匿名管理员/send-as 标志。不得根据正文、链接、群名或昵称猜用户身份。

如果消息存在真实 raw sender peer、但实体尚未 hydrated，则**仅在 `--sender-role` search 作用域**允许通过现有 Telegram client 尝试解析一次。解析结果按 peer 在本次请求中缓存；失败后保持 unknown，不会每条消息重复请求。普通 GUI/export/history/search 不启用这项补充解析。

可确定时会恢复 user/chat/channel、broadcast channel post、send-as、anonymous admin 等类型：

- Telegram 明确匿名管理员：`sender_type=anonymous_admin`、`anonymous_admin=true`、`is_admin=true`，不猜具体 user id；
- Telegram 明确以当前群组身份发送：填写 `posted_as_chat_id`，可以作为 admin 来源参与 `--sender-role admin`，但不声称是哪位具体管理员/群主；
- `post_author` 只作为 Telegram 展示标签使用，单独出现时不能证明发送者身份；
- `forward_origin` 始终与实际 `sender` 分离，转发来源中的管理员不能让当前消息匹配 admin sender-role。

Telegram 没有提供足够身份时继续返回 `sender_type=unknown`，并给出例如：

```text
service_message_without_sender
forwarded_message_without_actual_sender
post_author_without_sender_peer
unsupported_or_unavailable_sender_peer
telegram_sender_not_provided
```

## 10. Forum

```powershell
tgctl topics list --chat <forum> --limit 100 --json
tgctl topics history --chat <forum> --topic <id> --jsonl
```

非 forum → `NOT_A_FORUM`。实现使用 Telethon 1.44 `messages.GetForumTopicsRequest(peer=...)`。

## 11. Media

所有普通 reader 默认 metadata-only。

第一次：

```powershell
tgctl media download --chat <ref> --ids 123 456 --output D:\TGMedia --json
```

预期不是下载成功，而是：

```text
DOWNLOAD_CONFIRMATION_REQUIRED
file_count
estimated_bytes
unknown_size_count
confirmation_token
```

第一次不会创建 output dir，也不会下载。

确认后：

```powershell
tgctl media download --chat <ref> --ids 123 456 --output D:\TGMedia --confirm <token> --json
```

普通上限 20 files / 500 MiB；`--allow-large-download` 后最多 200 files / 5 GiB。token 绑定 chat/ids/output/plan 且短时有效。下载写 `.part`，成功后 atomic rename；filename 被安全化，不能通过 `../` 逃出 output。

## 12. 旧写命令仍兼容

```powershell
tgctl forward --from <chat> --to me --ids 123 --dry-run --json
tgctl send --to me --text "test" --dry-run --json
```

v0.3.3 内嵌开发版还提供有界原语：

```powershell
tgctl messages unread --chat <ref> --limit 500 --json
tgctl send-capture --to <ref> --text "#keyword" --url-domain mypikpak.com --dry-run --json
tgctl messages mark-read --chat <ref> --snapshot-token <token> --max-id <id> --confirm MARK_READ_FROZEN_SNAPSHOT --json
```

`messages unread` 的后续页必须传回首页 `next_cursor`。`mark-read` 的 token 与会话、冻结 `lower/upper` 绑定。`send-capture` 真实执行属于 Telegram write；请求已发送后连接中断时不得重放。

- forward = Telegram 真 forward；
- send = plain text；
- 默认 forward 20，显式 `--allow-large-batch` 最多 200；
- export 活跃时真实 write → `EXPORT_IN_PROGRESS`；
- FloodWait → `FLOOD_WAIT/retry_after_seconds`，不 retry storm；
- write 请求已发送但响应前 transport 中断 → `WRITE_OUTCOME_UNKNOWN`，不自动重发。

普通 Reader 扩展不会触发任何写入。`send-capture` 和 `messages mark-read` 是独立的受限执行面，具体安全语义见 ADR-008。

## 13. 退出码

```text
0  success
2  INVALID_ARGUMENT
3  NOT_AUTHORIZED / AUTH_GUI_ONLY
4  CHAT_NOT_FOUND / MESSAGE_NOT_FOUND
5  AMBIGUOUS_CHAT
6  FLOOD_WAIT
7  WRITE_FAILED
8  SESSION_BUSY
9  EXPORT_IN_PROGRESS
10 WRITE_OUTCOME_UNKNOWN
11 DAEMON_UNAVAILABLE
12 INVALID_CURSOR / CURSOR_STALE
13 ACCESS_DENIED / MEMBERS_UNAVAILABLE
14 NOT_A_FORUM
15 DOWNLOAD_CONFIRMATION_REQUIRED
16 DOWNLOAD_LIMIT_EXCEEDED
1  other failure
130 Ctrl+C
```

## 14. 日志/敏感信息

普通 log 不记录 message body、caption、URL text、媒体 filename。stdout 只有用户明确 reader 命令可返回正文。

严禁输出：api_id/api_hash、phone、OTP、2FA、Session、credentials 原文、access_hash、file_reference、IPC secret。

正常 GUI 关闭不得产生 `Fatal application error`、`Traceback`、未等待协程或 `Task was destroyed`；真正异常仍应保留错误日志。

## 15. 推荐 Codex 指令

> 使用 tgctl，只读列出我 Telegram 的所有会话类型，分页直到 `has_more=false`，不要执行任何写操作或媒体下载。

> 找到目标聊天，读取最近 500 条并列出当前 owner/admin；再用 `--url-domain <domain>` 与 `--regex <pattern>` 做 bounded 搜索。只依据结构化 sender/forward 字段，不根据正文猜身份。

> 在目标超级群中用 `--sender-role admin --url-domain <domain>` 做 bounded 只读搜索；统计 actual sender 分类，不把 forward_origin 或 post_author 文本当作管理员身份。

> 搜索 Saved Messages 中最近一个月包含“保研”的内容，只读，不标已读。

> 读取这个 Forum 的 topic 列表并总结指定 topic，不下载媒体。

## 16. 当前 sender-role 补丁真人只读复测

正式 v0.3.1 已发布；当前 `codex/v0.3.2-sender-role-fix` 是基于 v0.3.1 的小型 Candidate 补丁，不得覆盖现有 v0.3.1 Release。

自动化通过后，建议在用户本机对 Svip 做一次**只读 bounded**复测：

```powershell
tgctl messages search --chat <Svip-ref> --sender-role admin --url-domain mypikpak.com --limit 500 --json
```

只比较聚合统计：总匹配数，以及 `user/current-admin/current-owner/anonymous_admin/current-chat-send-as/unknown` 等分类数量。不要把真实 message body、URL、caption 或 media filename 粘贴到 Issue/PR/日志。

重点验收：

1. sender peer 存在但 entity 未加载时，`--sender-role` search 能受限恢复；同 peer 不重复请求；
2. 当前管理员/群主能匹配 admin；
3. Telegram 明确匿名管理员能匹配 admin，但不暴露/猜测个人 user id；
4. 当前群 send-as 能匹配 admin，并正确填写 `posted_as_chat_id`；
5. 普通成员、forward_origin 管理员、仅 post_author 文本、完全 unknown 不匹配 admin；
6. 普通 GUI 手动导出与普通 history/search 不出现本补丁新增的 sender 解析请求；
7. no mark-read / no media download / no real send-forward。

默认不执行真实 send/forward、mark-read、media confirm download、群管理、FloodWait 压测或 Session reset。需要这些写操作必须单独取得用户确认。

Mock/CI 不能代替真实账号 E2E。
