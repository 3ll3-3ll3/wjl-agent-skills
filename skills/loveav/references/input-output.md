# 输入与输出契约

## 接受的输入

可以接受以下任意组合：

- 直接粘贴的纯文本；
- 一个或多个 Telegram Desktop HTML 导出文件；
- Telegram Desktop JSON；
- TXT、CSV、MD、LOG 文本文件。

MissAV、Twitter、Bad.news 和海角都接受上述相同输入容器，不要求某个工具必须使用特定文件类型。同一个文件可以同时交给多个已选工具处理，每个工具独立应用自己的提取与复核规则。

HTML 输入应读取可见消息文本、链接、日期、消息 ID 和导出聊天标题。

JSON 输入应支持 Telegram 官方消息与文本数组结构，并在存在时保留明确的聊天或容器身份。

纯文本输入应根据输入标签和内容哈希生成临时来源身份，不得把普通文本伪装成 Telegram 聊天。

## 预览与选择

预览至少报告：

- 文件数量；
- 成功解析数量；
- 时间范围内包含数量；
- 因时间范围排除的数量；
- 来源数量；
- 解析错误数量。

面向用户的时间筛选按分钟精度处理，并包含边界时刻。没有日期的消息默认保留，除非宿主明确采用其他规则。

每个来源必须独立展示标题、类型、数量、稳定键和当前绑定工具。

用户可以：

- 搜索或筛选消息；
- 选择单条消息；
- 选择当前筛选结果；
- 选择全部预览消息。

已选来源缺少工具绑定时，必须在任何数据库写入前停止正式处理并要求用户确认。

同一聊天导出的多段 HTML 应按稳定聊天/导出键合并。不得只因为文件名相似就合并。

## 消息身份与临时隐私

对于已连接的 Telegram 来源，稳定身份可使用：

```text
account_id + chat_id + message_id
```

对于官方导出，使用可获得的最强聊天键配合消息 ID。

对于粘贴文本，使用来源标签配合确定性的内容索引或哈希。

消息内容被编辑时，应更新同一身份，而不是创建全新消息身份。

原始正文只允许临时存在。只有用户明确要求可复制片段时，才可在当前预览或当前回复中展示。原始正文不得进入永久历史、日志、备份、规则包或遥测。

## Svip 来源专用分类

Svip 官方资源回复只接受包含 `chat_id`、`message_id`、结构化 `sender`、回复关系和媒体元数据的 `tgctl` JSON/JSONL。私人配置中的精确 `chat_id` 必须匹配；标题相似不能替代稳定键。

输出分为主结果、待复核和排除三组。每条只保留消息 ID、日期、PikPak URL、分类和证据，不复制原始正文或伪造发送者身份。详细规则见 `svip-resource-replies.md`。

## 结果结构

每条派生记录应携带类似以下字段：

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

这些字段名属于机器接口，保持原样即可；面向用户的解释使用中文。

回复必须把主值列表和辅助链接列表分开，保持原始顺序，并报告数量。

结果不能仅因为来自“新文件”就判定为新增；必须把规范键与永久历史比较。

## 生成文件

- TXT：UTF-8，一行一个值，可复制列表中不加入解释性表头。
- CSV：UTF-8，带表头，正确引用单元格，并对以 `=`、`+`、`-`、`@` 开头的单元格做公式注入防护。
- JSON：使用带版本的外层结构，包含数量、规则版本、来源摘要和结果行；不得包含原始消息正文。
- MissAV 脚本：使用 Skill 内 v0.5.13 原版模板；从正式主体库实时派生参考女优 Tag，应用第一层黑名单后与安全转义的番号、第二层黑名单一同注入。
- MissAV Raindrop CSV：默认使用已验证的脚本结果结构，正确引用 URL、标题、Tags 和三目录字段；第二层黑名单命中项不得写入导入 CSV。
- 主体库 CSV：接受 Raindrop 官方 11 列和 MissAV 脚本 14 列输入，先预览后合并到唯一 `missav-library.csv`；详细规则见 `curated-library.md`。
- 规则包：只有用户明确要求时生成，包含清单版本、创建时间、记录数量、SHA-256 和规则版本；不得把主体库或 Telegram 原文混入规则包。

所有可复制结果都应避免混入额外解释文字。

## MissAV 默认落盘边界

每次 MissAV 处理默认只保存最终的 Raindrop 导入 CSV。番号列表、链接列表和浏览器脚本在对话中分别使用独立代码块返回，不生成 TXT、脚本文件或摘要 JSON，除非用户另行明确要求。
