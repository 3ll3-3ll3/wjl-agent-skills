# Whos.tv 已解决答案

第五个主功能处理 whos.tv 求助社区的“已解决”答案。它与 MissAV、Twitter、Bad.news、海角相互独立，不进入 MissAV 主体库，除非用户之后明确选择其中的番号入库。

## 固定目录与状态

- Obsidian 仓库：`E:\Desktop\codex项目\whostv-current`
- 最终文档：`已解决答案\YYYY-MM-DD.md`，日期按 `Asia/Shanghai` 计算
- 脚本归档：`脚本归档\whostv_scripts.md`
- 独立脚本：`脚本归档\generated\*.js`
- 整理器：Skill 内的 `scripts/organize_whos_answers.js`
- 当前状态：`.loveav\whostv-state.json`
- 浏览器 JSON 保存目录：`E:\Desktop\codex项目\whostv-current\.loveav\imports`
- 原始返回 JSON：该目录中的 `whos_tv_solved_answers*.json`；文件重名时追加时间戳和随机后缀，不覆盖已有结果。
- 不生成分类 JSON。

Obsidian 仓库是 Whos.tv 私人数据的唯一当前目录。最终 Markdown 和脚本归档可在 Obsidian 中阅读；点目录 `.loveav` 只保存机器状态与原始输入，不能提交进 Skill 仓库。旧路径只作迁移备份，不再写入。

截止帖必须在每次生成脚本时从 `.loveav\whostv-state.json` 读取，不能使用 Skill 内置的静态值。每次成功校验和整理一批新 JSON 后，将第一条记录 URL 的 pathname 写为新截止点；如果它的帖子编号比现有截止点更旧，则不得倒退状态。`/helps/6270` 仅是旧历史截止点，任何时候都不得回退使用。

## 抓取流程

用户要求“前 n 页”或“第 1-n 页”时，调用：

```powershell
node scripts/generate_whostv_scraper.js --pages n
```

用户要求“接着上次记录抓到今天最新”时，调用：

```powershell
node scripts/generate_whostv_scraper.js --incremental
```

每页请求默认超时 30 秒；只在网络明显较慢且用户知情时，才用 `--timeout` 调整为 1000-120000 毫秒。例如：

```powershell
node scripts/generate_whostv_scraper.js --incremental --timeout 45000
```

生成器把独立 `.js` 写入 `脚本归档\generated`，并把完整脚本说明追加到 `脚本归档\whostv_scripts.md` 最前面。脚本必须由用户在已登录的 whos.tv 页面显式启动，Agent 不得代为运行。日常优先使用 `tampermonkey-scripts` 仓库中的 `LoveAV Whos.tv 最新脚本启动器`；油猴入口不可用时，回退为用户在 Console 手动运行。用户明确要求控制 Chrome 时，可先检查可见账户菜单与“登出”；未确认登录就停止。不得使用 `javascript:` URL、原始 CDP 或规避手段。

## 油猴启动器

`LoveAV Whos.tv 最新脚本启动器` 只简化本地脚本选择和启动，不改变抓取、校验或状态语义：

1. 首次在 Whos.tv 页面点击右下角“运行 Whos.tv”，授权 `E:\Desktop\codex项目\whostv-current\脚本归档\generated`。
2. 后续点击时自动扫描最新的 `whostv_incremental_*.js` 或 `whostv_pages_*.js`。
3. 首次运行还需授权 JSON 保存目录 `E:\Desktop\codex项目\whostv-current\.loveav\imports`。此后在同一站点复用目录句柄；授权失效时通过“授权 / 更换 JSON 保存目录”恢复。脚本目录和 JSON 保存目录分别授权。
4. 运行前显示脚本文件、修改时间、模式、截止帖或页数、输出 JSON 和 SHA-256，并校验关键安全标记及项目目录保存模式；旧版 Downloads 脚本提示重新生成。
5. 用户点击“运行最新脚本”后，先确认 JSON 目录可写，再开始抓取；进度在 Console 中逐条显示，面板提供“取消抓取”。成功后显示已保存的实际文件名；用户只需告诉 LoveAV“整理最新 Whos.tv JSON”，无需从 Downloads 搬运或重新上传文件。
6. 启动器负责把完整 JSON 写入用户授权的 imports 目录并回读核验，不生成脚本、不读取或写入状态文件、不整理答案，也不更新截止点。只有 `organize_whos_answers.js` 校验整理成功才更新状态。

油猴脚本源码位于 `tampermonkey-scripts/scripts/loveav-whostv-runner/`。目录句柄保存在站点 IndexedDB，清理站点数据、换域名或撤销权限后可能需要重新授权。浏览器只暴露目录名，不能核验完整磁盘路径；界面必须明确提示用户选择上面的指定 imports 目录，不能把目录同名误称为绝对路径已验证。

Console 手动运行的新脚本也遵守相同保存规则：复用 imports 目录授权，缺失时显示可点击的目录授权面板；不支持目录 API、用户取消或权限拒绝时不开始抓取。禁止回退普通下载。

抓取脚本必须：

- 校验 `location.hostname` 是 `whos.tv` 或其子域；
- 从页面中真实存在的“已解决”入口读取基准 URL，并强制保留 `tab=solved`；即使用户当前停在“全部”列表，也只能抓取已解决列表；
- 按网站真实分页结构请求：第 1 页为 `/helps?tab=solved`，后续为 `/helps/page-n?tab=solved`；需要兼容语言路径时必须从页面入口派生，不能凭空猜测；
- 使用 `credentials: "include"`、`cache: "no-store"` 和页间延时；
- 每页请求必须使用独立 `AbortController` 和超时计时器。超时、取消、HTTP 失败或其他网络错误都必须停止，并且不保存部分结果；
- 启动时说明 Console 显示 `Promise {<pending>}` 在异步抓取期间属于正常现象，并给出明确的取消函数 `window.cancelWhosTvScrape()`；取消函数必须能中止当前请求或页间等待；
- 每页开始请求时打印页码、URL 和超时；每成功收录一条立即打印单行进度，格式包含页码、页内序号、累计数、帖子 pathname 和最多 48 个字符的标题，不打印答案正文；
- 命中增量截止帖时打印“命中截止点，不收录”，不得增加累计数，也不得继续处理该页更旧记录；
- 每页完成时打印该页提取数、收录数、忽略数、累计数与耗时；整次结束时无论成功、失败或取消，都打印状态、已请求页数、已完成页数、累计数、总耗时、是否保存、实际输出文件以及状态未更新；
- 记录每页帖子 pathname 序列；若后续分页返回与前页相同的帖子列表，或某页没有带来新记录且没有命中截止帖，必须按分页失效或无进展报错；跨页重复帖子 URL 仍按严格校验报错；
- 首选 `article[data-help-id], article[data-post-href]`；
- 首选 `[data-post-answer-preview] p`，旧“答案：”结构只作回退；
- 只允许忽略同时明确带有“置顶”和“官方公告”的非答案卡片，并把忽略项写入结果元数据；其他缺少答案区域的帖子必须报错，不能用静默跳过掩盖漏抓；
- 保留答案内真正的 http/https 链接；
- 在 0 条、空答案、HTTP 失败、重复 URL 或增量未找到截止帖时抛错且不保存文件；
- 增量结果不包含截止帖；结果按最新到较旧顺序排列。

浏览器抓取脚本只将完整 JSON 保存到已授权的 imports 目录，不读取或写入 `.loveav\whostv-state.json`。全部抓取与内容校验通过后才创建输出；关闭写入流并回读核验一致后才能报告保存成功。写入失败应中止写入流并清理本轮尚未提交的空文件；已经开始提交或回读失败时必须提示检查实际文件，不能声称肯定没有保存。提交期间取消不能把已落盘结果误报为未保存。超时、取消、解析失败、重复页、无进展或网络错误时不得保存部分抓取结果。没有通过整理器校验的返回数据不得更新截止点。

## JSON 校验与整理

用户告知抓取完成后，先扫描固定 imports 目录中最近生成的 `whos_tv_solved_answers*.json`，结合当前截止点与 `updatedFrom` 识别本轮待处理文件；不要再次整理已经成功导入的旧文件。若存在多个不同截止点的未处理文件，列出简短候选让用户确认，不凭修改时间猜测。找到本轮唯一匹配 JSON 后告知实际文件名并运行：

```powershell
node scripts/organize_whos_answers.js <JSON路径>
```

整理器接受普通数组，或带 `entries` 的对象。对象必须有与 `entries.length` 相等的 `count`。它验证必需字段、连续页码、空答案、重复 URL和增量截止点，并输出总数、页码范围、第一条、最后一条、空答案数和重复数；任一校验失败都不生成最终 Markdown，也不更新状态。

## 四类输出

先从答案中移除 http/https URL，再识别番号。`magnet:` 和 `ed2k:` 不算访问链接。支持 `ABC-123`、`FC2-PPV-123456`、`FC2 PPV 123456`、`030515-821`、`4149-PPV043` 等形式。

分类固定为：

1. 答案只有番号的：有番号，无 http/https URL；
2. 答案只有访问链接的：有 http/https URL，无番号；
3. 答案同时有番号和访问链接的：两者都有；
4. 其他内容：两者都没有。

Markdown 开头是“答案只有番号的”分类中提取出的纯番号列表，大小写不敏感去重且保留首次顺序。随后一级标题顺序固定为：答案只有访问链接的、其他内容、答案同时有番号和访问链接的、答案只有番号的。最后一类不重复展开答案，只说明已收录于开头。其余每条包含二级标题、来源 URL、页码和保留多行的引用块。
