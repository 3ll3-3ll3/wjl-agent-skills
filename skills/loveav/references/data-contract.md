# 本地数据、精选库与管理契约

## 永久数据

本地宿主只能持久化用户明确选择保留的派生业务数据，例如：

- 来源身份与 tool binding；
- 确定性消息身份与 content hash；
- 规范化结果行及其 lineage；
- 永久精选库记录及其 history key；
- reference Tags、两层黑名单、不可变 rule version 与 diff；
- 待确认规则建议，以及带正/负回归样本的用户确认规则；
- 可选的紧凑 run/output metadata 与错误分类，但不得保存完整输入记录；
- 仅作为本地导出产物的 Raindrop mapping，不得包含 API credential 或 remote session。

禁止把 Telegram message body、OTP、password、API hash、Bot Token、cookie、browser storage 或 session text 持久化到这些表或文件中。

用户选择入库的记录才构成产品的持久知识库。某条处理结果如果用户没有选择保留，即使它曾出现在预览里，也必须保持临时状态。

## 历史语义

- 同一 message/tool pair 再次出现时必须保持幂等，但仍可作为本次运行结果展示。
- 消息被编辑时，应更新原 lineage 并重新处理受影响工具。
- 消息被删除时，应创建 tombstone 或 inactive lineage，不能静默抹掉审计历史。
- 手动文本工具只有在用户选择某条派生结果后才保存；保存后才能参与未来查重与参考判断。
- `historical` 表示 canonical key 已存在于 curated library；它不同于“本次输入内部重复”。

## 精选库文件

权威精选记录保存在本地 CSV 或等价本地表中，至少包含：

```text
tool
canonical_key
primary_value
secondary_value
tags
folder
first_seen_at
last_seen_at
seen_count
rule_version
status
```

可以从权威精选库生成更小的 `history-index.csv` 用于快速查重，但禁止把生成索引当成 source of truth 直接编辑。

Reference Tags 与两个 MissAV 黑名单必须保持独立文件。Tag 黑名单不得删除精选结果；精选库记录也不得静默变成黑名单规则。任何自动建议都先进入 preview，只有用户明确晋级后才生效。

更新必须使用临时文件 + atomic replace，保留带时间戳 backup，并验证 headers、unique keys、UTF-8 和行完整性。规则建议只有在明确确认和回归检查后才能激活。

即使 CSV 被其他 AI 工具打开，本地主机仍负责 locking 与 conflict detection。

## 数据操作

所有 query、create、update、bulk-update、delete、restore、copy 与 export 操作必须通过带 table whitelist 和 field validation 的 host adapter 执行。

大数据量查询使用 cursor pagination。跨页选择应保存 filter descriptor + exclusions，而不是无限增长的 ID list。

破坏性或高影响写入必须满足：

1. 先展示 preview、影响数量以及 conflict/invalid 明细；
2. 取得 operation-specific confirmation token 或用户明确确认；
3. 创建操作前 snapshot；
4. 使用一个 transaction，任一错误则 rollback；
5. 写 audit record，但不得包含 raw text 或 secrets。

UI 可以提供业务视图和高级表格视图，但不得开放任意 SQL。长文本应使用合适编辑器，不要通过反复单字段追问完成大规模编辑。

## 数据包与迁移

Result、library、rule 与 backup package 必须包含 manifest 和 SHA-256。

Import 一律先预览：

- new
- duplicate
- conflict
- invalid
- skipped

确认前不得写入；冲突不得静默覆盖。

v0.5.13 migration 在确认前必须只读：先检查 source integrity/schema/hash，预览 mapping，创建 destination snapshot，再在一个 transaction 中提交业务记录。

可迁移：codes、tags、task history、可靠 source bindings、Raindrop export mappings。

不得迁移：sessions、credentials、read positions、Bot offsets、raw Telegram bodies、caches、network task internals、123AV account state。

## 仅 UI 操作

以下场景可以使用小型 UI：

- 批量 Tag/blacklist 编辑；
- source binding 修正；
- 大量 conflict review；
- database backup/restore；
- legacy migration。

UI 只是本契约的 adapter，不得形成第二套产品逻辑。