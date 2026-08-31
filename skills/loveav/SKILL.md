---
name: loveav
description: 使用本地优先的 LoveAV 工作台处理 Telegram 导出、粘贴文本、MissAV 主体库、Svip 官方资源回复、v0.5.13 兼容过滤规则、自适应规则复核以及 Whos.tv 已解决答案。
---

# 目标

让 Codex 或其他兼容 Agent 以本地优先方式完成 TG 文本与导出文件的解析、过滤、查重、MissAV 精华入库、规则复核和结果输出，同时保持与既定 v0.5.13 规则语义兼容。

# 触发条件

当用户要求处理以下任一内容时使用本 Skill：

- Telegram Desktop 导出；
- 粘贴文本；
- TXT、CSV、MD、LOG 文件；
- MissAV 番号；
- Twitter 创作者；
- Bad.news 链接；
- 海角链接；
- MissAV 主体库记录；
- 自适应规则复核；
- Whos.tv 已解决答案数据。
- Svip 群中的官方 PikPak 资源回复。

默认使用手动、本地处理。除非存在独立、受支持的适配器且用户明确要求，否则不得切换到 Telegram 联网执行、云端执行、Raindrop 远程写入或 123AV 账号操作。

# 工作流

1. 识别输入来源、所选工具、时间范围和资料库策略。
2. 预览并规范化全部临时输入。
3. 在正式处理前解析来源绑定。
4. 对每个已选工具应用确定性的基线规则。
5. 把陌生、冲突或证据不足的候选送入自适应复核。
6. 将规范化结果与唯一 MissAV 主体库和两个既有黑名单比较。
7. 优先返回立即可用、可复制的结果。
8. 只持久化用户明确选择的派生记录，或用户明确确认的规则变更。
9. 准确报告失败、未完成步骤和部分完成状态。

# 业务规则

## 工作模式

开始处理前按请求确定模式：

- **手动模式（默认）**：接受粘贴文本，以及 Telegram Desktop HTML/JSON、TXT、CSV、MD、LOG 文件。不连接 Telegram，不索要 API 凭据，也不标记消息已读。
- **本地资料库模式**：预览完成后，只把用户明确选择保留的 MissAV 行加入唯一 `missav-library.csv`。主体库用于未来查重和参考判断；不能把每一次处理的全部候选都当成永久历史。
- **管理模式**：用于编辑 MissAV 主体库、两个 MissAV 黑名单、备份、迁移或冲突复核。参考女优 Tag 不再维护独立资料库，而是在生成脚本时从正式主体库实时提取。

Telegram personal API、Bot API、Work/cloud、后台同步、远程 Raindrop 写入和 123AV 账号操作不属于当前默认启用范围。不得因为旧版兼容文档存在就主动索要这些凭据或建议执行这些联网操作。

## 本地状态

只有用户明确配置后，才能把指定目录视为私人数据目录。MissAV 主体库、每批 Raindrop CSV、现有规则文件和 Whos.tv 数据都属于用户私有数据，不得随 Skill 发布。

如果 `missav-library.csv` 不存在，则从空库开始并明确说明。不得擅自创建、移动、删除或猜测用户尚未提供的数据目录。Whos.tv 保持其既有固定目录和状态，不迁入 MissAV 数据目录。

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

Svip 官方资源回复使用 `tgctl` 的结构化 JSON/JSONL；处理前必须读取 `references/svip-resource-replies.md`。该功能在 Telegram 可验证身份之外提供明确标注的业务规则高可信分类，但绝不把业务推定伪装成具体管理员身份。

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

## MissAV 主体库与历史

处理 MissAV 时，先用唯一 `missav-library.csv` 比较规范化番号，再报告是否为新结果。不得再维护第二份 `seen-index.csv` 作为长期历史真源。

主体库同时合并用户提供的 Raindrop 官方 CSV 和 LoveAV 处理后确认保留的 Raindrop 导入 CSV；物理上每个规范番号只有一行，逻辑上分别维护 `loveav_in_raindrop`、`loveav_in_skill_added`、`loveav_has_missav` 与 `loveav_has_123av`。同一番号有多个来源时对应标记同时为 `true`，不能重复建行或丢失差异字段。

同一番号多条 Raindrop 记录不得直接合并 Tags。主字段使用高优先级、较新的完整记录；MissAV URL 优先规范化为 `/cn/<番号>`，旧 URL、123AV URL、旧 Tags、Raindrop ID、时间和其他差异全部保存在来源变体中。

任何新 CSV 导入必须先展示新增、重复、补全、冲突、无效、范围外和待复核数量。用户确认后才能备份并原子更新主体库。详细字段、Raindrop 目录过滤和合并规则见 `references/curated-library.md`。

主体库、规则建议和黑名单必须保持不同语义。参考女优 Tag 集合是正式主体库中女优 Tag 的只读派生视图，不是第二份长期资料库；两层黑名单仍保持独立文件和独立语义。

## MissAV 浏览器脚本

生成脚本前必须读取 `references/missav-browser-script.md`。只能使用 Skill 内 `assets/missav-browser-script.txt` 的 v0.5.13 原版模板，并通过 `scripts/generate_missav_browser_script.py` 确定性注入。

参考女优 Tag 的唯一来源改为正式 `missav-library.csv`：扫描每行主 Tags 和 `loveav_variants_json` 中全部来源变体，沿用 v0.5.13 的类型边界规则识别女优 Tag。任何一个已识别女优 Tag 出现在新作品 Tags 中，就视为参考命中。第一层黑名单在注入前从派生集合排除；第二层黑名单独立注入并阻止相应记录进入 Raindrop 导出。

不得继续使用 `Miss_AV.html`、旧内置 Tag TXT、女优合集 CSV 或模型临时猜测作为脚本参考女优库。主体库不存在、格式不合法或无法提取任何女优 Tag 时必须停止生成脚本。

## MissAV 两层黑名单

两个 MissAV 黑名单必须独立应用，不能合并：

- 参考 Tag 黑名单：只取消对应 Tag 的参考匹配资格；
- Raindrop 导出黑名单：只阻止对应结果进入 Raindrop 导出。

命中黑名单不能静默删除主体库记录，必须保留适当的排除原因。

## 输出规则

先给简短摘要，再给用户真正需要的可复制结果。解释文字不能混进可复制列表。

不同类型的主值和链接要分开：

- **MissAV**：番号列表与 URL 列表分开；默认长期落盘仅保存本批最终 Raindrop 导入 CSV，浏览器脚本在对话代码块中返回；
- **Twitter**：创作者/handle 列表与主页 URL 列表分开；
- **Bad.news、海角**：输出规范化后的直达帖子 URL；
- **Whos.tv**：先校验 JSON，再按固定四类生成 Markdown；
- **Svip 官方资源回复**：主结果只包含 Telegram 已验证管理员来源与业务规则高可信回复；待复核和明确排除分别报告；
- **通用导出**：其他工具按请求支持 UTF-8 TXT、带公式注入防护的 CSV 和 JSON；MissAV 的长期默认文件遵守上述单 CSV 边界。

条件允许时，应报告：输入数量、时间排除数量、无效数量、重复数量、历史数量、新结果数量、`review` 数量和错误数量。

只有用户要求时才生成额外文件。

## 只保存派生数据

不得把每次运行的全部记录、Telegram 原文或临时预览永久保存。

只保存用户明确保留的派生行，以及主体库合并所需的最小元数据，例如：

- 规范化键；
- Tags；
- 规则版本；
- 来源哈希；
- 时间戳。

MissAV 每批默认不保存代码 TXT、链接 TXT、浏览器脚本或摘要 JSON。用户需要这些内容时先在对话中以独立代码块返回；只有用户另行明确要求才生成额外文件。

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

## Whos.tv 页面读取与脚本生成的模型要求

- 在“读取 whos.tv 页面结构并生成或修复抓取脚本”这一步，必须使用 GPT-5.6 **Sol** 模型，并把推理强度设为“极高”（或宿主界面中含义相同的最高档位）。
- 该要求覆盖页面结构判断、选择器设计、增量截止点核对、脚本校验和脚本生成；不要求也不允许 Agent 代替用户运行浏览器控制台脚本。
- 如果当前宿主无法选择 Sol 或极高推理强度，必须明确告知用户模型档位无法强制，再停止生成脚本或等待用户切换；不得假装已经满足要求。
- 生成的脚本始终只交给用户，由用户在已登录的 whos.tv 页面 Console 手动运行；Agent 不得通过浏览器自动执行、`javascript:` URL、原始 CDP 或其他绕过方式运行。

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

Whos.tv 文档与 MissAV 主体库必须分开。只有用户另外选择，才能把 Whos.tv 中提取出的番号加入主体库。

# 宿主逻辑操作

把以下逻辑操作映射到当前可用的 MCP、CLI 或本地适配器：

```text
input.preview(files, pasted_text, start, end)
input.process(preview_id, selected_message_keys, source_bindings, tools)
history.search(tool, canonical_query, include_deleted)
rules.get / rules.preview / rules.suggest / rules.review / rules.commit / rules.rollback
results.query / results.copy / results.export
script.generate(codes, missav_library, both_blacklists)
whostv.script.generate(mode, pages_or_cutoff)
whostv.answers.validate / whostv.answers.organize / whostv.state.update
svip.resources.classify(tgctl_messages, private_source_config)
library.preview_import / library.commit_confirmed / library.query / library.update / library.remove
library.backup / library.verify / library.raindrop_filter
rules.export / rules.import_preview
```

当前宿主允许运行本地 Python 时，MissAV 主体库预览使用：

```powershell
python scripts/manage_missav_library.py --library <missav-library.csv> --input <输入.csv>
```

只有用户看过预览并明确确认后，才允许追加：

```powershell
--commit --confirm WRITE_MISSAV_LIBRARY
```

如果宿主只能分析而不能写入，仍要在对话中完成解析、过滤和输出，并明确说明用户还需要通过哪个入口保存派生数据。不得假装数据库写入成功。

# 安全与确认

执行任何破坏性本地操作前，读取 `references/safety.md`，并在最后负责时刻取得确认。

以下操作尤其需要确认：

- 导入、合并或覆盖 MissAV 主体库数据；
- 删除资料库行；
- 修改正式规则；
- 恢复备份；
- 导出原始消息文本；
- 其他会造成不可逆或高影响修改的操作。

手动解析和当前对话内的派生输出不需要额外确认。

不得要求用户粘贴或上传 Telegram API hash、Bot Token、OTP、密码、Session、cookies、浏览器存储、Raindrop token，或含有这些内容的数据库。

# UI 边界

UI 不是日常工作入口。只有以下情况才优先使用 UI：

- 大批量 MissAV 主体库编辑；
- 规则或黑名单维护；
- 备份与恢复；
- v0.5.13 迁移；
- 对话无法安全表达的宿主能力。

UI 必须调用同一套宿主操作和规则，不能维护第二套业务实现。

# 异常与边界

- 不得因为存在兼容适配器就自动切换为联网模式。
- 不得因为格式陌生就直接丢弃候选。
- 不得把一次智能猜测固化为永久规则。
- 不得把未选择的候选当作主体库历史。
- 不得把 Telegram 原文写入长期历史、日志、备份、规则包或遥测。
- 不得在网络写入、上传、数据库写入或其他外部动作失败时声称成功。
- 不得把 HTTP 200 本身当成业务成功证据。
- 不得绕过登录、CAPTCHA、访问挑战或未知账号状态。

# 最终验收

一次 LoveAV 处理完成前，至少确认：

1. 已识别输入来源和所选工具；
2. 未绑定来源已得到用户选择；
3. 每个工具独立应用自己的规则；
4. 陌生候选没有被静默丢弃；
5. MissAV 主体库、来源标记、黑名单和规则建议没有混淆；
6. 可复制结果中没有混入解释文字；
7. 只保存了用户明确选择的派生数据，且 MissAV 默认只落盘本批 Raindrop 导入 CSV；
8. 所有失败和未完成步骤都被准确报告；
9. 没有泄露或持久化敏感凭据和 Telegram 原文。
10. Svip 业务规则结果没有被错误描述为已验证的具体管理员身份。

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
- `references/data-contract.md`：长期数据边界、写入、迁移、同步和隐私字段；
- `references/curated-library.md`：MissAV 唯一主体库、两种 Raindrop CSV、目录过滤、查重和原子合并；
- `references/missav-browser-script.md`：正式主体库女优 Tag 派生、双层黑名单注入和原版脚本生成；
- `references/legacy-parity.md`：v0.5.13 兼容能力对照；
- `references/v0513-feature-map.md`：旧版功能映射；
- `references/safety.md`：凭据、网络、账号操作、破坏性操作和恢复；
- `references/rule-learning.md`：候选复核、规则建议、晋级和回归；
- `references/examples.md`：自然语言请求和预期回复结构；
- `references/whostv-solved-answers.md`：Whos.tv 抓取、截止点、校验、分类和 Markdown 规则。
- `references/svip-resource-replies.md`：Svip 官方 PikPak 回复的双层证据、分类与私人来源配置。

如需从旧 SQLite 数据库执行一次性本地迁移，使用：

```powershell
python scripts/migrate_v0513_library.py
```

该脚本只读打开旧库并生成预览；旧库候选仍必须按 `references/curated-library.md` 的新主体库契约复核后才能合并。不得借迁移过程修改现有规则数据。
