---
name: loveav
description: 使用本地优先的 LoveAV 工作台处理 Telegram 导出、粘贴文本、精选资料库、v0.5.13 兼容过滤规则、自适应规则复核以及 Whos.tv 已解决答案。
---

# 目标

让 Codex 或其他兼容 Agent 以本地优先方式完成 TG 文本与导出文件的解析、过滤、查重、精选入库、规则复核和结果输出，同时保持与既定 v0.5.13 规则语义兼容。

# 触发条件

当用户要求处理以下任一内容时使用本 Skill：

- Telegram Desktop 导出；
- 粘贴文本；
- TXT、CSV、MD、LOG 文件；
- MissAV 番号；
- Twitter 创作者；
- Bad.news 链接；
- 海角链接；
- 精选资料库记录；
- 自适应规则复核；
- Whos.tv 已解决答案数据。

默认使用手动、本地处理。除非存在独立、受支持的适配器且用户明确要求，否则不得切换到 Telegram 联网执行、云端执行、Raindrop 远程写入或 123AV 账号操作。

# 工作流

1. 识别输入来源、所选工具、时间范围和资料库策略。
2. 预览并规范化全部临时输入。
3. 在正式处理前解析来源绑定。
4. 对每个已选工具应用确定性的基线规则。
5. 把陌生、冲突或证据不足的候选送入自适应复核。
6. 将规范化结果与精选资料库、历史索引和黑名单比较。
7. 优先返回立即可用、可复制的结果。
8. 只持久化用户明确选择的派生记录，或用户明确确认的规则变更。
9. 准确报告失败、未完成步骤和部分完成状态。

# 业务规则

## 工作模式

开始处理前按请求确定模式：

- **手动模式（默认）**：接受粘贴文本，以及 Telegram Desktop HTML/JSON、TXT、CSV、MD、LOG 文件。不连接 Telegram，不索要 API 凭据，也不标记消息已读。
- **本地资料库模式**：预览完成后，只把用户明确选择保留的行加入本地精选库。精选库用于未来查重和参考判断；不能把每一次处理的全部候选都当成永久历史。
- **管理模式**：用于编辑精选记录、参考 Tag、两个 MissAV 黑名单、备份、迁移或冲突复核。大表格编辑优先使用小型本地编辑器。

Telegram personal API、Bot API、Work/cloud、后台同步、远程 Raindrop 写入和 123AV 账号操作不属于当前默认启用范围。不得因为旧版兼容文档存在就主动索要这些凭据或建议执行这些联网操作。

## 本地状态

把 Skill 旁边的 `loveav-data/`，或用户明确配置的目录，视为运行状态目录。精选 CSV、规则文件和本地索引属于用户私有数据，不得随 Skill 发布。

如果本地资料库不存在，则从空库开始并明确说明。升级旧安装时，只有用户明确指出 `tg-toolbox-data/` 时，才能把它识别为旧数据目录；禁止静默移动或删除。

即使宿主存在已连接适配器，默认仍使用手动模式。不能仅因为输入看起来像 Telegram 导出就自动切换为联网模式。

## 输入契约

MissAV、Twitter、Bad.news、海角四个前置工具共用同一输入容器：

- Telegram Desktop HTML/JSON；
- TXT；
- CSV；
- MD；
- LOG；
- 粘贴纯文本。

文件类型只是容器；具体提取内容由所选工具决定。一份输入可以同时运行多个工具，各工具独立应用自己的提取、过滤和复核规则。

Whos.tv 使用单独的返回 JSON 工作流。

## 预览与来源绑定

处理前必须：

1. 一起解析所有粘贴文本和文件；
2. 合并同一导出会话的 Telegram Desktop 多文件；
3. 能取得时保留消息日期、来源和 `message_id`；
4. 按稳定消息身份去重；
5. 原始消息正文只保留在当前请求或当前预览中。

正式处理前，展示每个来源的标题、类型、数量和稳定键。只有稳定键匹配时才复用保存的绑定。

若来源没有绑定，或一个来源可能对应多个工具，必须让用户选择；不得只根据文件名猜测。

## 基线规则与自适应复核

每个工具独立处理，并保持输入顺序。先使用 `references/tool-rules.md` 中的既有基线，再根据 `references/rule-learning.md` 检查陌生或边界候选。

未知格式不能仅因为“不像旧格式”就直接丢弃。证据不足时，状态必须为 `review`。

自适应复核只有三种结果：

- 接受；
- 排除；
- `review`。

对于 `review`，只能临时保留当前回复需要的最小证据片段，说明支持证据、反对证据和最小确认问题；不得猜测。

## 规则学习

用户确认某个结果，不等于确认一条通用规则。

新规则只有同时满足以下条件时，才能晋级为正式规则：

- 用户明确确认这条规则，而不是只确认某一个结果；
- 至少有一个应命中的正例；
- 至少有一个不应命中的负例；
- 作用域明确；
- 回归检查通过；
- 生成新的规则版本。

不同工具的规则必须分开，除非有明确证据证明它们可以共享。

如果当前宿主没有写入适配器，则把规则建议以可复制形式返回；不得声称已经学习或保存。

## 精选资料库与历史

先用精选资料库比较规范化结果键，再报告是否为新结果。

如果 `seen-index.csv` 中已有某个键，但精选库中没有，则应标记为“以前见过但未精选”，不能静默抑制。

只有用户明确选择入库的行，才能进入精选历史。

精选库、已见索引、规则建议和黑名单必须保持不同语义，不能互相混用。

## MissAV 两层黑名单

两个 MissAV 黑名单必须独立应用，不能合并：

- 参考 Tag 黑名单：只取消对应 Tag 的参考匹配资格；
- Raindrop 导出黑名单：只阻止对应结果进入 Raindrop 导出。

命中黑名单不能静默删除精选记录，必须保留适当的排除原因。

## 输出规则

先给简短摘要，再给用户真正需要的可复制结果。解释文字不能混进可复制列表。

不同类型的主值和链接要分开：

- **MissAV**：番号列表与 URL 列表分开；
- **Twitter**：创作者/handle 列表与主页 URL 列表分开；
- **Bad.news、海角**：输出规范化后的直达帖子 URL；
- **Whos.tv**：先校验 JSON，再按固定四类生成 Markdown；
- **通用导出**：支持 UTF-8 TXT、带公式注入防护的 CSV、JSON，以及版本化结果包、资料库包和规则包。

条件允许时，应报告：输入数量、时间排除数量、无效数量、重复数量、历史数量、新结果数量、`review` 数量和错误数量。

只有用户要求时才生成额外文件。

## 只保存派生数据

不得把每次运行的全部记录、Telegram 原文或临时预览永久保存。

只保存用户明确保留的派生行，以及必要的最小元数据，例如：

- 规范化键；
- Tags；
- 规则版本；
- 来源哈希；
- 时间戳。

## 失败报告

必须区分：

- 解析错误；
- 无效候选；
- 网络错误；
- 访问挑战；
- 限流；
- 需要用户确认；
- 部分完成。

只有宿主真正提供检查点或续跑能力时，才能声称支持重试或续跑。不能把超时或单纯 HTTP 状态当成成功。

# Whos.tv 已解决答案

把抓取、继续抓取、校验、整理、分类或更新 Whos.tv 已解决答案视为第五个主功能。执行前读取 `references/whostv-solved-answers.md`。

生成抓取脚本时使用：

```powershell
node scripts/generate_whostv_scraper.js --pages n
```

或：

```powershell
node scripts/generate_whostv_scraper.js --incremental
```

用户提供 `whos_tv_solved_answers*.json` 时，运行：

```powershell
node scripts/organize_whos_answers.js <JSON路径>
```

只有校验成功才能信任输出。校验失败时：

- 不更新截止点；
- 不创建最终 Markdown；
- 不把失败结果当成成功记录。

Whos.tv 文档与 MissAV 精选历史必须分开。只有用户另外选择，才能把 Whos.tv 中提取出的番号加入精选库。

# 宿主逻辑操作

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

如果宿主只能分析而不能写入，仍要在对话中完成解析、过滤和输出，并明确说明用户还需要通过哪个入口保存派生数据。不得假装数据库写入成功。

# 安全与确认

执行任何破坏性本地操作前，读取 `references/safety.md`，并在最后负责时刻取得确认。

以下操作尤其需要确认：

- 导入或覆盖精选数据；
- 删除资料库行；
- 修改正式规则；
- 恢复备份；
- 导出原始消息文本；
- 其他会造成不可逆或高影响修改的操作。

手动解析和当前对话内的派生输出不需要额外确认。

不得要求用户粘贴或上传 Telegram API hash、Bot Token、OTP、密码、Session、cookies、浏览器存储、Raindrop token，或含有这些内容的数据库。

# UI 边界

UI 不是日常工作入口。只有以下情况才优先使用 UI：

- 大批量精选库编辑；
- 规则或黑名单维护；
- 备份与恢复；
- v0.5.13 迁移；
- 对话无法安全表达的宿主能力。

UI 必须调用同一套宿主操作和规则，不能维护第二套业务实现。

# 异常与边界

- 不得因为存在兼容适配器就自动切换为联网模式。
- 不得因为格式陌生就直接丢弃候选。
- 不得把一次智能猜测固化为永久规则。
- 不得把未选择的候选当作精选历史。
- 不得把 Telegram 原文写入长期历史、日志、备份、结果包、规则包或遥测。
- 不得在网络写入、上传、数据库写入或其他外部动作失败时声称成功。
- 不得把 HTTP 200 本身当成业务成功证据。
- 不得绕过登录、CAPTCHA、访问挑战或未知账号状态。

# 最终验收

一次 LoveAV 处理完成前，至少确认：

1. 已识别输入来源和所选工具；
2. 未绑定来源已得到用户选择；
3. 每个工具独立应用自己的规则；
4. 陌生候选没有被静默丢弃；
5. 精选库、历史、黑名单和规则建议没有混淆；
6. 可复制结果中没有混入解释文字；
7. 只保存了用户明确选择的派生数据；
8. 所有失败和未完成步骤都被准确报告；
9. 没有泄露或持久化敏感凭据和 Telegram 原文。

# 示例

用户可以直接这样提出请求：

```text
使用 LoveAV 处理我上传的 Telegram 导出，运行 MissAV 和 Twitter，先预览，不要自动入库。
```

或者：

```text
整理 whos_tv_solved_answers_since_2026-08-27.json，校验通过后再生成最终 Markdown。
```

# 参考资料

- `references/tool-rules.md`：MissAV、Twitter、Bad.news、海角和 123AV 规则；
- `references/input-output.md`：输入容器、规范化、选择和输出契约；
- `references/data-contract.md`：历史、CRUD、数据包、迁移和隐私字段；
- `references/curated-library.md`：精选资料库、去重、黑名单和原子更新；
- `references/legacy-parity.md`：v0.5.13 兼容能力对照；
- `references/v0513-feature-map.md`：旧版功能映射；
- `references/safety.md`：凭据、网络、账号操作、破坏性操作和恢复；
- `references/rule-learning.md`：候选复核、规则建议、晋级和回归；
- `references/examples.md`：自然语言请求和预期回复结构；
- `references/whostv-solved-answers.md`：Whos.tv 抓取、截止点、校验、分类和 Markdown 规则。

如需从旧 SQLite 数据库执行一次性本地迁移，使用：

```powershell
python scripts/migrate_v0513_library.py
```

该脚本只读打开旧库并生成预览；只有用户明确批准时，才能使用 `--activate-ok` 将符合条件的旧库行晋级到精选库。