# Architecture Decision Records

这里存放长期影响架构、安全或产品语义的 ADR。细粒度 D-xxx 决策索引见 [`../DECISIONS.md`](../DECISIONS.md)。

| ADR | Status | Summary |
| --- | --- | --- |
| [ADR-001](001-single-daemon-session-owner.md) | Accepted / Production | v0.2+ single daemon 是正常路径唯一 Telegram Session owner |
| [ADR-002](002-local-named-pipe-json-ipc.md) | Accepted / Production | Authenticated Windows Named Pipe + UTF-8 JSON bytes；拒绝 TCP/HTTP/pickle |
| [ADR-003](003-bounded-reader-pagination-and-safe-cursors.md) | Accepted / Production | Reader default 100/max500；HMAC/query-bound safe cursor |
| [ADR-004](004-telegram-write-safety-and-no-auto-retry.md) | Accepted / Production | Telegram write 显式/有上限；unknown outcome 不自动 replay |
| [ADR-005](005-migrated-group-logical-identity.md) | Accepted / Production | Current Supergroup 是 logical chat；legacy Basic Group 仅 historical source |
| [ADR-006](006-human-e2e-release-gate.md) | Accepted | CI 不能替代真实 Telegram/Windows acceptance；v0.3.0 已履行，v0.3.1 复用 |
| [ADR-007](007-current-unread-snapshot-at-export-start.md) | Accepted / implemented / released | Current-unread 每群在自身 export start 冻结 lower/upper |

## When to add an ADR

只有当决定会长期影响架构/安全/数据语义、存在多个合理方案、后续 Agent 很可能重新提出已否决方案、或改变后需要迁移/E2E/安全评估时才建 ADR。

普通每日进度、小 bug、CI run/hash 放 `HANDOFF.md` / PR / release notes，不放 ADR。

## Changing an accepted decision

用户明确改变方向时：新建 ADR 或标记旧 ADR Superseded；写清 Context/Decision/Consequences；同步 `docs/DECISIONS.md`、`HANDOFF.md`；涉及 Production/security 时同步 `docs/SECURITY_MODEL.md`；runtime 变化重新按 `docs/TESTING.md` 验证。