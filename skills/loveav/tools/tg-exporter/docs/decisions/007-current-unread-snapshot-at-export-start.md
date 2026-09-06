# ADR-007 — Current-Unread Snapshot Is Frozen at Each Group's Export Start

## Status
Accepted、implemented、Issue #22 closed，已随 formal v0.3.0 发布；v0.3.1 继续保留回归 gate。

## Context
Current unread 需要确定性的 lower/upper。早期实现把边界冻结在 catalogue refresh，可能比某个 later group 真正开始导出早很多；若无 upper bound，导出过程中持续到来的消息又会使集合不确定。

## Decision
每个 current-unread 群在**该群实际开始执行时**获取一个不可变快照：

```text
lower = read_inbox_max_id_at_group_start
upper = latest_message_id_at_group_start
export only lower < message_id <= upper
```

每群单独 snapshot，不用 catalogue-global/batch-global 值。Optional read acknowledgement 只能 ack 到同一 frozen upper，并且只在：

```text
JSON atomic success
→ checkpoint
→ optional read acknowledgement
```

之后执行。Snapshot 后到达的新消息留在下一轮，不被本轮 ack。

Basic Group→Supergroup current-unread 只使用 current logical Supergroup；legacy Basic Group 只作适当历史 source。Catalogue/workspace GroupInfo 不因 execution snapshot 被原地修改。

## Alternatives rejected
- catalogue refresh snapshot：会 stale；
- no upper/live-unbounded：run 集合不确定且可能误 ack；
- one batch-global snapshot：later groups 开始太晚，语义不符。

## Consequences
每个 unread group 在 execution start 会有一次 fresh read-state lookup。正确性优先；若未来优化性能，不得改变上述语义。

## Risk
Telegram read acknowledgement 推进 read pointer；因此 GUI warning 与 default-OFF policy 必须保留。