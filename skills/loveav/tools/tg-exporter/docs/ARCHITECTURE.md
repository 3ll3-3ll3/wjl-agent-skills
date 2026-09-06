# Architecture

## 1. Product shape

v0.3.0 由三个本地角色组成：

```text
TGExporter GUI ─┐
               ├→ local IPC → TG daemon → TelegramService/Telethon → user account
tgctl / Codex ─┘
```

只有 daemon 持有 `%APPDATA%\TelegramMultiChatExporter\telegram.session`。GUI 仍是可视化导出工具；tgctl 是 Codex 的机器接口；Personal Account Reader 是 daemon-side Core。

## 2. 进程与生命周期

GUI/tgctl 都通过 `DaemonIPCClient` 调用本机 Named Pipe。Pipe payload 只传 UTF-8 JSON bytes，不传 pickle，不开 TCP/HTTP。

Daemon：

- 单实例 `FileLease`；
- 唯一 `TelegramService` / `SessionLease`；
- Windows tray；
- GUI lease/heartbeat；
- export job coordinator；
- operation coordinator；
- reader RPC；
- 无活跃 GUI/job/request 后约 10 分钟 idle shutdown；
- 下次 GUI/tgctl 自动唤醒。

## 3. Session semantics

正常 v0.3：GUI + tgctl 共用 daemon，不应互相 `SESSION_BUSY`。

兼容边界：旧 v0.1.x/direct process 已经 OS-lock Session → daemon `SessionLease` 获取失败 → client 得到 `SESSION_BUSY`。packaged `tgctl` native exit code 必须严格为 8；UTF-8 console fix 防止中文 JSON 输出二次异常覆盖退出码。

## 4. OperationCoordinator

第一版稳定性优先，单 Telegram client 串行协调：

```text
LOCAL status/job/heartbeat → 立即
export → 独占 Telegram work
reader → export 活跃时等待
real send/forward → export 活跃时立即 EXPORT_IN_PROGRESS
media confirmed download → 按 reader 队列等待 export
```

write 请求发送后 transport outcome unknown 不自动 retry。

## 5. GUI export pipeline

GUI 仍提交 `GroupExportPlan`，但 Telegram 抓取和 JSON 写入在 daemon 内执行：

```text
GUI plan
→ export.batch.start RPC
→ daemon ExportCoordinator
→ Telegram
→ serializer
→ output/category/group/timestamp.json
→ atomic replace
→ checkpoint
→ optional read ack
```

正文不需要为批量导出跨 Named Pipe 来回搬运。关闭/崩溃 GUI 后 daemon job 可继续；GUI 重开读取安全 job metadata。

## 6. Reader 模型隔离

GUI `GroupInfo` 保持导出器语义。全账号 reader 使用独立模型：

```text
AccountProfile
DialogInfo
ChatDetails
ParticipantInfo
SenderInfo
MessageInfoV3
ForumTopicInfo
MediaMetadata
Page
```

因此 private/bot/Saved Messages 不会破坏 GUI 群组工作区假设。

## 7. Reader service layering

```text
TelegramService
  └─ Telethon client / Session / proxy

PersonalAccountReader
  ├─ account
  ├─ dialogs
  ├─ dialog resolution
  ├─ members/role snapshot
  ├─ chat details
  └─ rich history/get

PersonalAccountReaderV3
  └─ logical-chat identity fixes，例如 legacy history 仍按 current supergroup role snapshot

reader_search.py
reader_topics.py
reader_media.py
reader_rpc.py
```

Daemon v3 server subclass在保留 v2 auth/export/write safety 的同时增加 reader methods。

## 8. Dialog completeness

`dialogs.list` 与 GUI `chats.catalogue` 分开。

Reader dialog types：group/supergroup/channel/private/bot/saved。包含 archive/forum/unread/pinned/muted/folder/migration safe metadata。

为避免 Telegram activity order 在翻页时被新消息重排，完整目录默认每次构建当前 catalogue 后按 canonical key 稳定排序，并用 HMAC cursor 续页。

Saved Messages 若未自然作为 dialog 返回，则合成唯一 self row `reference=me`，不重复 self private row。

## 9. Cursor

`CursorCodec`：

- base64url body.signature；
- HMAC-SHA256；
- version + method + query fingerprint + safe position；
- 不包含 access_hash/file_reference；
- query mismatch/tamper → `INVALID_CURSOR`；
- Telegram entity offset 无法恢复 → `CURSOR_STALE`。

默认 page 100，max 500。

## 10. Members / roles

群/频道 participant 使用 Telegram participant APIs；Basic Group 使用 full chat participants。role cache 为短 TTL 内存 cache，不持久化成员正文。

`owner/admin/member` 是 current snapshot。匿名管理员/send-as 只表达 Telegram 可证明的身份，不根据显示名推断隐藏 user。

## 11. MessageInfoV3

统一 schema 包括安全可得的：chat/source chat/message id、date/edit date、structured sender、text/caption、entities、reply、forum topic、forward origin、grouped id、views/forwards、reactions、poll、service action、pinned、media metadata、availability。

Media 默认 metadata-only，不下载 `file_reference`。

Migration history：current segment → legacy segment；唯一定位键 `(source_chat_id,message_id)`。

## 12. Search

Advanced search 先服务器/会话范围缩小候选，再 bounded local filters。支持 single/global、contains、sender id/current role、time、message type、topic、link、URL domain。

每次候选扫描有 cap；达到 cap 后通过 cursor 续跑，不无限扫描。URL domain 使用 URL parsing/hostname normalization，不访问网络目标 URL。

## 13. Forum

Forum topic list 使用 Telethon 1.44 `functions.messages.GetForumTopicsRequest(peer=...)`。Topic history 复用 rich history 并以 topic id 约束。非 forum → `NOT_A_FORUM`。

## 14. Explicit media download

普通 history/search/get 不下载。

`media.download`：

```text
RPC 1: resolve + metadata plan
→ DOWNLOAD_CONFIRMATION_REQUIRED + token
→ no output dir / no bytes written

RPC 2: same chat/ids/output + confirm token
→ validate HMAC/query/plan digest/TTL
→ enforce 20/500MiB or explicit large 200/5GiB
→ download to safe *.part
→ actual-byte hard cap
→ os.replace to final file
```

文件名只取 basename 并过滤 Windows/path traversal 字符。confirmed call 在 IPC 中标记为 side effect，transport 中断不自动 retry。

## 15. JSON / JSONL

Daemon IPC 始终 bounded JSON frame。JSONL 不把 Pipe 变成无限 stream：daemon 返回最多 500 条 page，tgctl 再输出 meta/item/end 行。

## 16. Logging / secrets

AppData 兼容目录继续：

```text
api_credentials.json
telegram.session
telegram.session.lock
settings.json
local_state.json
logs/app.log
cache/avatars/
```

禁止 stdout/log/cursor：api_id/api_hash、phone、OTP/2FA、Session、credentials 原文、access_hash、file_reference、IPC secret。消息正文只可在用户明确 reader stdout 中返回，普通 log 不记录正文/caption/URL text/media filename。

## 17. Packaging

Candidate CI 构建：

```text
TGExporter.exe
tgctl.exe
```

两个 one-file 可作为 daemon worker 自启动。CI 必须跑 pytest、import、两个 PyInstaller、packaged `SESSION_BUSY exit 8` regression、packaged smoke，并上传 candidate artifact。

正式 Release packaging 只有用户验收后才进行；v0.3 candidate 不自动发布。
