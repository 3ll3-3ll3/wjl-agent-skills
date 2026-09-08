# LoveAV

这是面向桌面 Codex 及其他兼容 AI 工具的本地优先可复用 Skill。Skill 是产品主体；本目录默认不保存 Telegram 原文、数据库、Token、Session 或浏览器资料。

## 唯一源码仓库

本 Skill 的 GitHub 主源码仓库是 [`3ll3-3ll3/wjl-agent-skills`](https://github.com/3ll3-3ll3/wjl-agent-skills)。`loveav/` 是其中的 Skill 目录；后续版本以该 monorepo 为准，不再使用旧的独立 `loveav` 仓库作为发布真源。

## 使用

1. 将整个 `loveav` 文件夹作为 Skill 安装或上传。
2. 在对话中使用 `$loveav`，上传 Telegram Desktop 的 HTML/JSON、TXT/CSV/MD/LOG，或直接粘贴文本。
3. 说明要运行的工具、时间范围、是否排除 MissAV 主体库已有记录和需要的输出。默认只做本地或对话内解析，不连接 Telegram。
4. 预览完成后，只确认你要长期保留的 MissAV 结果；它们合并进唯一 `missav-library.csv`，未选择的候选不会进入主体库。

如果只说“我要使用 MissAV”，LoveAV 会启动简短的对话式操作面板，依次询问消息来源、仅在需要时询问范围，再选择标准处理、全量重查或只预览。也可以直接说“按默认设置处理 MissAV 日常未读”，跳过向导并使用五个固定来源的当前未读、主体库查重和合并脚本预设。

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
- Svip PikPak 链接消息：精确来源内全部合法 PikPak URL 默认接受，发送者身份不参与筛选；输出保留完整消息、链接与密码，并生成独立收藏夹的 Raindrop CSV。
- 123AV 的番号解析、页面证据和导出规则；收藏/关注等账号操作不启用。
- Telegram Desktop 文件解析、消息规范化和时间筛选；用户明确要求时，可通过内嵌 TG Exporter 助手访问个人账号的会话历史与搜索。MissAV 支持一个手动范围来源和五个固定未读来源；五群在每次被调用时合并生成脚本，并在能力可用时分别确认本轮冻结范围已读。Skill 不在后台自动巡检。

详细规则位于 `references/`。自适应规则学习见 `references/rule-learning.md`，MissAV 主体库与 Raindrop CSV 契约见 `references/curated-library.md`。

生成 MissAV 浏览器脚本时，注入脚本的参考女优 Tag 不再读取 `Miss_AV.html` 或独立 Tag 库，而是扫描正式 `missav-library.csv` 的主 Tags 与全部来源变体。浏览器首次运行选择从正式库生成的 `初始女优Tag合集.csv`，以后选择上次生成的最新 `*_女优tag合集.csv` 作为“当前女优 Tag 合集”；这些合集只用于恢复处理进度和女优映射，不是正式主体库，也不会自动写回主体库。确定性生成器、命令和双层黑名单规则见 `references/missav-browser-script.md`。

## 长期数据设计

- Whos.tv 保持既有固定目录、状态与 Markdown 流程，不移动。
- MissAV 只维护一个 `missav-library.csv` 主体库，并用行级标记记录“来自 Raindrop”和“来自 Skill 新增”。
- 每批 MissAV 结果默认只保存可导入 Raindrop 的 CSV；番号、链接和浏览器脚本在对话中返回，不额外落盘。
- 每批 Svip 结果默认生成收藏夹 `Svip PikPak链接消息` 的 Raindrop CSV；已有链接跳过，密码补全或冲突进入单独复核 CSV，不另建 Svip 数据库。
- 主体库、批次 CSV 和私人备份可由用户自行使用 Google Drive 同步，但不得提交 GitHub。

主体库导入默认只预览：

```powershell
python scripts/manage_missav_library.py --library <missav-library.csv> --input <Raindrop或脚本结果.csv>
```

确认预览后才可使用 `--commit --confirm WRITE_MISSAV_LIBRARY`。脚本会先备份现有主体库，再执行原子替换；不会生成摘要 JSON 文件。

Skill 决定流程、规则和输出；完整 TG Exporter 源码作为本地读取助手内嵌在 `tools/tg-exporter/`，LoveAV 通过 `scripts/tg_exporter_adapter.py` 自动定位 `tgctl.exe`、检查兼容性并完成多页读取。它不是第二套业务规则，也不是云端执行器。

直接读取 Telegram 前先在 TG Exporter GUI 登录。之后可以让 LoveAV 自动读取，例如：

```text
用 LoveAV 读取 Svip 最近 1000 条，提取全部 PikPak 链接消息，并生成 Raindrop 导入 CSV。
```

如果要单独检查适配器：

```powershell
python scripts/tg_exporter_adapter.py health
python scripts/tg_exporter_adapter.py history --chat <ref> --total-limit 1000
```

适配器默认不保存原始消息，不发送、不下载媒体。Svip 仍默认只读；MissAV 五个固定来源按 `references/missav-telegram-sources.md` 处理，但当前正式 `tgctl` 尚无命令行标已读接口，无法执行时必须如实报告。Svip 主结果可在目标群唯一确认、dry-run 预览和用户最终确认后，通过 Telegram 真转发保留原消息内容和媒体。

## 版本与边界

规则基线：Windows `missav-manager` v0.5.13（稳定提交 `4e2aad0`）。123AV 和 Telegram 的联网部分仅作为兼容参考，不属于当前启用范围；当前默认不联网、不自动标记已读、不直写 Raindrop。

当前六个主功能是：MissAV、Twitter、Bad.news、海角、Whos.tv 已解决答案、Svip PikPak 链接消息。

Svip PikPak 链接消息消费 `tgctl` 结构化 JSON，校验精确来源并提取全部合法 URL，完成密码绑定、完整消息输出、Raindrop 去重与六列 CSV 生成；发送者身份只作为上下文，不影响筛选。它还可在受确认保护的流程中把选中的原消息转发到收藏群，是独立的第六个主功能。
