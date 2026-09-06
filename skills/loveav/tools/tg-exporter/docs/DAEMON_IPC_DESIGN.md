# Single Telegram Daemon + Local IPC Design

> 状态：**Accepted design / implementation not yet merged**
> 目标版本：**v0.2.0**
> 基线：TG Exporter v0.1.9

## 1. 用户已经确认的目标体验

本设计不再追求“所有前端同时并发访问 Telegram”，而是追求**一个后台拥有 Telegram、多个前端共享它、任务顺序可预测**。

用户于 2026-08-29 确认：

1. **关闭 GUI 时如果正在导出，导出继续在后台完成。**
2. **GUI 没打开时，Codex/tgctl 可以自动唤醒后台并查询 Telegram。**
3. **GUI 正在导出时，Codex 的 Telegram 搜索/读取等待导出结束，不与导出并发。**
4. **GUI 正在导出时，真正 send/forward 禁止执行。** dry-run 可以保留，但凡需要 Telegram preflight 的部分也等待导出完成。
5. **GUI 崩溃时 daemon 与导出任务继续；重新打开 GUI 后能恢复看到当前任务进度/最近结果。**
6. **daemon 在 Windows 右下角显示托盘图标，可查看状态并手动退出后台。**
7. **手机号 / OTP / 2FA 登录仍然只由 TG Exporter GUI 交互；tgctl/Codex 不提供登录入口。**
8. **没有 GUI lease、没有活跃请求、没有 export job 后，daemon 空闲约 10 分钟自动退出；下次按需唤醒。**

最终体验：

```text
                       ┌───────────────────────────┐
                       │ TG Telegram daemon        │
                       │                           │
                       │ 唯一 TelegramService      │
                       │ 唯一 Telethon client      │
                       │ 唯一 telegram.session     │
                       │ export job + operation Q  │
                       │ Windows tray icon         │
                       └─────────────┬─────────────┘
                                     │ authenticated local IPC
                         ┌───────────┴───────────┐
                         ▼                       ▼
                  TG Exporter GUI             tgctl.exe
                                                 │
                                                 ▼
                                               Codex
```

v0.2.0 不实现 MCP；未来 MCP 只作为同一 IPC client 的薄 adapter。

## 2. 必须保持的不变量

- 只复用 `%APPDATA%\TelegramMultiChatExporter\telegram.session`，不复制第二 Session。
- 复用现有 `api_credentials.json` 与 Windows system proxy detection。
- GUI 导出仍是独立 JSON，不做累计数据库。
- 输出仍是 `总输出目录 / Export Category / 群组 / YYYY-MM-DD_HH-mm-ss.json`。
- GUI 消息导出仍不下载聊天媒体；caption 可保留。
- Basic Group → Supergroup migration collapse 不变。
- current unread frozen snapshot 与 Option B 顺序不变。
- tgctl 对外 JSON envelope / error code 尽量兼容 v0.1.9。
- forward 必须是真正 Telegram forward；send 仍只允许纯文本。
- dry-run、20/200 cap、AMBIGUOUS_CHAT、FloodWait stop、no-body logging 必须同时在 client 和 daemon policy 层保留。
- 不增加 24/7 listener、自动转发规则、AI Agent、Bot API、联系人/群/管理员管理、删除消息、媒体发送/媒体转发。

## 3. Session 所有权

迁移完成后 GUI/tgctl **不再直接创建 TelegramClient**。

```text
GUI       ─┐
tgctl     ─┼── IPC ──> daemon ──> TelegramService ──> telegram.session
future MCP─┘
```

现有 `SessionLease` 保留，但只有 daemon 获取它。这样升级期间若旧 v0.1.9 GUI/tgctl 仍直接占用 Session，新 daemon 会安全失败，而不是绕过锁。

另加 daemon singleton OS lock：

```text
%APPDATA%\TelegramMultiChatExporter\tg-daemon.lock
```

锁依赖 OS ownership，不依赖 lock 文件是否存在。

## 4. IPC：Windows Named Pipe + JSON bytes

首选 Python 标准库 `multiprocessing.connection` 的 Windows `AF_PIPE`。

- 不开 TCP/HTTP/Web Server；
- 不监听 LAN；
- 不需要 Windows Service；
- 只使用 `send_bytes()/recv_bytes()`；
- 禁止 `Connection.send()/recv()` 的 pickle object transport；
- payload 为 UTF-8 JSON；
- 单 frame 建议 hard cap 8 MiB。

兼容 AppData 增加：

```text
ipc_identity.json
```

首次原子生成随机 instance id + 256-bit auth secret。Pipe 名带非敏感 instance id；auth secret 不写日志、stdout 或 Git。

安全目标是防止误连接和普通跨用户连接；不声称抵抗已经取得当前 Windows 用户 AppData 读取权限的恶意程序。

## 5. daemon 生命周期与托盘

### 5.1 按需启动

GUI/tgctl 调用 `ensure_daemon()`：

```text
try IPC hello
→ 不存在
→ 启动 tg-daemon.exe
→ 等待 pipe ready
→ 调用
```

不注册 Windows Service，不设置开机自启。

### 5.2 GUI lease

GUI 打开后创建 lease，并周期 heartbeat。正常关闭 detach；GUI 崩溃则 lease 超时自动失效。

只要 GUI lease 有效，daemon 不因 idle 退出。

### 5.3 关闭 GUI

- 没有 export job：GUI detach，daemon 进入 idle 计时。
- 有 export job：GUI 退出不取消 job；daemon 继续导出。
- 重开 GUI：通过 `export.jobs.list/status` 恢复当前 job 和最近结果。

### 5.4 idle shutdown

以下条件全部满足约 10 分钟后 graceful shutdown：

```text
no live GUI lease
no active export job
no active IPC request
no queued Telegram read
```

下次 GUI/tgctl 调用自动重新唤醒。

### 5.5 Windows tray icon

`tg-daemon.exe` 在交互式 Windows 用户会话中显示托盘图标。托盘至少提供：

- 状态：未连接 / 已连接 / 正在导出 / 空闲倒计时；
- “打开 TG Exporter”；
- “退出后台”。

手动退出规则：

- 无运行中 export job：graceful disconnect + exit；
- 有运行中 export job：不得直接杀死任务；托盘提示“导出进行中，完成后再退出”或提供“导出完成后退出”；第一版优先后者。

托盘不可用时 daemon 功能仍应继续，不能因为 Explorer/tray 异常导致导出失败。

## 6. Telegram 调度：单作业队列而不是无限并发

这是用户选择 3B/4B 后的核心。

### 6.1 export 是独占 Telegram job

开始 GUI export batch 后：

```text
export_active = true
```

整个 batch 由 daemon `ExportCoordinator` 串行/受控执行。

### 6.2 Telegram read 在 export 期间等待

以下 tgctl/GUI Telegram read：

```text
chats.list
messages.search
messages.get
avatar.get
需要真实 Telegram 的 account refresh
```

如果 export 正在运行，不与 export 并发，而是在 daemon operation coordinator 中等待 export 完成。

`system.hello`、daemon status、job status/result、GUI heartbeat 等**纯本地 RPC 不等待**，所以用户仍能查看进度。

### 6.3 真正 write 在 export 期间拒绝

`forward` / `send` 若 `dry_run=false` 且 export active：

```json
{
  "ok": false,
  "error": {
    "code": "EXPORT_IN_PROGRESS",
    "message": "当前正在导出。请等待导出完成后再发送或转发。"
  }
}
```

不得自动排队后偷偷发送，因为用户选择的是“导出期间禁止发送”，不是“以后自动帮我发”。

`dry_run=true` 不产生 Telegram write；如果 dry-run 需要读取源消息做 preflight，则按普通 read 等待 export 完成。

### 6.4 write serialization

无 export 时，真正 write 仍通过单独 write lock 串行执行，并再次验证：

- dry-run flag；
- forward 20/200 cap；
- chat ambiguity；
- media restriction；
- FloodWait；
- no-body logging。

## 7. GUI export job 必须在 daemon 内执行

当前 `exporter.py` 直接用 TelegramClient 迭代消息。长历史导出不能改成“daemon 抓几万条正文 → 一个巨大 IPC response → GUI 写盘”。

采用：

```text
GUI 提交 GroupExportPlan batch
→ daemon 创建 job_id
→ daemon 内调用 exporter + TelegramService.client
→ daemon 直接原子写最终 JSON
→ daemon 更新 checkpoint
→ optional Option B read ack
→ GUI 只轮询 job 状态/结果
```

因此正文不为了 GUI 导出跨进程搬运。

关键顺序继续由 daemon coordinator 保证：

```text
Telegram fetch
→ JSON atomic write success
→ checkpoint success
→ optional read acknowledgement
```

建议 RPC：

```text
export.batch.start
export.jobs.list
export.job.status
export.job.result
export.job.request_exit_after_finish
```

第一版可以暂不支持危险的强制 cancel；若以后加 cancel，必须定义 JSON/checkpoint/read-ack 的原子边界。

job registry 至少在 daemon 生命周期内保留 active + recent jobs；另将**不含消息正文**的 job metadata 原子持久化到 AppData，使 daemon 意外重启后 GUI 能显示 interrupted/completed 摘要。daemon 自身崩溃后不承诺继续原 job；只保证 GUI 崩溃不会终止 daemon job。

## 8. 登录：仍只由 GUI 交互

`tgctl` 没有 phone/OTP/2FA 命令。

为了让 daemon 成为唯一 Telethon owner，GUI 的登录 UI 改为调用仅允许 `client.kind=gui` 的 auth RPC：

```text
auth.configure_api
auth.status
auth.send_code
auth.sign_in_code
auth.sign_in_password
```

GUI 负责收集输入与显示错误；daemon 负责真正 Telegram 调用。敏感参数允许在认证本地 pipe 内传输，但：

- 绝不日志记录 params；
- 不持久化 OTP/2FA；
- api_hash 仅按现有规则保存到本地 `api_credentials.json`；
- tgctl/Codex 调 auth method 必须返回 `AUTH_GUI_ONLY`。

## 9. IPC protocol v1

协议：`tgipc/1`。

请求：

```json
{
  "protocol":"tgipc/1",
  "request_id":"uuid",
  "client":{"kind":"gui","app_version":"0.2.0"},
  "method":"messages.search",
  "params":{}
}
```

响应：

```json
{"protocol":"tgipc/1","request_id":"uuid","ok":true,"result":{}}
```

或：

```json
{"protocol":"tgipc/1","request_id":"uuid","ok":false,"error":{"code":"...","message":"...","details":{}}}
```

要求：

- unknown method 明确拒绝；
- daemon 不返回 traceback；
- request log 只记 request_id/method/duration/status，不记 message body 或敏感 auth params；
- `tgctl --json` 对外继续映射 v0.1.9 envelope，不暴露 IPC 内部细节。

`system.hello` 返回 protocol/app version/capabilities/daemon pid/job state。

## 10. daemon crash / write unknown outcome

read-only RPC 在 daemon crash/pipe broken 后，client 可自动 `ensure_daemon()` 并最多重试一次。

**真实 write 绝不自动重试。** 如果 send/forward 已交给 daemon 后连接中断，返回：

```text
WRITE_OUTCOME_UNKNOWN
```

调用者必须先检查目标聊天，避免重复发送。

## 11. 建议模块

```text
src/telegram_exporter/
├─ daemon_main.py
├─ daemon_server.py
├─ daemon_manager.py
├─ daemon_tray.py
├─ operation_coordinator.py
├─ ipc_identity.py
├─ ipc_protocol.py
├─ ipc_transport.py
├─ ipc_client.py
├─ telegram_proxy.py
└─ export_coordinator.py
```

`telegram_service.py` 与 `exporter.py` 保留为 daemon-side Telegram Core。

## 12. 实施阶段

### Phase A — IPC foundation（无真实 Telegram）

- identity/auth；
- AF_PIPE bytes transport；
- protocol validation；
- daemon singleton；
- fake backend；
- ensure_running；
- tests：并发启动、坏 auth、坏 JSON、frame cap、protocol mismatch。

### Phase B — daemon owns Telegram + tgctl migration

- daemon 唯一实例化 TelegramService；
- tgctl 全命令迁到 IPC；
- operation coordinator：export read wait / write reject；
- 保持 v0.1.9 CLI JSON/exit-code 兼容；
- write unknown outcome 保护。

### Phase C — GUI auth/read/avatar + tray

- GUI 登录 RPC；
- GUI catalogue/avatar/read 调 IPC；
- GUI lease/heartbeat；
- tray status/open/exit-after-export；
- GUI 不再创建 TelegramClient。

### Phase D — GUI export jobs

- ExportCoordinator；
- daemon-side JSON write/checkpoint/read ack；
- GUI job progress/restore；
- GUI close/crash 后 job 继续。

### Phase E — lifecycle / packaging / recovery

- idle 10 min；
- daemon autostart/restart；
- persisted safe job metadata；
- PyInstaller `tg-daemon.exe`；
- packaged smoke tests。

### Phase F — v0.2.0 release gate

必须验证：

- v0.1.9 Session/settings 原地复用；
- GUI + tgctl 不再 `SESSION_BUSY`；
- export 时 tgctl read 真正等待；
- export 时 true send/forward 返回 `EXPORT_IN_PROGRESS`；
- GUI 关闭/崩溃后 export 继续；
- GUI 重开恢复 job；
- tray 状态与手动退出；
- idle shutdown + later auto-wake；
- real Saved Messages dry-run/forward/send；
- no credential/body leakage；
- daemon crash 后 read 最多 retry once，write 不自动 retry。

## 13. v0.2.0 明确不做

- MCP Server；
- Windows Service / 开机自启；
- 24/7 Telegram event listener；
- 自动转发规则；
- AI classifier/agent；
- Bot API；
- 联系人/群/管理员管理；
- 删除消息；
- 媒体发送/媒体转发；
- 云端 IPC/Web server。
