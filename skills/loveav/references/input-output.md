# 输入与输出契约

## 接受的输入

可以接受任意组合：

- pasted plain text；
- 一个或多个 Telegram Desktop HTML 导出文件；
- Telegram Desktop JSON；
- TXT、CSV、MD、LOG 文本文件。

MissAV、Twitter、Bad.news 和海角都接受上述相同容器，不要求某个工具必须使用专门文件类型。同一文件可以同时交给多个选定工具处理，各工具独立应用自己的提取与复核规则。

对于 HTML，应读取可见消息文字、链接、日期、message ID 和导出 chat title。

对于 JSON，应支持官方 message/text-array 结构，并在存在时保留明确的 chat/container identity。

对于 pasted text，应根据 input label 与 content hash 创建临时 source identity；不得把纯文本伪装成 Telegram chat。

## Preview 与选择

Preview 必须报告：

- file count；
- parsed count；
- included count；
- excluded-by-time count；
- source count；
- parsing errors。

用户可见的时间筛选以分钟精度包含边界。没有日期的消息默认保留，除非当前 host 明确规定其他策略。

每个 source 必须独立展示：

- title；
- kind；
- count；
- stable key；
- current bound tools。

用户可以选择单条消息、当前过滤结果或全部 preview messages。选定来源缺少 binding 时，必须在任何数据库写入前停止处理并让用户选择。

同一导出 chat 的 multipart HTML 应按稳定 chat/export key 合并。禁止仅因为文件名相似就合并。

## Message identity 与临时隐私

Connected Telegram source 使用：

```text
account_id + chat_id + message_id
```

官方导出文件使用能取得的最强 export-chat key + message ID。

Pasted text 使用 source label + deterministic content index/hash。

内容编辑应更新同一 identity，而不是静默生成新消息身份。

Raw text 只允许临时存在于当前 preview，或用户明确要求的当前回复摘录中。禁止把 raw text 写入 permanent history、logs、backups、result packages、rule packages 或 telemetry。

## Result shape

每条派生结果建议包含：

```json
{
  "tool": "missav | twitter | badnews | haijiao | av123",
  "canonical_key": "stable tool-specific key",
  "primary_value": "code, creator, or URL",
  "secondary_value": "detail/profile URL when applicable",
  "source_key": "transient or connected source identity",
  "rule_version": "immutable version identifier",
  "status": "new | duplicate | historical | invalid | review | error | excluded",
  "reason": "short machine-readable reason"
}
```

返回结果时：

- primary 与 secondary list 必须分开；
- 保留稳定顺序；
- 报告数量；
- 不能因为输入文件是新的就直接把结果标成 `new`，必须先用 canonical key 对比 permanent history。

## Generated files

- `TXT`：UTF-8，一行一个值；可复制列表中不放解释性表头。
- `CSV`：UTF-8，带 header，正确引用单元格；对以 `=`、`+`、`-`、`@` 开头的单元格做 formula-injection protection。
- `JSON`：使用带版本的 envelope，包含 counts、rule version、source summary 与 rows；不得包含 raw message body。
- MissAV script：使用已验证模板，并安全注入 code/tag blocks。
- Raindrop HTML：转义 title/URL/tags，保持三个固定 folder，并输出第二层黑名单排除报告。
- Result/history/rule packages：包含 manifest version、created time、record count、SHA-256、rule version 和 conflict-safe import preview。