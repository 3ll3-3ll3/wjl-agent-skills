# ADR-002 — Authenticated Windows Named Pipe with UTF-8 JSON Bytes

## Status
Accepted for v0.2+；当前 Production 使用。

## Context
Single daemon 需要 Windows 本地 GUI/tgctl IPC，但产品不需要网络 server。

## Decision
使用 Windows Named Pipe / `multiprocessing.connection` `AF_PIPE` + 本地认证 + UTF-8 JSON bytes：`send_bytes/recv_bytes`；禁止 pickle object transport；不开放 TCP/HTTP/LAN；本地 IPC identity/auth secret 留在 AppData；大体量导出正文留 daemon-side，不跨 IPC。

## Alternatives rejected
- localhost HTTP/TCP：无用户收益却扩大网络 trust boundary；
- pickle：任意对象反序列化风险和耦合过高；
- Windows Service：不符合按需用户态 daemon。

## Consequences
IPC schema/error code 成为兼容契约；secret 不得进 stdout/log/Git；clients 可唤醒 daemon；Telegram write transport failure 必须区分 outcome unknown。

## Risk boundary
不声称抵抗已完全控制当前 Windows 用户/AppData 的恶意程序。