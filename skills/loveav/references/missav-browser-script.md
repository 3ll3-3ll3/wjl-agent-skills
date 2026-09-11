# MissAV 浏览器脚本规则

## 权威来源

- 完整脚本模板：`assets/missav-browser-script.txt`，来自 Windows v0.5.13 已验证原版。
- 参考女优 Tag 真源：用户配置的正式 `missav-library.csv`。
- 类型边界：`assets/missav-type-boundary-tags.txt`。
- 确定性生成器：`scripts/generate_missav_browser_script.py`。

当前本机正式库为：

```text
E:\Desktop\codex项目\LoveAV-Data\missav\library\missav-library.csv
```

默认黑名单位于同一数据树：

```text
E:\Desktop\codex项目\LoveAV-Data\missav\rules\1-参考女优Tag库黑名单.txt
E:\Desktop\codex项目\LoveAV-Data\missav\rules\2-Raindrop导出黑名单.txt
```

路径不存在时必须要求用户指定实际正式库，不能回退到 `Miss_AV.html`、旧内置 Tag TXT、浏览器运行检查点 CSV 或模型临时生成的名单。

## 参考女优 Tag 派生

每次生成脚本时重新读取正式主体库，不维护第二份参考女优资料库：

1. 读取每行主 `tags`。
2. 解析 `loveav_variants_json`，读取每个 MissAV/123AV 来源变体的 `tags`。
3. 每组 Tags 保持原顺序，从开头逐项判断。
4. Tag 命中系统标签、类型边界、包含数字/空白/网址，或不符合中文、日文、合法拉丁姓名形状时停止读取该组后续 Tags。
5. 对识别出的女优 Tag 精确去重，保留首次出现顺序。
6. 应用第一层参考女优 Tag 黑名单后得到最终 `REFERENCE_ACTRESS_TAGS`。

该集合的语义是：新作品的最终 Tags 只要含其中任一完整 Tag，即视为参考女优命中。派生过程只读，不修改主体库、不生成长期参考库文件，也不把普通类型 Tags 自动当成女优。

## 当前女优 Tag 合集与主体库

必须区分正式数据真源和浏览器运行检查点：

- `missav-library.csv`：正式长期主体库和最终查重真源；
- `初始女优Tag合集.csv`：从正式主体库生成的首次运行快照，历史第一次运行时选择它；
- `*_女优tag合集.csv`：每次浏览器处理生成的检查点，记录已处理番号及其女优映射；下一次运行选择最新一份作为“当前女优 Tag 合集”。

当前合集用于跳过已处理番号、延续女优映射并生成下一份合集，不作为脚本参考女优 Tag 的权威来源。它不得自动覆盖、改写或反向合并到 `missav-library.csv`。只有用户明确确认保留的 Raindrop CSV，经过主体库导入预览和确认后，才能合并进正式主体库。

## 默认工作目录

当前本机的当前女优 Tag 合集父目录和脚本输出根目录是同一个目录：

```text
E:\Desktop\codex项目\LoveAV-Data\missav\results
```

浏览器安全规则不允许控制台脚本仅凭绝对路径直接获得磁盘读写权限。因此启动面板按以下方式工作：

1. 首次在同一 MissAV 站点域名下运行时，用户只需授权一次上述 `results` 目录。
2. 脚本将 `FileSystemDirectoryHandle` 保存在该站点本地的 IndexedDB 中，不保存凭据或文件内容。
3. 后续启动会自动恢复目录句柄，递归扫描最新的 `*女优tag合集.csv` / `*女优Tag合集.csv`，并将它作为当前运行检查点。
4. 点击“开始处理”时，脚本自动在同一 `results` 目录下创建 `YYYYMMDD_HHmm_missav_import` 子目录并保存本次输出。
5. Chrome 清理站点数据、使用隐私模式、更换 MissAV 域名或撤销文件权限后，可能需要重新授权；脚本只在这种情况下再次询问。
6. 不保留浏览器普通下载兜底。无法取得 `results` 的可写目录句柄、创建本批子目录失败或写入失败时，必须停止并提示重新授权；不得把任何本批结果写入 Downloads。

面板中的“授权 / 更换默认工作目录”必须在点击后直接打开 Chrome 目录选择器，不得因为已经记住旧目录而静默返回。“重新扫描最新女优 Tag 合集”必须立即显示扫描中状态，并在完成后显示完成时间；即使扫描结果没有变化，也不能表现为无响应。

面板必须显示实际扫描到的最新合集相对路径和修改时间，并保留“更换默认工作目录”和“手动选择合集”作为纠错入口。

本批目录固定使用 `YYYYMMDD_HHmm_missav_import` 命名，保存在 `results` 之下。五类浏览器产物必须进入同一个本批目录：三目录 HTML、Raindrop 导入 CSV、处理报告 CSV、最新女优 Tag 合集 CSV 和失败备份 JSON。浏览器 Downloads 不属于 MissAV 正式输出位置。

## 油猴启动器

日常运行优先使用 `tampermonkey-scripts` 仓库中的 `LoveAV MissAV 最新脚本启动器`，不再要求用户把完整浏览器脚本复制到 Console：

1. 用户在 MissAV 页面点击右下角“运行 LoveAV”。
2. 首次授权上述 `results` 目录；启动器与生成脚本复用同一 IndexedDB 目录句柄。
3. 启动器递归选择最新的 `*_missav-browser-script.js`，并展示相对路径、修改时间、番号数量和 SHA-256。
4. 只有文件名与 LoveAV 脚本结构校验同时通过时，才允许用户点击“运行最新脚本”。
5. 运行后继续使用原有 MissAV 导入面板；所有分类、黑名单、节流、检查点和输出规则保持不变。

油猴脚本只是本地启动入口，不生成或改写浏览器脚本，不读取 Telegram，不更新主体库。Tampermonkey 不可用时，才回退为用户手动在 Console 运行完整脚本。

## 两层黑名单

- 第一层黑名单在生成脚本前从派生参考集合中排除完整 Tag；它只取消参考命中资格。
- 第二层黑名单注入 `RAINDROP_EXPORT_BLACKLIST_TAGS`；作品命中任一完整 Tag 时不写入 Raindrop HTML/CSV，但处理报告保留记录与原因。
- 两层黑名单均为 UTF-8 TXT、每行一个完整 Tag；不得合并语义。`# `（井号后紧跟一个空格）开头的行是说明注释，不作为 Tag；以井号开头但没有该空格的真实 Tag 不受影响。

## 生成命令

```powershell
python scripts/generate_missav_browser_script.py `
  --library <missav-library.csv> `
  --codes-file <一行一个番号.txt> `
  --reference-blacklist <第一层黑名单.txt> `
  --export-blacklist <第二层黑名单.txt> `
  --output <完整脚本.js>
```

省略黑名单参数时，生成器必须从 `<主体库目录的上一级>\rules\` 自动读取上述两个固定文件名。第一层允许是 0 字节空文件；任一文件缺失时必须停止并报出路径，不能静默当成空列表。显式参数只用于迁移、测试或用户另行指定的数据目录。番号也可以通过可重复的 `--code <番号>` 传入。

生成器必须报告主体库行数、来源变体数、两层黑名单路径/条数/哈希、黑名单前女优 Tag 数、第一层命中数、最终注入数、番号数以及主体库、模板、输出脚本的 SHA-256。报告不得输出完整私人 Tag 列表。

## 模板与执行边界

- 以原版模板为基线，注入只涉及 `CODE_TEXT`、`REFERENCE_ACTRESS_TAGS`、`RAINDROP_EXPORT_BLACKLIST_TAGS` 三个数据区；生成器随后可以应用有专项测试的等价性能补丁。
- 当前 `safe-fetch-v1` 只移除已证明无效的等待：明确的非瞬态 HTTP 4xx 不重复请求；最后一次重试、最后一个候选和最后一个番号之后不再额外等待。网络异常、408、425、429 与 5xx 仍重试一次。
- 性能补丁不得增加并发、删减候选地址、缩短番号之间 900ms 节流、改变解析/分类/文件格式或把失败冒充成功。模板锚点不匹配时必须停止生成，不能静默跳过补丁。
- 缺少任一占位区、模板不是异步浏览器脚本、正式库格式错误或最终参考集合为空时停止。
- Agent 只把完整脚本交给用户；脚本由用户在已登录的 MissAV 页面 Console 手动运行。启动面板第一步统一显示“选择当前女优 Tag 合集”；首次运行选择 `初始女优Tag合集.csv`，后续选择上次生成的最新合集。
- 不使用 `javascript:` URL、原始 CDP 或其他绕过方式代替用户运行。
- 原版三目录和优先级保持不变：`需要查找` 优先，其次 `参考女优Tag命中`，最后 `其他`；三个目录即使为空也创建。
- 123AV 数据只通过主体库来源变体贡献已识别女优 Tag，不触发 123AV 网络或账号操作。

## 长期保存边界

完整脚本默认在对话中返回，只有用户要求时才保存 `.js`。每批长期业务结果仍只有用户确认保留的最终 `*_missav_raindrop_import_threeway.csv`；`*_女优tag合集.csv` 作为下一次运行所需的检查点另外保留，但不属于正式主体库。脚本、代码 TXT、链接 TXT 和摘要 JSON 默认不长期保存。
