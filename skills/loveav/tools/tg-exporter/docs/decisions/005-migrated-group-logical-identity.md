# ADR-005 — Basic Group Migration Uses One Logical Current Chat

## Status
Accepted since v0.1.8；v0.3 reader 继续扩展。

## Context
Telegram 可将 legacy Basic Group (`Chat`) 迁移为 Supergroup (`Channel/megagroup`)；Telethon 可能暴露两端。直接展示两端会重复，完全丢 legacy 又会漏历史。

## Decision
Current Supergroup 是 user-visible logical chat，legacy Basic Group 仅 historical source：catalogue 显示一个逻辑群；migration 必须来自 Telegram metadata，不按同名猜；current-unread/since-last 只看 current；date-range/history 可 current→legacy；消息唯一键 `(source_chat_id,message_id)`；legacy rich output 保持 `chat_id=current logical`、`source_chat_id=legacy`。

Current owner/admin role snapshot 以 current logical group 为准，不伪造历史管理员任期。

## Alternatives rejected
- 完全 ignore legacy：漏 pre-migration history；
- 显示两个 chat：用户体验重复；
- same-title merge：会误合 unrelated chats；
- 只按 message_id 去重：peer-local ID 会冲突。

## Consequences
Pagination/search cursor 需要 current/legacy segment；migration metadata 不可用时返回 stale/unavailable，不猜。