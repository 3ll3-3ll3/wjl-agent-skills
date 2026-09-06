# Security Model

本文件描述 TG Exporter 的信任边界、Production 定义、高风险操作和永久安全约束。漏洞/敏感信息细则同时见根目录 [`SECURITY.md`](../SECURITY.md)。

## 1. Production 定义

TG Exporter 没有远程生产数据库、云服务器或 Web API。Production 是：

```text
GitHub 正式 Release 二进制
+
用户本机 %APPDATA%\TelegramMultiChatExporter\
+
用户真实 Telegram 账号
+
用户选择的导出目录
```

当前正式版是 `v0.3.0 @ 8e230e33...`。v0.3.1 仍是 patch Candidate；Actions Artifact 不是 Production。

## 2. 本机敏感资产

`%APPDATA%\TelegramMultiChatExporter\` 可能包含 credentials、telegram.session/journal/lock、daemon/IPC identity、settings/state/job metadata、logs、avatar cache。

永久规则：

- 不删除/迁移整个 AppData 来“修问题”；
- 不复制 Session 以绕过并发；
- 不删 lock 文件绕过 OS ownership；
- 品牌改名不迁移兼容路径；
- Session reset/cleanup 必须由用户明确选择。

## 3. 严禁泄露

不得进入 GitHub、Issue、PR、Actions log、Release notes 或普通 app.log：

- api_id/api_hash；phone；OTP；2FA；
- Session / credentials 原文；
- IPC auth secret；
- access_hash / file_reference；
- 用户真实聊天正文、URL、媒体文件名、导出 JSON、头像二进制。

用户明确执行 reader 命令时，正文可出现在该命令 stdout JSON/JSONL；普通日志仍只允许 safe metadata。

## 4. Session trust boundary

历史 v0.1.x direct-session 仅作为 legacy compatibility：GUI/tgctl 通过 OS `SessionLease` 互斥，冲突必须 `SESSION_BUSY` + packaged native exit 8。

当前 v0.3.0 Production / v0.3.1 Candidate 正常路径：

```text
GUI ─┐
     ├→ authenticated Windows Named Pipe → TG daemon → one Telegram Session
tgctl┘
```

- daemon 是正常路径唯一 TelegramClient/Session owner；
- GUI/tgctl 不 fallback direct Session；
- Pipe 使用 UTF-8 JSON bytes，不 pickle；
- 不监听 TCP/HTTP/LAN；
- auth secret 留在本机，不 stdout/log/Git。

## 5. 副作用分类

### LOCAL
status/job/heartbeat/cursor validation 等。

### TELEGRAM_READ
account/dialogs/chat/members/history/search/get/topics/media metadata。不得 send/forward/delete/leave/改 Folder/vote/mark-read/自动下载。

### LOCAL_DISK_WRITE
GUI JSON export；用户显式确认的 media download。

### TELEGRAM_WRITE
仅既有批准边界：forward、send、GUI current-unread optional read acknowledgement。

### GUI_AUTH
phone/OTP/2FA/API 配置只属于 GUI。

## 6. Telegram write safety

- forward = Telegram true forward；dry-run；默认 <=20，explicit large <=200；
- send = plain text / `parse_mode=None`；dry-run；
- ambiguous target → `AMBIGUOUS_CHAT`，不 first-match；
- FloodWait structured stop，不 retry storm；
- export 活跃时 real send/forward → `EXPORT_IN_PROGRESS`，不排队；
- write request 已送 daemon、response 前 transport 中断 → `WRITE_OUTCOME_UNKNOWN`，绝不自动 replay。

## 7. Read acknowledgement

GUI “导出后标已读”默认 OFF，仅 current-unread：

```text
JSON atomic success
→ checkpoint
→ optional read acknowledgement
```

export 与 ack 使用同一 export-start frozen upper。导出失败不 ack；ack 失败不删除成功 JSON。Reader 不得暗中复用该写能力。

## 8. Explicit media download

默认 metadata-only。真实下载必须：

```text
plan
→ DOWNLOAD_CONFIRMATION_REQUIRED + token
→ no download/no output dir
confirm same plan
→ bounded download
→ *.part
→ atomic rename
```

normal 20 files / 500 MiB；explicit large max 200 / 5 GiB。path/basename 必须安全化。confirmed transport outcome unknown 不自动 retry。

## 9. Identity / search truthfulness

- owner/admin/member 仅依据 Telegram participant/admin data；
- role 是 current snapshot；
- anonymous admin/send-as 不反推隐藏个人；
- actual sender 与 forward origin 分开；
- 无足够信息保持 unknown + reason；
- unavailable 不拿消息作者集合冒充成员表；
- message 查不到不自动声称 deleted；
- `--url-domain` 使用离线 hostname/IDNA parsing，不访问 URL/follow redirect；
- `--regex` 本地 bounded，非法/空/超长 pattern 在 Telegram work 前拒绝；
- Windows ProxyServer 带 auth/query 的输入保持拒绝，safe label 只含 endpoint metadata。

## 10. Migration safety

Basic Group→Supergroup：current Supergroup 是 logical entity，legacy Basic Group 仅 historical source；不按同名猜；消息唯一键 `(source_chat_id,message_id)`；current-unread 只用 current Supergroup；历史 role snapshot 基于 current logical group。

## 11. GitHub / Release safety

- 不直接 push/force-push main；
- 不移动/删除历史 tags；
- 不覆盖 Releases；
- GitHub Actions 不放真实 Telegram credentials；
- `v0.3.0` 已正式发布，视为不可变；
- v0.3.1 PR #24 在本地/真实账号 acceptance + 用户明确授权前保持 Draft，不 merge/release。

仓库当前未强制 branch protection，因此 Agent 必须自行遵守这些规则。

## 12. 明确不做

未经重新授权和安全设计，不新增 MCP Server、TCP/HTTP/Web/Cloud server、Bot API、24/7 listener、自动转发/AI 自主分类、联系人/群/管理员管理、删除消息、退群、修改 Chat Folder、Secret Chat、已删除内容恢复、绕权读取、媒体发送/媒体转发。

## 13. Incident response

Secret 误提交：停止传播、轮换 credential/Session、评估 Git 历史清理，HANDOFF 只记录非敏感摘要。

Telegram write outcome 不确定：绝不自动 retry；先由用户检查目标聊天。