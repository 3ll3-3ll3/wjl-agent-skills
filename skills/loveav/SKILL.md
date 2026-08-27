---
name: loveav
description: "Use this skill as a local-first LoveAV content workbench for Telegram exports, pasted text, curated libraries, v0.5.13-compatible filters, and Whos.tv solved-answer collection."
---

# LoveAV Skill

LoveAV 是本地优先、可复用的 TG 内容处理 Skill。它是产品主体，让 Codex 或其他兼容 AI 执行内容解析、过滤、查重和输出；UI 只作为偶尔使用的管理入口。当前规则是稳定基线，遇到陌生输入时再按[自适应规则学习](references/rule-learning.md)流程复核。绝不能静默发明、启用或丢弃规则。

## 工作模式

开始处理前先选择一个模式：

- **手动（默认）：** 接受粘贴文本，以及 Telegram Desktop HTML/JSON/TXT/CSV/MD/LOG 文件。不连接 Telegram，不索要 API 凭据，也不标记消息已读。
- **本地资料库：** 预览后，只把用户明确选择保留的行加入本地精选库。以后用精选库做查重和参考判断；不能把每一条处理记录都当成永久历史。
- **管理：** 只用于编辑精选记录、参考 Tag、两个 MissAV 黑名单、备份、迁移或冲突复核。需要大表格时，优先使用小型本地编辑器。

Telegram 个人 API、Bot API、Work/cloud 执行、后台同步、远程 Raindrop 写入和 123AV 账号操作不属于当前启用范围。v0.5.13 兼容文档只作为参考；默认流程中不得提议这些操作，也不得索要相应凭据。

把本地伴随数据目录（Skill 旁边的 `loveav-data/`，或用户明确配置的目录）视为 Skill 的运行状态。目录中的精选 CSV 和规则文件属于用户私有数据，不得随 Skill 发布。如果伴随库不存在，就从空库开始并明确告知。升级旧安装时，只有用户明确指出 `tg-toolbox-data/` 才能把它识别为旧目录；不得静默移动或删除。

即使存在已连接的适配器，默认仍使用手动模式。不能仅因为某个文件看起来像 Telegram 导出，就自动切换模式。

前四个内容功能（MissAV、Twitter、Bad.news、海角）共用同一输入契约：可组合使用 Telegram Desktop HTML/JSON、TXT、CSV、MD、LOG，或直接粘贴纯文本。文件类型只是容器；具体能提取什么由所选工具决定。一份输入可以同时运行多个工具，各工具独立应用自己的提取、过滤和复核规则。Whos.tv 使用单独的返回 JSON 工作流。

## 标准流程

1. **识别请求。** 确认输入、所选工具、时间范围、本地资料库策略和输出要求。如果缺少必要选择，只问一个简短问题；不能猜设置后直接保存。
2. **预览临时输入。** 一起解析所有粘贴文本和文件。合并同一导出会话的 Telegram Desktop 多文件，能取得时保留消息日期、来源和 message ID，并按稳定消息身份去重。原始消息文本只保留在当前请求/预览内。
3. **处理前展示来源。** 展示每个来源的标题、类型、数量和稳定键。只有稳定键匹配时才复用保存的绑定。来源没有绑定或可能对应多个工具时，必须让用户选择；不能只根据文件名推断。
4. **执行基线规则并复核。** 对每个所选工具独立处理，保持输入顺序并使用规范化键去重。先应用[工具规则](references/tool-rules.md)中的已知基线，再按[规则学习](references/rule-learning.md)中的证据清单检查陌生或边界候选。不能因为格式新就直接丢弃；证据不足时标为 `review`。
5. **应用资料库和黑名单。** 先用精选行资料库比较规范化结果键，再报告“new”。如果可选的 `seen-index.csv` 也包含该键、但精选库没有，就标记为“以前见过但未精选”，不能静默抑制。两个 MissAV 黑名单必须按各自语义、按正确顺序应用，不能合并。新规则建议只有在用户确认并记录回归样本后才能生效。
6. **立即返回有用结果。** 先给简短摘要，再给可复制的纯文本代码块；主值和链接分开。只有用户要求时才生成文件。具体格式见[输入与输出契约](references/input-output.md)。
7. **只保存用户选择的派生数据。** 只保存用户明确保留的行，以及规范化键、Tags、规则版本、来源哈希和时间戳。不能保存每次运行的全部记录、Telegram 原文或临时预览。
8. **准确报告失败。** 分开说明解析错误、无效候选、网络错误、访问挑战、限流、需要用户确认和部分完成。只有主机提供检查点时才提供重试/续跑；不能把超时或单纯 HTTP 状态当成成功。

## 自适应规则学习

当基线无法可靠判断候选时，使用三路结果：接受、排除或 `review`。对 `review` 只在回复中保留临时证据片段，说明相互矛盾的检查项，并提出最小确认问题，不能猜测。把用户确认或拒绝的例子记录为带作用域、理由和误报防护的版本化规则建议。只有同时满足以下条件，建议才能晋级为正式规则：用户明确确认、至少一个应命中的正例和一个不应命中的负例、作用域清楚、回归检查通过，并生成新的规则版本。不同工具的规则必须分开，除非证据证明可以共享。

如果当前主机没有写入适配器，就把建议以可复制形式返回，不能声称已经学会或保存。具体生命周期和字段见[规则学习](references/rule-learning.md)。

## Whos.tv 已解决答案

把抓取、继续抓取、校验、整理、分类或更新 Whos.tv 已解决答案视为第五个主功能。执行前读取[Whos.tv 已解决答案规则](references/whostv-solved-answers.md)。

- 使用 `node scripts/generate_whostv_scraper.js --pages n` 或 `--incremental` 生成完整控制台脚本；不要在对话中手写不完整脚本。
- 用户提供 `whos_tv_solved_answers*.json` 时，运行 `node scripts/organize_whos_answers.js <path>`，只有验证成功才能信任输出。
- 校验失败时，不要更新截止点，也不要创建最终 Markdown。
- Whos.tv 答案文档必须与精选 MissAV 历史分开。只有用户另外选择，才能把提取出的番号加入精选库。

## 统一主机操作

把以下逻辑操作映射到当前可用的 MCP、CLI 或本地适配器：

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

如果主机只能分析而不能写入，仍要在对话中完成解析、过滤和输出，并明确说明用户需要通过 UI 保存哪些派生数据。不能假装数据库写入成功。

## 输出规则

- **MissAV：** 分开输出一行一个番号、一行一个 URL；用户要求时再输出完整浏览器脚本和 Raindrop 导入 HTML。
- **Twitter：** 分开输出创作者/handle 列表和主页 URL 列表。
- **Bad.news、海角：** 一行一个规范化直达帖子 URL；排除 App、栏目、广告、跟踪和垃圾 URL。
- **Whos.tv：** 先校验返回 JSON，再按固定四类顺序生成日期命名的 Markdown，并在最前面放纯番号列表。
- **通用导出：** UTF-8 TXT、带公式注入防护的 CSV、JSON，以及版本化结果包/资料库包/规则包。
- 条件允许时，始终报告输入、时间排除、无效、重复、历史、new、`review` 和错误数量。
- 解释文字不能放进可复制列表；标签和列表必须分开。

## 安全与确认

执行任何破坏性本地操作前，读取[安全规则](references/safety.md)，并在最后负责时刻取得确认。导入/覆盖精选数据、删除资料库行、修改规则、恢复备份或导出原始消息文本前尤其需要确认。手动解析和对话内派生输出不需要确认。

## UI 边界

UI 不是日常工作入口。只有大批量精选库编辑、规则/黑名单维护、备份/恢复、v0.5.13 迁移或对话无法安全表达的主机能力才打开 UI。UI 必须调用同一套主机操作和规则，不能维护第二套实现。

## 文档维护约定

本 Skill 的 `SKILL.md`、README 和 `references/` 源码以简体中文为主，英文仅作为辅助说明或机器兼容文本。阅读和修改文档时先以中文语义为准；不要因为保留英文命令、状态值、字段名或链接就把它们翻译掉。新增规则、流程和示例应先写中文，再按实际兼容需求补充简短英文说明。

## 参考资料

- [工具规则](references/tool-rules.md) — MissAV、Twitter、Bad.news、海角和 123AV 行为。
- [输入与输出契约](references/input-output.md) — 接受的来源、规范化、选择和文件。
- [数据契约](references/data-contract.md) — 历史、CRUD、数据包、迁移和隐私字段。
- [精选资料库](references/curated-library.md) — 精选行 CSV、去重、黑名单和原子更新。
- [旧版能力对照](references/legacy-parity.md) — 仅作为禁用参考保留的 v0.5.13 能力。
- [v0.5.13 功能地图](references/v0513-feature-map.md) — 后续适配器的对照清单。
- [安全规则](references/safety.md) — 凭据、网络、账号操作、破坏性操作和恢复。
- [规则学习](references/rule-learning.md) — 可疑候选、证据复核、建议、晋级和回归样本。
- [示例](references/examples.md) — 自然语言请求和预期回复结构。
- [Whos.tv 已解决答案](references/whostv-solved-answers.md) — 抓取、动态截止点、校验、分类、归档和 Markdown 规则。

如需从旧 SQLite 数据库执行一次性本地迁移，使用 `scripts/migrate_v0513_library.py`。该脚本只读打开旧库并生成预览；只有用户明确批准，才能传入 `--activate-ok`，将成功的旧库行晋级到精选库。
