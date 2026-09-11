# ADR-008：有界发送即时捕获与快照绑定已读

- 状态：Accepted / implemented / unreleased
- 日期：2026-09-08

## 背景

LoveAV 的 PikPak 通知兑换会在发送关键词后 1～2 秒收到可能很快删除的机器人回复。分离的 `send` 和后续 `history` 会丢回复。处理成功后还需只确认本轮已冻结的未读范围，不得波及后到消息。

## 决定

1. 新增通用 `send.capture`：在唯一 daemon / Session 内先订阅目标会话，再发送一条纯文本，只在有界时间窗内捕获回复。
2. 新增 `messages.unread`：首页冻结 `lower/upper`，后续页使用 HMAC/query-bound cursor 复用同一范围。
3. 新增 `messages.mark_read`：只接受与会话、`lower/upper` 绑定的签名 token，且 `max_id` 必须落在范围内。
4. 三者都是通用 Telegram 原语；PikPak 关键词、URL、密码和收藏规则仍属于 LoveAV。
5. 真实发送/已读均经 `OperationCoordinator.run_write`；导出活跃时立即拒绝。
6. 请求已送达 daemon 后传输失败仍返回 `WRITE_OUTCOME_UNKNOWN`，调用方不得自动重放。
7. 普通 reader、GUI 导出、history/search 的默认行为不变，不引入后台监听或自动规则。

## 后果

- LoveAV 可以不开第二 Session 地可靠捕获短命回复。
- 快照后新消息不会被本轮确认已读。
- 进程崩溃后不能猜测写入是否成功；必须停止并人工复核。
- 真实 Telegram E2E 仍是 Candidate/Release 前的单独验收门槛。
