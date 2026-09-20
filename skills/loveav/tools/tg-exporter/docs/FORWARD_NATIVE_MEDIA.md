# Native Forward Protocol — v0.3.4 Candidate

本文件定义 LoveAV 内嵌 TG Exporter 的通用 `forward` 契约。该能力不包含任何业务关键词、固定群名、机器人成功文案或特定站点逻辑。

## 1. 不变量

`forward` 必须直接调用 Telegram/Telethon 的原生 `forward_messages`。照片和相册不得经过 `download_media`、本地文件、`send_message` 或重新上传。这样由 Telegram 自身保留原照片、caption、caption entities、转发来源和原生转发语义。

CLI 保持兼容：

```powershell
tgctl forward --from <source> --to <destination> --ids <id...> [--dry-run] [--allow-large-batch] --json
```

默认请求上限 20；显式 `--allow-large-batch` 上限 200。相册补全后的实际计划仍有 200 条 hard cap。

## 2. 支持范围

当前原生 forward 支持：

- 纯文字/网页预览消息（保留旧行为）；
- 单张 Telegram 原生照片；
- 带 caption/富文本 entities 的照片；
- `grouped_id` 照片相册；
- 同一来源内单图与多个相册混合。

不支持的媒体不会转换或重传，而是逐条返回 `UNSUPPORTED_MESSAGE`。service message 返回 `SERVICE_MESSAGE`。找不到或当前账号不可访问的请求 ID 返回 `MESSAGE_NOT_FOUND`。

## 3. 相册原子性

只要请求命中一个 `grouped_id`，服务端先在该消息附近读取同一 `grouped_id` 的当前可见成员，并把整个相册作为一个不可拆分的 forward unit。

- 相册成员按源消息 ID 升序；
- 一个相册必须整体进入同一个 Telegram `forward_messages` 调用；
- 100 条 RPC 分批边界不得切开相册；
- 不允许只转发相册中用户点到的那一张；
- 当前可见 grouped 集合若不连续、少于 2 条、超过 Telegram 相册上限，整组返回 `ALBUM_INCOMPLETE`；
- 相册内出现非照片媒体时整组返回 `ALBUM_UNSUPPORTED_MEDIA`。

TG Exporter 不猜测已经永久不可见的历史相册成员；“完整”指当前 Telegram API 对该账号可见、可验证的同一 grouped 集合。

## 4. Protected content

若来源会话的 `noforwards/protected content` 已启用，或消息本身带禁止转发标志，相关消息返回：

```text
CONTENT_PROTECTED
```

不得下载后重新上传绕过 Telegram 的保护。若 Telegram 在真实写入时才返回 forwards restricted，同样把尚未成功的消息标成 `CONTENT_PROTECTED`，不会 fallback 到 send/upload。

## 5. dry-run 返回结构

`dry_run=true` 只做读取与计划，不调用 Telegram `forward_messages`。核心字段：

```json
{
  "requested_ids": [],
  "requested_count": 0,
  "planned_ids": [],
  "forwardable_count": 0,
  "photo_count": 0,
  "album_count": 0,
  "albums": [
    {"grouped_id": 1, "message_ids": []}
  ],
  "excluded": [
    {"message_id": 1, "reason": "MESSAGE_NOT_FOUND", "grouped_id": null}
  ],
  "dry_run": true
}
```

`planned_ids` 是真实写入时将按顺序交给 Telegram 的源消息 ID；如果请求只命中相册中一条，它会包含自动补全的同组成员。

## 6. 真实写入结果与对账

成功写入后除了兼容字段 `successful_ids/failed_ids`，还返回：

```text
destination_message_ids
forwarded_messages[source_message_id, destination_message_id, grouped_id]
destination_before_message_id
destination_after_message_id
```

因此 LoveAV 可以用精确的目标消息 ID 做主对账，并在需要时读取目标侧这些消息的 `forward_origin` 复核来源。`destination_before_message_id` / `destination_after_message_id` 是额外边界信息，不替代精确返回 ID。

本 Candidate **未新增 `forward.capture`**。若未来需要“转发前订阅目标会话并捕获随后机器人回复”，必须设计成通用 Telegram 能力，不能在 TG Exporter 中硬编码任何业务机器人或成功文案。

## 7. 写入不确定性与重试

真实 forward 不自动重试。

- Telegram FloodWait → `FLOOD_WAIT` + `retry_after_seconds`；
- daemon 已收到写请求、IPC 在返回前中断 → `UNKNOWN_OUTCOME`；
- Telegram 请求发出后连接/超时异常，无法确认是否落地 → `UNKNOWN_OUTCOME`；
- Telegram 返回的目标消息 ID 数量不完整 → `UNKNOWN_OUTCOME`。

`UNKNOWN_OUTCOME` 的 details 会区分已经确认成功、当前不确定和尚未尝试的源消息 ID。调用方必须先检查目标聊天再决定人工后续，绝不能自动重发。

## 8. 能力发现

`system.hello` / `tgctl status --json` 增加：

```text
forward.native_photo_album
forward.reconcile_ids
```

存在这些 capability 才能假定当前 daemon 支持本文件的照片/相册和目标 ID 对账契约。
