# ADR-003 — Bounded Reader Pagination and HMAC-Bound Safe Cursors

## Status
Accepted for v0.3+。

## Context
Codex 需要 account-wide dialogs/history/search，但无界读取会造成不可预测网络、内存和延迟；cursor 也不能泄露 Telegram credential-like metadata。

## Decision
所有 reader page 默认 100、最大 500；account-wide candidate scan 继续受独立 hard cap。Cursor 为 opaque base64url token，带版本/method/query fingerprint/safe continuation position + HMAC-SHA256；不得含 access_hash/file_reference/Session/credential；tamper/query mismatch → `INVALID_CURSOR`；continuation unavailable → `CURSOR_STALE`。

Dialogs 用 stable canonical order；history newest→older；migration current→legacy composite segment，唯一键 `(source_chat_id,message_id)`。

v0.3.1 的 normalized url-domain、regex pattern 与 case-sensitive state 同样属于 query fingerprint。

## Alternatives rejected
- `limit=None` / read all：无界资源风险；
- raw Telegram offsets/access hashes：泄露内部/credential-like 数据并耦合 Telethon；
- activity-order completeness pagination：新消息会重排造成 gap/duplicate。

## Consequences
Clients 必须沿 `next_cursor` 续页；搜索可以在 bounded scan 后返回 continuation，而不是一请求扫描整个账号。