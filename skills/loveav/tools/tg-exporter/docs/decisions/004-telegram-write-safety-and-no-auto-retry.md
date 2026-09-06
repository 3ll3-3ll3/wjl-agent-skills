# ADR-004 — Telegram Write Safety and No Automatic Retry

## Status
Accepted since v0.1.9；daemon/v0.3+ 继续继承。

## Context
`tgctl` 通过用户真实 Telegram user account 操作。目标歧义、重复 retry、延迟队列都可能造成不可逆用户可见副作用。

## Decision
Writes 必须显式、bounded、可 dry-run：forward 必须 Telegram true forward，默认 <=20、explicit large <=200；send 纯文本/`parse_mode=None`；ambiguous target → `AMBIGUOUS_CHAT`。

Failure：FloodWait structured stop；export 活跃时 real send/forward → `EXPORT_IN_PROGRESS`；write 已交 daemon 后 transport disconnect → `WRITE_OUTCOME_UNKNOWN`，**绝不自动 replay**。日志不记录 message body。

## Alternatives rejected
- 自动 retry transient write：可能重复发送；
- queue until export finishes：会造成惊讶的未来发送；
- first-match ambiguous name：高风险误发；
- remove caps：自然语言误指令可能产生大规模副作用。

## Consequences
Automation 必须在 unknown outcome 后先检查目标再由用户决定是否重试。