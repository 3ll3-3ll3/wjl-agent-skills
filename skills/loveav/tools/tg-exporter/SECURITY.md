# Security Policy

TG Exporter 处理真实 Telegram 用户账号 Session、聊天正文与少量显式副作用，因此默认采用：**本地最小权限、单 Session 所有权、默认只读、最少持久化、显式写入边界、可审计但普通日志不记录正文**。

## Sensitive data must stay local

以下内容不得提交到 GitHub、Issue、PR、CI log、普通 app log 或公开文档：

- Telegram `api_id` / `api_hash`；
- 手机号；
- OTP / 登录验证码；
- 2FA 密码；
- `*.session` / session journal / Session 内容；
- credentials 原文；
- IPC auth secret；
- Telegram `access_hash`；
- Telegram `file_reference` bytes；
- 用户真实聊天正文/导出文件；
- 用户真实头像 cache 二进制。

用户明确执行 reader 命令时，消息正文可出现在该命令 stdout JSON/JSONL；这不等于允许把正文写进普通日志。

## Local runtime

兼容目录固定：

```text
%APPDATA%\TelegramMultiChatExporter\
```

可能含：`api_credentials.json`、`telegram.session`、journal/lock、settings/state、`logs\app.log`、avatar cache、daemon identity/job metadata。

这些都不是发布资产。不得通过删除 lock 文件绕过 OS lock。

## v0.3 daemon trust boundary

```text
GUI ─┐
     ├→ authenticated local Named Pipe → TG daemon → Telegram Session
tgctl┘
```

- daemon 是唯一 TelegramClient/Session owner；
- GUI/tgctl 不 fallback direct Session；
- Pipe 只传 UTF-8 JSON bytes，禁止 pickle object transport；
- 不开放 TCP/HTTP；
- local IPC auth secret 不 stdout、不 log、不 Git；
- 旧 direct process 已锁 Session 时安全返回 `SESSION_BUSY`，不得抢锁/复制 Session。

## Logging allowlist

普通日志允许：动作/阶段、safe error class/code、proxy safe label、chat/message/topic safe IDs、数量、耗时、text length、成功/失败。

普通日志禁止：

- api_id / api_hash；
- phone / OTP / 2FA；
- Session/credentials/IPC secret；
- access_hash/file_reference；
- message body/caption；
- URL 文本；
- media filename；
- raw TL object repr（除非经过明确 safe mapper）。

新增异常日志前先确认 `repr(exc/object)` 不会包含上述字段。Reader 对 Telegram RPC 错误优先返回安全错误类型名，而不是 raw TL repr。

## Default reader is Telegram read-only

以下第三代能力不得产生 Telegram write/read-ack：

```text
account get
dialogs list
chats get
chats members
messages history/search/get
topics list/history
media metadata
```

它们不得发送、转发、删除、退群、改 Chat Folder、投票、标已读或自动下载媒体。读取不应推进 Telegram read marker。

Secret Chat、已删除内容恢复、账号无权访问内容不尝试绕过。

## Explicit media download

`media download` 是**本地磁盘写入**，不是 Telegram 写入，但仍必须显式授权：

1. 用户提供 chat/ids/output；
2. 第一次只生成 plan，返回 `DOWNLOAD_CONFIRMATION_REQUIRED`、数量、已知预计字节、未知大小数量、confirmation token；不创建 output dir、不下载；
3. 第二次必须带同一 query/plan 的短时 HMAC token；
4. normal：20 files / 500 MiB；explicit large：最多 200 files / 5 GiB；hard cap 不可绕过；
5. filename 只取 basename 并做 Windows/path traversal 安全化；
6. 写 `.part`，成功后原子 rename；错误/取消清理当前 `.part`；
7. confirmed IPC request 的 transport outcome unknown 不自动 retry。

普通 reader 永远不因为“看见有媒体”而自动下载。

## Existing Telegram writes

已批准的 Telegram write 仍只有既有边界：

- `forward`：真正 Telethon forward，dry-run，默认 20、显式大批量 200，同名歧义拒绝；
- `send`：纯文本，dry-run，`parse_mode=None`；
- GUI optional read-ack：仅用户明确开启 current-unread Option B，严格 `JSON success → checkpoint → optional read ack`。

v0.3 Reader 不扩大上述授权，不新增隐式 mark-read。

Export 活跃时真实 send/forward 立即 `EXPORT_IN_PROGRESS`，不得排队后自动发出。已发送 write 请求若返回前 transport 中断 → `WRITE_OUTCOME_UNKNOWN`，不得自动 retry。

FloodWait 返回 `retry_after_seconds`，不 retry storm。

## Identity truthfulness

- owner/admin/member 只能依据 Telegram participant/admin data；
- role 表示查询时 current snapshot，不伪造历史管理员任期；
- anonymous admin/send-as 不从显示名、post_author 或管理员列表猜隐藏 user；
- 成员不可枚举时返回 unavailable/access denied，不拿消息作者集合冒充完整成员表；
- URL domain 只做安全 hostname parsing，不访问链接、不 follow redirect。

## Cursor/output safety

Cursor 必须 HMAC/query-bound，只包含 safe offset/peer IDs/segment 等；不得带 access_hash、file_reference、Session/credentials。

MessageInfoV3/ChatDetails/DialogInfo/ParticipantInfo 使用 allowlisted safe fields，不序列化 raw Telethon object。

`MESSAGE_NOT_FOUND` 只能表示 not found/unavailable，不能武断声称内容“已删除”。

## CI / real E2E

GitHub Actions 不保存真实 Telegram credential。CI 使用 mock/fake Telegram + 本地 OS lock 测试：

- no api credential/message body logging；
- cursor/output no access_hash/file_reference；
- media plan no disk write；
- packaged UTF-8 JSON；
- legacy OS Session lock → packaged `SESSION_BUSY` + native exit 8；
- PyInstaller smoke。

Mock 不能代替用户真实账号只读 E2E。真实测试默认不执行 Telegram write；媒体真实下载作为本地磁盘副作用也只在用户明确选择测试时进行。

## Out of scope

除非用户重新明确授权并重新做安全设计，不增加：MCP Server、Web/TCP server、Bot API、24/7 Telegram listener、自动转发规则、AI 自主分类、联系人/群/管理员管理、删除消息、退群、改 Chat Folder、媒体发送/媒体转发、绕权读取、Secret Chat。

## Accidental secret response

发现 Secret 误提交时：立即停止传播；轮换相关 credential/Session；必要时清理 Git 历史；在 HANDOFF 只记录非敏感摘要，不复制 Secret。
