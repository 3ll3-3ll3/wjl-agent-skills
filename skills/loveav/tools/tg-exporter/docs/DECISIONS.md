# Design Decisions

本文件记录已经明确采用、后续 Agent 不应随意反转的设计决策。长期架构/安全决定的完整 Context / Alternatives / Consequences 另见 [`docs/decisions/README.md`](decisions/README.md)。用户若明确改变方向，应同步更新本文件、ADR 与 `HANDOFF.md`。

## GUI / export

- **D-001 Accepted** — 每群每次独立 JSON；历史文件不读取、不合并、不覆盖；同秒 `_2/_3/...`。
- **D-002 Accepted** — GUI JSON 是导出的权威数据源；未来 HTML 只从 JSON 本地渲染。
- **D-003 Accepted** — GUI 聊天导出默认文字/caption，不下载聊天媒体；头像仅 selector cache。
- **D-004 Accepted** — date range / current unread / since last export / Export Category 均按群独立。
- **D-005 Accepted** — focused workspace：catalogue 与主工作区分离。
- **D-006 Accepted / Issue #22** — current unread 在每个群真正开始执行时冻结 `read_inbox_max_id_at_group_start < id <= latest_message_id_at_group_start`；不用 catalogue refresh 旧值，不移除 upper bound。
- **D-007 Accepted** — read-ack 默认 OFF；`JSON atomic success → checkpoint → optional read ack`，且复用同一 frozen upper。
- **D-008 Accepted** — Qt + Telethon 使用 qasync 单事件循环；禁止重新引入 blocking nested modal。
- **D-009 Accepted** — Windows system proxy 通过 `proxy.py` 显式传给 Telethon；安全标签不含认证/query。
- **D-010 Accepted** — Telegram Desktop JSON 兼容目标限“文本范围内尽量一致”，不扩成完整媒体备份。
- **D-011 Accepted** — 正式二进制只经 GitHub Releases；Actions Artifact 仅 Candidate/CI。
- **D-012 Accepted** — 本地状态最小化，不持久化聊天正文。
- **D-013 Accepted / deprioritized** — 杀软误报/代码签名当前不是主线。
- **D-014 Accepted** — Telegram Chat Folders 只读复用，不写回 Telegram。
- **D-015 Accepted** — 品牌 `TG Exporter / TG 导出器`；兼容数据目录保持 `%APPDATA%\TelegramMultiChatExporter\`。
- **D-016 Accepted** — selector 头像懒加载 + 受限并发 + AppData cache；失败不阻断。
- **D-017 Accepted** — Export Category 本地管理；删除分类不删除历史磁盘数据。
- **D-018 Accepted** — Basic Group→Supergroup 显示一个 logical current chat；legacy peer 仅历史 source，不按同名猜 migration。

## tgctl / daemon / write safety

- **D-019 Accepted** — 先建设确定性本地 `tgctl` Core/CLI，不直接做 MCP。
- **D-020 Accepted** — tgctl 复用同一用户 Session，不实现第二套登录；phone/OTP/2FA 仅 GUI。
- **D-021 Historical compatibility** — v0.1.x direct GUI/tgctl 用 OS SessionLease；v0.2+ 正常路径由 daemon 单独持有 Session。
- **D-022 Accepted** — 稳定 JSON envelope/error code 是机器接口契约。
- **D-023 Accepted** — Telegram writes dry-run + hard caps + 无歧义目标；FloodWait 不 retry storm；日志不记正文。
- **D-024 Accepted** — forward 必须 Telegram true forward，不静默复制正文+send。
- **D-025 Accepted** — send 只做纯文本，`parse_mode=None`。
- **D-026 Accepted** — v0.2+ single local daemon 是正常路径唯一 Telegram Session owner。
- **D-027 Accepted** — IPC = authenticated Windows Named Pipe / AF_PIPE + UTF-8 JSON bytes；禁止 pickle/TCP/HTTP。
- **D-028 Accepted** — export 是独占 Telegram job；reader 等待；真实 send/forward 在 export 活跃时立即 `EXPORT_IN_PROGRESS`，绝不排队后发送。
- **D-029 Accepted** — GUI 关闭/崩溃不能取消 daemon-side export；GUI 重开可恢复 safe job metadata。
- **D-030 Accepted** — daemon 按需启动、托盘可见、空闲退出；不是 Windows Service。
- **D-031 Accepted** — auth interaction 仅 GUI；tgctl/Codex 调 auth → `AUTH_GUI_ONLY`。
- **D-032 Accepted** — write request 已送 daemon 后 transport 中断 → `WRITE_OUTCOME_UNKNOWN`；绝不自动 replay。

## v0.3 Personal Account Reader

- **D-033 Accepted** — v0.3.0 继承 v0.2 daemon，新增 Personal Account Reader，不另起 direct-session reader。
- **D-034 Accepted** — reader 使用独立 Account/Dialog/Chat/Participant/Sender/Message/Topic/Media 模型，不机械扩大 GUI GroupInfo。
- **D-035 Accepted** — reader default page 100 / max 500；HMAC/query-bound cursor；不得包含 access_hash/file_reference/credential。
- **D-036 Accepted** — dialogs stable canonical order；history newest→older；migration current→legacy composite cursor；消息唯一键 `(source_chat_id,message_id)`。
- **D-037 Accepted** — sender-role 是查询时 current snapshot，不伪造历史角色；不可见则 unknown/unavailable。
- **D-038 Accepted** — anonymous admin/send-as 结构化，但绝不反推隐藏个人。
- **D-039 Accepted** — rich message metadata 可读；普通 reader media metadata-only；显式下载需 plan→confirmation→download + caps。
- **D-040 Accepted** — 同代 GUI/tgctl 共 daemon，不应互相 SESSION_BUSY；legacy direct lock 仍需 packaged exit code 8。
- **D-041 Accepted** — Telegram 无法可靠证明 deleted 时不得伪造 `deleted=true`；按 ID 查不到为 not_found/unavailable。
- **D-042 Accepted** — URL domain filter 必须解析离线 hostname，exact/subdomain 匹配；不访问 URL/follow redirect。

## Release gates / v0.3.1

- **D-043 Fulfilled / historical** — v0.3.0 Candidate 在自动化完成后曾冻结并等待真人 E2E；用户验收通过后于 2026-08-30 正式发布 `v0.3.0 @ 8e230e33...`。这一 gate 已成功履行，不再把 PR #20/v0.3.0 视为 pending。
- **D-044 Accepted** — 已发布 Release/tag 视为不可变历史。v0.3.1 必须是新的 patch line；不得原地覆盖、移动或重建 v0.3.0。
- **D-045 Accepted** — v0.3.1 search filter：`--url-domain` 使用离线 IDNA/hostname normalization；`--regex` 使用本地 bounded filter；非法输入在 Telegram work 前 `INVALID_ARGUMENT`；domain/regex/case state 均进入 cursor query binding。
- **D-046 Accepted** — GUI 正常关闭是 frontend detach：必须先完成 init/job-monitor/heartbeat cancel+await 与 lease detach，再结束 qasync/Qt event loop；不得关闭 shared daemon，也不得用 `loop.stop()` 隐藏未完成 cleanup。

## Critical ADR mapping

| Decision area | ADR |
| --- | --- |
| Single daemon Session owner | ADR-001 |
| Local Named Pipe JSON IPC | ADR-002 |
| Bounded pagination / safe cursors | ADR-003 |
| Telegram write safety / no auto replay | ADR-004 |
| Migrated logical chat identity | ADR-005 |
| Human E2E release gate | ADR-006 |
| Current-unread export-start snapshot | ADR-007 |
