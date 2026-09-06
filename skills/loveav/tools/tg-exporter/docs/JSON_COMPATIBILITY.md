# Telegram Desktop JSON Compatibility

本项目输出的是 **Telegram Desktop 风格 JSON**，目标是在“纯文本消息”范围内尽量兼容官方 Desktop 导出，而不是完整克隆 Telegram Desktop 的全量导出器。

## 1. 当前权威输出

每群输出：

```text
<batch>/<group>/result.json
```

外层结构：

```json
{
  "name": "Group name",
  "type": "private_supergroup",
  "id": 123456,
  "messages": []
}
```

普通文本消息当前核心字段：

```text
id
type
date
date_unixtime
from
from_id
reply_to_message_id
edited
edited_unixtime
text
text_entities
```

## 2. 当前做得较好的部分

对普通纯文字消息：

- Telegram message id 保留。
- 时间和 Unix 时间戳保留。
- sender name / sender id 保留。
- reply_to_message_id 保留。
- edit time 保留。
- 中文、Emoji、换行可以写 UTF-8 JSON。
- 媒体消息若存在 caption，可把 caption 当文字保留。

## 3. 已知差异（必须保持诚实）

### 3.1 Rich text entity 未完整映射

当前 `desktop_json.py` 把整段文字作为：

```json
{"type": "plain", "text": "..."}
```

尚未把 Telegram entities 映射为官方 Desktop 风格的：

```text
bold
italic
underline
strikethrough
link
text_link
mention
hashtag
code
pre
blockquote
spoiler
custom_emoji
...
```

结果：文本内容通常仍可读，但格式语义丢失。

### 3.2 `text` 目前按纯字符串设计

Telegram Desktop 对复杂富文本时 `text` 可能是字符串与 entity object 混合数组。当前项目主要输出普通字符串，不保证复杂格式 byte-for-byte 一致。

### 3.3 Chat type 尚需真实判断/验证

历史实现使用 `private_supergroup` 作为常用 chat type。后续需要根据 Telegram entity 真实区分 public/private supergroup/channel/basic group，并与 Desktop 实际输出对照。

### 3.4 Top-level chat id 尚需 differential test

Telethon `get_peer_id()` 对 channel/supergroup 使用 marked peer id（常见 `-100...`）。Desktop 顶层 `id` 的表示不能简单假设等于 `abs(marked_id)`。

在同一群官方 Desktop `result.json` 对照前，不要宣称顶层 chat id 100% 兼容。

### 3.5 Whitespace 原样性

历史导出路径使用 `(message.message or "").strip()`，因此消息开头/结尾空格或换行可能被移除。

推荐后续改进：

- 判断“是否有文字”时使用不破坏原值的方法；
- 写入 JSON 时保留 Telegram 返回的原始文本。

### 3.6 Service messages

Telegram Desktop 会导出 `type: "service"`、actor/action 等信息。当前项目主要聚焦普通文本消息，不保证 service event 完整兼容。

### 3.7 Forward metadata

官方 Desktop 可能保留转发来源、原始 sender/date 等元数据。当前尚未完整映射。

### 3.8 Media metadata 是刻意省略

官方 Desktop 可输出 photo/file/video/audio/sticker 等路径、大小、MIME、宽高、时长等。

本项目产品边界明确：

- 不下载媒体；
- 纯媒体且无 caption 的消息通常不进入结果；
- 有 caption 时只保留 caption 文本。

因此 media metadata 差异不是必须“修复”的 bug，除非用户改变产品方向。

## 4. 建议兼容优先级

优先修纯文本兼容，而不是扩大媒体范围：

### P1

1. 保留原始 whitespace。
2. 精确 chat type。
3. 精确 top-level chat id。
4. 同一群/同一窗口 Desktop differential test。

### P2

5. Rich text entities。
6. Forward metadata。
7. Service message 的“文本分析友好”映射策略。

## 5. Differential test 推荐方法

选择一个小群和同一时间窗口：

1. Telegram Desktop 导出 JSON，关闭所有不需要的媒体下载。
2. 本工具使用完全相同时间范围导出。
3. 按 message id 对齐。
4. 比较：

```text
message count
id
date/date_unixtime
from/from_id
reply_to_message_id
edited
text
text_entities
chat type
chat id
```

5. 把差异分为：

- product-intentional（例如不下载媒体）；
- compatibility bug；
- Telegram API / Desktop 自身语义差异。

6. 将结论写入本文件和 `HANDOFF.md`。

## 6. 不要做的错误兼容

- 不要为了字段看起来像官方而伪造未知值。
- 不要把 marked peer id 当成已验证 Desktop id。
- 不要为了媒体字段开始下载用户没有要求的媒体。
- 不要把 service/media 消息伪装成普通文本消息而不记录这一差异。
