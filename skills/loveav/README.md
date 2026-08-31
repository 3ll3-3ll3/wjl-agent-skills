# LoveAV

这是面向桌面 Codex 及其他兼容 AI 工具的本地优先可复用 Skill。Skill 是产品主体；本目录默认不保存 Telegram 原文、数据库、Token、Session 或浏览器资料。

## 唯一源码仓库

本 Skill 的 GitHub 主源码仓库是 [`3ll3-3ll3/wjl-agent-skills`](https://github.com/3ll3-3ll3/wjl-agent-skills)。`loveav/` 是其中的 Skill 目录；后续版本以该 monorepo 为准，不再使用旧的独立 `loveav` 仓库作为发布真源。

## 使用

1. 将整个 `loveav` 文件夹作为 Skill 安装或上传。
2. 在对话中使用 `$loveav`，上传 Telegram Desktop 的 HTML/JSON、TXT/CSV/MD/LOG，或直接粘贴文本。
3. 说明要运行的工具、时间范围、是否排除 MissAV 主体库已有记录和需要的输出。默认只做本地或对话内解析，不连接 Telegram。
4. 预览完成后，只确认你要长期保留的 MissAV 结果；它们合并进唯一 `missav-library.csv`，未选择的候选不会进入主体库。

## 语言规范

本 Skill 的说明文档统一使用简体中文，包括 `SKILL.md`、`README.md` 和 `references/`。

只有工具名、命令、路径、参数、代码、字段名、URL、文件名以及其他必须保持原样的技术标识保留英文。除此之外，不再维护英文段落、英文标题或英文 README 副本。

## v0.5.13 初始化

如需从 v0.5.13 旧库初始化，可运行 `scripts/migrate_v0513_library.py`。它只读打开旧 SQLite，生成可复核的番号、Tag 和非敏感 Raindrop 元数据候选；候选还要按 `references/curated-library.md` 的唯一主体库契约预览后才能合并，迁移不会修改现有规则数据。

## 包含的 v0.5.13 能力

- MissAV、Twitter、Bad.news、海角四个基线过滤器，并对未知格式提供可疑项复核和确认后学习。
- MissAV 番号规范化、详情链接、原版浏览器脚本、从正式主体库实时派生的参考女优 Tag、两层黑名单和三目录 Raindrop CSV 导出。
- 四个前置工具统一接受 Telegram Desktop HTML/JSON、TXT、CSV、MD、LOG、多文件和粘贴文本；支持时间筛选、选择、查重和历史语义。
- 单一 MissAV 主体库、Raindrop 官方/脚本 CSV 合并查重、规则包、TXT/CSV/JSON 输出，以及 v0.5.13 业务数据迁移契约。
- Whos.tv 已解决答案：控制台抓取脚本、增量截止点、JSON 校验、四类 Markdown 和脚本归档。
- Svip 官方 PikPak 资源回复：区分 Telegram 已验证管理员来源、业务规则高可信回复、待复核与明确普通成员。
- 123AV 的番号解析、页面证据和导出规则；收藏/关注等账号操作不启用。
- Telegram Desktop 文件解析、消息规范化和时间筛选；个人 API、Bot、历史回拉、检查点和标记已读不启用。

详细规则位于 `references/`。自适应规则学习见 `references/rule-learning.md`，MissAV 主体库与 Raindrop CSV 契约见 `references/curated-library.md`。

生成 MissAV 浏览器脚本时，参考女优 Tag 不再读取 `Miss_AV.html` 或独立 Tag 库，而是扫描正式 `missav-library.csv` 的主 Tags 与全部来源变体。确定性生成器、命令和双层黑名单规则见 `references/missav-browser-script.md`。

## 长期数据设计

- Whos.tv 保持既有固定目录、状态与 Markdown 流程，不移动。
- MissAV 只维护一个 `missav-library.csv` 主体库，并用行级标记记录“来自 Raindrop”和“来自 Skill 新增”。
- 每批 MissAV 结果默认只保存可导入 Raindrop 的 CSV；番号、链接和浏览器脚本在对话中返回，不额外落盘。
- 主体库、批次 CSV 和私人备份可由用户自行使用 Google Drive 同步，但不得提交 GitHub。

主体库导入默认只预览：

```powershell
python scripts/manage_missav_library.py --library <missav-library.csv> --input <Raindrop或脚本结果.csv>
```

确认预览后才可使用 `--commit --confirm WRITE_MISSAV_LIBRARY`。脚本会先备份现有主体库，再执行原子替换；不会生成摘要 JSON 文件。

Skill 只决定流程、规则和输出；本版本不包含 Telegram、Work/cloud 或远程账号执行器。

## 版本与边界

规则基线：Windows `missav-manager` v0.5.13（稳定提交 `4e2aad0`）。123AV 和 Telegram 的联网部分仅作为兼容参考，不属于当前启用范围；当前默认不联网、不自动标记已读、不直写 Raindrop。

当前五个主功能是：MissAV、Twitter、Bad.news、海角、Whos.tv 已解决答案。

Svip 官方资源回复是 Telegram 来源的专用预处理工作流，不作为新的内容工具计数。它消费 `tgctl` 结构化 JSON，在进入后续工具前完成来源证据分类。
