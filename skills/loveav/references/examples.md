# 自然语言示例

这些示例用于说明预期回复结构，不要求逐字照搬。

## Manual MissAV + Twitter

用户：

```text
使用 LoveAV 处理我上传的三个 Telegram HTML。
MissAV 来源提取番号，Twitter 来源提取博主；排除精选库已有记录，返回番号、番号链接、博主名和主页链接。
```

预期行为：

1. 预览全部文件，并展示识别到的来源与数量。
2. 只有来源未绑定或确实存在歧义时才询问用户。
3. 使用当前 rule version 独立处理选中的来源。
4. 分别返回番号、番号链接、博主名、主页链接四个可复制列表，同时报告 `new`、`historical`、`duplicate`、`invalid` 与 error 数量。

## Rule administration

用户：

```text
把这个 Miss_AV.html 导入为新的参考女优 Tag 库，并把两层黑名单分别预览。
```

预期行为：

- 先展示提取出的 Tags、duplicates、边界 Tag 清理结果与两层黑名单影响。
- 只有用户明确确认后才 commit。
- commit 后创建新的 immutable rule version，并刷新可编辑 TXT mirror。

## Data lookup

用户：

```text
查找所有包含 ABF 的 MissAV 结果，只返回番号，一行一个。
```

预期行为：

- 调用带过滤条件的 result query。
- 排除 deleted rows。
- 返回纯文本代码块，代码块内部不放 bullets 或解释文字。

## Same containers, adaptive review

用户：

```text
用 LoveAV 处理这个 CSV，运行 MissAV、Twitter、Bad.news 和海角；不要把不确定的格式直接丢掉，列出可疑项并说明证据。
```

预期行为：

1. 同一个输入容器同时运行四个所选工具。
2. 分开返回 accepted、excluded、`review` 和 error 数量。
3. 遇到新候选形状时，只提出最小确认问题。
4. 最多创建 rule suggestion；不得静默激活 learned rule。

## Legacy opt-in

用户：

```text
使用已经配置好的个人 Telegram 适配器，读取“番号群”今天 09:00 之后的新消息，但先只生成预览，不要标记已读。
```

预期行为：

- 先检查 adapter capability 与 secure-store 状态。
- 预览来源和时间范围。
- 在任何 mark-read 或其他 remote side effect 前停止。
- 如果 adapter 不存在，明确说明当前可用路径是手动导出并上传文件。

## Whos.tv increment

用户：

```text
接着上次记录抓到今天最新。
```

预期行为：

1. 读取 `whostv-state.json`。
2. 使用 `/helps/10250` 生成 incremental console script。
3. 把脚本追加到 `whostv_scripts.md` 最前面。
4. 报告生成的 `.js` 路径和预期 JSON 文件名。
5. 在返回 JSON 通过 deterministic organizer 前，不更新 cutoff。

## Whos.tv returned JSON

用户：

```text
整理 whos_tv_solved_answers_since_2026-08-27.json。
```

预期行为：

1. 运行 organizer。
2. 只有 count、pages、answers、URLs、cutoff 与 ordering 全部通过时，才生成按 Asia/Shanghai 日期命名的 Markdown。
3. 报告四类数量和纯番号数量。
4. 成功后再把 cutoff 推进到第一条记录的 pathname。