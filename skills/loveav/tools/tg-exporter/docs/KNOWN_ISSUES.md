# Known Issues

GitHub 当前事实优先于本文。

## Current status

截至 2026-08-30：

- Production 在 v0.3.1 正式发布完成前仍是 `v0.3.0 @ 8e230e33...`；
- v0.3.1 自动化 correctness/package gate 已通过；
- **没有已知未修复的自动化 correctness blocker**；
- 用户已明确授权 v0.3.1 直接发布，并对该版本一次性豁免剩余真实 Windows/Telegram human E2E；
- 被豁免项目记为 **unverified/waived**，不是 PASS。

v0.3.1 发布时仍未在用户真实环境独立验证的类别：真实 packaged domain+regex 查询、真实 GUI 多场景关闭、两个真实 GUI 顺序关闭后的 daemon/tgctl 可用性、真实新日志段异常计数、同一 bounded sender 样本的修复后聚合统计。

## KI-001 — Current-unread snapshot captured too early

**RESOLVED / released in v0.3.0.** 每群在自身 execution start 冻结：

```text
lower = read_inbox_max_id_at_group_start
upper = latest_message_id_at_group_start
export only lower < message_id <= upper
```

export/read-ack 复用同一 upper；post-snapshot 新消息不进入本轮；export failure 不 ack；migrated current-unread 只看 current logical Supergroup。

## KI-002 — Packaged `--url-domain` normalization crash

**RESOLVED in v0.3.1 automated validation.** 修复为显式离线 stdlib IDNA normalization + frozen-build defense + standalone/portable packaged search-filter smoke。非法域名返回 `INVALID_ARGUMENT`。

## KI-003 — GUI normal close could stop qasync loop too early

**RESOLVED in automated v0.3.1 validation; real local close scenarios waived/unverified for this release.** Cleanup 在 event loop 仍存活时完成；local tasks/heartbeat cancel+await；GUI lease detach；shared daemon 不因正常 GUI close 退出。

## KI-004 — Sender/owner diagnostics too coarse + regex gap

**RESOLVED in automated v0.3.1 validation; real sender before/after aggregate waived/unverified for this release.** Sender 使用 Telegram peer fields，不从正文/昵称猜；actual sender 与 forward_origin 分开；unknown 有 unknown_reason；owner visibility 更细；bounded `--regex` 已实现并进入 cursor binding/package smoke。

## Historical regression knowledge

后续修改相邻代码必须保留：qasync no nested blocking modal；packaged UTF-8 `SESSION_BUSY` native exit 8；migration cursor no duplicate/gap；logical/source identity；zero-current-unread empty JSON；proxy safe label 不含 username/password/query；domain/regex packaged smoke。
