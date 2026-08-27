---
name: loveav
description: Use this skill as a local-first LoveAV content workbench for Telegram exports, pasted text, curated libraries, v0.5.13-compatible filters, adaptive rule review, and Whos.tv solved-answer collection.
---

# Goal

让 Codex 或其他兼容 Agent 以本地优先方式完成 TG 文本与导出文件的解析、过滤、查重、精选入库、规则复核和结果输出，同时保持与既定 v0.5.13 规则语义兼容。

# Trigger

Use this skill when the user asks to process Telegram Desktop exports, pasted text, TXT/CSV/MD/LOG files, MissAV codes, Twitter creators, Bad.news links, Haijiao links, curated-library records, adaptive rule review, or Whos.tv solved-answer data.

Use manual/local processing by default. Do not switch to connected Telegram, cloud execution, Raindrop remote writes, or 123AV account actions unless a separate supported adapter is explicitly enabled and the user requests that capability.

# Workflow

1. Identify input sources, selected tools, time range, and library policy.
2. Preview and normalize all transient input.
3. Resolve source bindings before processing.
4. Apply deterministic baseline rules per selected tool.
5. Route unfamiliar or conflicting candidates to adaptive review.
6. Compare normalized results with the curated library and blacklists.
7. Return useful copy-ready results first.
8. Persist only user-selected derived rows or explicitly confirmed rule changes.
9. Report failures and partial completion accurately.

# Business Rules

## 工作模式

开始处理前按请求确定模式：

- **手动模式（默认）**：接受粘贴文本，以及 Telegram Desktop HTML/JSON、TXT、CSV、MD、LOG 文件。不连接 Telegram，不索要 API 凭据，也不标记消息已读。
- **本地资料库模式**：预览完成后，只把用户明确选择保留的行加入本地精选库。精选库用于未来查重和参考判断；不能把每一次处理的全部候选都当成永久历史。
- **管理模式**：用于编辑精选记录、参考 Tag、两个 MissAV 黑名单、备份、迁移或冲突复核。大表格编辑优先使用小型本地编辑器。

Telegram personal API、Bot API、Work/cloud execution、background sync、remote Raindrop write 和 123AV account actions 不属于当前默认启用范围。不得因为旧版兼容文档存在就主动索要这些凭据或建议执行这些联网操作。

## Local state

把 Skill 旁边的 `loveav-data/`，或用户明确配置的目录，视为运行状态目录。精选 CSV、规则文件和本地索引属于用户私有数据，不得随 Skill 发布。

如果本地资料库不存在，则从空库开始并明确说明。升级旧安装时，只有用户明确指出 `tg-toolbox-data/` 时，才能把它识别为旧数据目录；禁止静默移动或删除。

即使宿主存在已连接适配器，默认仍使用手动模式。不能仅因为输入看起来像 Telegram 导出就自动切换为联网模式。

## Input contract

MissAV、Twitter、Bad.news、海角四个前置工具共用同一输入容器：

- Telegram Desktop HTML/JSON
- TXT
- CSV
- MD
- LOG
- pasted plain text

文件类型只是容器；具体提取内容由所选工具决定。一份输入可以同时运行多个工具，各工具独立应用自己的提取、过滤和复核规则。

Whos.tv 使用单独的返回 JSON 工作流。

## 预览与来源绑定

处理前必须：

1. 一起解析所有粘贴文本和文件；
2. 合并同一导出会话的 Telegram Desktop 多文件；
3. 能取得时保留消息日期、来源和 `message_id`；
4. 按稳定消息身份去重；
5. 原始消息正文只保留在当前预览或当前回复所需范围内。

每个来源必须展示标题、类型、数量和稳定键。只有稳定键匹配时才复用保存的 source binding。来源未绑定或可能对应多个工具时，必须让用户选择，不能只根据文件名猜测。

## 基线规则与自适应复核

对每个所选工具独立处理，保持输入顺序并按规范化键去重。先应用 `references/tool-rules.md` 中的基线规则，再对陌生或边界候选使用 `references/rule-learning.md` 中的证据复核流程。

未知格式不能仅因为“看起来不像旧格式”就直接丢弃。结果必须进入以下三类之一：

- 接受；
- 明确排除；
- `review`。

对 `review` 只保留当前回复所需的最小证据片段，列出支持证据、反对证据和最小确认问题，不得猜测。

只有同时满足以下条件，规则建议才能升级为正式规则：

- 用户明确确认规则，而不是只确认某一条结果；
- 至少有一个应命中的正例；
- 至少有一个不应命中的负例；
- 作用域明确；
- 回归检查通过；
- 生成新的规则版本。

不同工具的规则必须分开，除非证据明确证明可以共享。

如果当前宿主没有规则写入适配器，只能返回可复制的规则建议，不能声称已经保存或“学会”。

## 资料库与黑名单

先使用精选资料库比较规范化结果键，再判断 `new`。

如果 `seen-index.csv` 中已有该键，但精选库没有，只能标记为“以前见过但未精选”，不能静默过滤。

MissAV 的两个黑名单必须保持独立语义：

- reference blacklist：只取消参考女优 Tag 的命中资格，不删除精选番号；
- Raindrop export blacklist：只阻止结果进入 Raindrop 导出，不删除结果本身。

禁止把两层黑名单合并成一个规则。

## 保存规则

只允许持久化用户明确选择的派生数据，例如：

- 规范化结果键；
- 主要结果值；
- Tags；
- 规则版本；
- 来源哈希；
- 时间戳；
- 用户确认后的精选状态。

禁止把每次运行的全部候选、Telegram 原文、OTP、密码、Token、Session、Cookie 或临时预览写入永久资料库。

## Result delivery

先返回简短摘要，再返回可复制纯文本块。主值与链接必须分开，解释文字不能混入可复制列表。

只有用户明确要求时才生成文件。具体格式遵循 `references/input-output.md`。

输出时条件允许应报告：

- input count
- time excluded count
- invalid count
- duplicate count
- historical count
- new count
- `review` count
- error count

## MissAV

- 输出番号时一行一个。
- URL 与番号分开输出。
- 只有用户要求时才生成完整浏览器脚本和 Raindrop 导入 HTML。
- 番号规范化、详情链接、参考女优 Tag、两层黑名单等规则以 `references/tool-rules.md` 为准。
- Skill 默认不得直接请求 MissAV 网站；浏览器脚本只生成，不自动执行。

## Twitter

- 输出 creator/handle 列表与 profile URL 列表，必须分开。
- profile URL 使用 `https://x.com/<handle>`。
- handle 识别、保留和排除规则以 `references/tool-rules.md` 为准。

## Bad.news / 海角

- 一行一个规范化直达帖子 URL。
- 排除 App、栏目、广告、跟踪和其他已确认垃圾 URL。
- 陌生但可能有效的直达帖形状进入 `review`，不要直接丢弃。

## Whos.tv solved answers

把 Whos.tv 的抓取脚本生成、继续抓取、JSON 校验、整理、分类或状态更新视为第五个主功能。

执行前读取 `references/whostv-solved-answers.md`。

Commands:

```text
node scripts/generate_whostv_scraper.js --pages n
node scripts/generate_whostv_scraper.js --incremental
node scripts/organize_whos_answers.js <path>
```

规则：

- 抓取脚本必须由生成器生成，不在对话中手写不完整版本。
- 用户返回 `whos_tv_solved_answers*.json` 后，必须先运行 organizer 校验。
- 校验失败时，不更新 cutoff，也不生成最终 Markdown。
- Whos.tv 文档与 MissAV 精选历史保持分离。
- 只有用户另外选择时，才能把其中提取出的番号加入精选库。

## Host operations

Map the following logical operations to the current MCP, CLI, or local adapter when available:

```text
input.preview(files, pasted_text, start, end)
input.process(preview_id, selected_message_keys, source_bindings, tools)
history.search(tool, canonical_query, include_deleted)
rules.get / rules.preview / rules.suggest / rules.review / rules.commit / rules.rollback
results.query / results.copy / results.export
script.generate(codes, reference_tags, both_blacklists)
whostv.script.generate(mode, pages_or_cutoff)
whostv.answers.validate / whostv.answers.organize / whostv.state.update
library.preview_import / library.commit_selected / library.query / library.update / library.remove
library.export / library.backup / library.verify
rules.export / rules.import_preview
```

如果宿主只有分析能力、没有写入能力，仍应完成解析、过滤和输出，但必须明确说明哪些派生数据尚未保存。禁止假装数据库写入成功。

## UI boundary

UI 不是默认工作入口。只有以下情况才优先使用 UI：

- 大批量精选库编辑；
- 规则或黑名单维护；
- backup/restore；
- v0.5.13 migration；
- 对话无法安全表达的批量数据操作。

UI 必须调用同一套规则和 host operations，不能维护第二套业务实现。

# Edge Cases

- 来源未绑定：处理前停止，并让用户选择工具绑定。
- 文件名看起来像某工具：不能只靠文件名推断来源类型。
- 新格式证据不足：进入 `review`，不接受也不丢弃。
- 用户只确认一条结果：最多加入精选库，不能自动推广成通用规则。
- 规则建议没有负例：不得晋级正式规则。
- `seen-index.csv` 命中但精选库未命中：标记“以前见过但未精选”，不能当成 `historical` 静默过滤。
- 解析失败、HTTP 失败、访问挑战、限流和需要用户确认必须分开报告。
- 单纯 HTTP 200 不能证明页面有效或远程写入成功。
- 没有 host checkpoint 时，不要声称可以安全续跑。
- 没有 write adapter 时，不要声称规则、资料库或状态已经保存。

# Safety Rules

执行破坏性或高影响本地操作前，必须读取 `references/safety.md`。

以下操作尤其需要在最后负责时刻取得明确确认：

- delete / restore / overwrite
- curated library import/replace
- rule commit
- backup restore
- package import
- 导出原始消息正文
- 任何会改变远端账号状态的联网操作

手动解析和对话内派生输出不需要确认。

不得要求用户粘贴 Telegram API hash、Bot Token、OTP、密码、Session、Cookie、Raindrop Token 或包含这些内容的数据库。

# Final Checks

Before finishing a run, verify:

- 所有选定来源都已解析或明确报告失败。
- source binding 没有被猜测。
- 每个工具独立应用自己的规则。
- 未知候选没有被静默丢弃。
- `review` 与正式结果分开。
- 精选库和两个 MissAV 黑名单的语义没有混淆。
- 未选择的候选没有被写入永久精选库。
- Telegram 原文和秘密信息没有进入永久数据。
- 可复制列表内部没有解释文字。
- 主值和链接按要求分开。
- 任何写入、规则晋级、状态更新或远程动作都只有在真实成功后才报告成功。

# Examples

```text
使用 LoveAV 处理我上传的三个 Telegram HTML。
MissAV 来源提取番号，Twitter 来源提取博主；排除精选库已有记录，返回番号、番号链接、博主名和主页链接。
```

Expected flow:

1. Preview all files.
2. Resolve ambiguous source bindings only when necessary.
3. Run MissAV and Twitter independently.
4. Compare canonical keys with the curated library.
5. Return separate copy-ready lists and counts.

```text
用 LoveAV 处理这个 CSV，运行 MissAV、Twitter、Bad.news 和海角；不要把不确定的格式直接丢掉，列出可疑项并说明证据。
```

Expected flow:

1. Run all four tools over the same input container.
2. Separate accepted, excluded, `review`, and error results.
3. Ask the smallest confirmation question for a new candidate shape.
4. Create only a rule suggestion; do not silently activate it.

```text
接着上次记录抓到今天最新。
```

Expected flow:

1. Read `references/whostv-state.json`.
2. Generate the incremental console script.
3. Do not advance cutoff until returned JSON passes deterministic validation.

# References

- `references/tool-rules.md`
- `references/input-output.md`
- `references/data-contract.md`
- `references/curated-library.md`
- `references/rule-learning.md`
- `references/legacy-parity.md`
- `references/v0513-feature-map.md`
- `references/safety.md`
- `references/examples.md`
- `references/whostv-solved-answers.md`

# Maintenance Invariant

本 Skill 的机器结构保持英文，复杂业务规则保持中文。新增业务规则、边界和验收要求时，优先写成完整中文句子；tool names、paths、commands、JSON/API fields 和 code 保持原样。不得为了形式把一条规则写成杂乱的中英混合句。