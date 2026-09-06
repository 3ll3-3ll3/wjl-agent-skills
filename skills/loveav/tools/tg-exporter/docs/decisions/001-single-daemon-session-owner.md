# ADR-001 — Single Telegram Daemon Owns the User Session

## Status
Accepted for v0.2+；当前 v0.3.0 Production 与 v0.3.1 Candidate 均采用。

## Context
v0.1.x GUI/tgctl direct-open 同一 Telethon SQLiteSession 会产生锁竞争。OS SessionLease 能安全拒绝并发，但无法提供同代 GUI+tgctl 共存和 GUI 关闭后 export 继续运行。

## Decision
使用一个本地 daemon 作为正常路径**唯一** `TelegramClient` / `TelegramService` / `telegram.session` owner：

```text
TG daemon
├─ GUI IPC client
├─ tgctl IPC client
└─ future thin client
```

GUI/tgctl 不 fallback direct Session，不复制 Session。

## Alternatives rejected
- direct GUI/tgctl + OS lock：保留为 v0.1.x legacy compatibility，但不满足新体验；
- second/copied Session：auth 状态分叉，安全性更差；
- always-running Windows Service：生命周期/权限复杂度无必要。

## Consequences
同代 GUI+tgctl 正常应无 `SESSION_BUSY`；legacy direct process 仍可能通过 OS lock 触发 `SESSION_BUSY`；login 仅 GUI；daemon/IPC 成为关键基础设施。

## Risks
Daemon 是共享故障点，因此需要 safe job metadata、明确 shutdown、`DAEMON_UNAVAILABLE` / `WRITE_OUTCOME_UNKNOWN` 等结构化语义。