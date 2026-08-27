# LoveAV

[简体中文](README.md) | [English](README.en.md)

这是面向桌面 Codex 及其他兼容 AI 工具的本地优先可复用 Skill。Skill 是产品主体；本目录默认不保存 Telegram 原文、数据库、Token、Session 或浏览器资料。

## 唯一源码仓库

本 Skill 的 GitHub 主源码仓库是 [`3ll3-3ll3/wjl-agent-skills`](https://github.com/3ll3-3ll3/wjl-agent-skills)。`loveav/` 是其中的 Skill 目录；后续版本以该 monorepo 为准，不再使用旧的独立 `loveav` 仓库作为发布真源。

## 使用

1. 将整个 `loveav` 文件夹作为 Skill 安装或上传。
2. 在对话中使用 `$loveav`，上传 Telegram Desktop 的 HTML/JSON、TXT/CSV/MD/LOG，或直接粘贴文本。
3. 说明要运行的工具、时间范围、是否排除精选库已有记录和需要的输出。默认只做本地/对话内解析，不连接 Telegram。
4. 预览完成后，只勾选你要长期保留的结果入库；未选择的候选不会进入精选历史库。

## Skill 语言规范

本 Skill 的 `SKILL.md` 采用“英文骨架 + 中文业务规则”：

- YAML metadata、`Trigger`、`Workflow`、tool names、function names、paths、commands、JSON/API fields、code 保持英文或原始技术标识；
- 复杂业务规则、异常处理、禁止事项、验收标准和容易误解的细节使用中文；
- 示例贴近真实用户输入语言；
- 不把一句业务规则写成杂乱的中英混合句。

README 与 `references/` 属于人类可读业务文档，默认优先使用中文；确需英文阅读时使用 `README.en.md`，技术标识保持原样。

## v0.5.13 初始化

如需从 v0.5.13 旧库初始化，可运行 `scripts/migrate_v0513_library.py`。它只读打开旧 SQLite，生成 `seen-index.csv`、精选候选、待复核候选、女优 Tag 候选和旧 Raindrop 元数据；默认不会生成正式精选库。只有你明确确认后，才使用 `--activate-ok` 激活 `status=ok` 的候选。

## 包含的 v0.5.13 能力

- MissAV、Twitter、Bad.news、海角四个基线过滤器，并对未知格式提供可疑项复核和确认后学习。
- MissAV 番号规范化、详情链接、浏览器脚本、参考女优 Tag、两层黑名单和三目录 Raindrop 导出。
- 四个前置工具统一接受 Telegram Desktop HTML/JSON、TXT、CSV、MD、LOG、多文件和粘贴文本；支持时间筛选、选择、查重和历史语义。
- 精选结果库、查重索引、规则包，TXT/CSV/JSON 输出，以及 v0.5.13 业务数据迁移契约。
- Whos.tv 已解决答案：控制台抓取脚本、增量截止点、JSON 校验、四类 Markdown 和脚本归档。
- 123AV 的番号解析、页面证据和导出规则；收藏/关注等账号操作不启用。
- Telegram Desktop 文件解析、消息规范化和时间筛选；personal API、Bot、history backfill、checkpoint 和 mark-as-read 不启用。

详细规则位于 `references/`。自适应规则学习见 `references/rule-learning.md`，精选资料库契约见 `references/curated-library.md`。Skill 只决定流程、规则和输出；本版本不包含 Telegram、Work/cloud 或远程账号执行器。

## 版本与边界

规则基线：Windows `missav-manager` v0.5.13（稳定提交 `4e2aad0`）。123AV 和 Telegram 的联网部分仅作为兼容参考，不属于当前启用范围；当前默认不联网、不自动标记已读、不直写 Raindrop。

当前五个主功能是：MissAV、Twitter、Bad.news、海角、Whos.tv 已解决答案。