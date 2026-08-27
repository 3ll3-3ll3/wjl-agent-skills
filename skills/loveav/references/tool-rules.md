# 工具规则

这些规则继承自 Windows v0.5.13 的稳定基线。它们是行为规则，不代表 Skill 可以在没有用户明确请求的情况下访问对应网站。

基线规则也不是封闭式拒绝列表：完成基线判断后，陌生候选必须进入 `rule-learning.md` 定义的 adaptive review lifecycle。

## MissAV

- 番号统一转为大写；空格或下划线分隔符规范化为 `-`；连续多个连字符压缩；FC2 变体统一为 `FC2-PPV-<digits>`。
- 接受既定的字母数字番号形状，即 `letters-digits` 加可选、已验证 suffix。
- 明确排除普通说明文字、无关网站 URL、日期、栏目标签和明显噪声。
- 输入中存在可信 MissAV detail URL 时应保留；只有当前 host rule adapter 支持时，才在缺少详情链接时生成规范化 MissAV URL。
- 边界形状或新形状必须进入 `review` 并附证据，禁止静默丢弃。
- 类似 `https://missav.ai/dm558/110223-001` 与 `https://missav.ai/dm166/pondo-030326_001` 的 URL 应视为 detail-page candidate；可信 detail path 已提供 identifier 时，不强制要求短 `AA-999` 形状。
- Browser script 必须来自已验证用户模板。只允许注入规范化后的 `CODE_TEXT`、当前 reference actress tags 和 export blacklist。注入前必须转义 backticks 与 `${`。如果模板缺少必要 placeholder，不得自行编造替代脚本。
- Reference Tag blacklist 只取消该 Tag 的参考匹配资格，不删除 source library 中的 Tag，也不阻止影片进入非参考输出目录。
- Raindrop export blacklist 与 reference blacklist 独立；命中后设置 `include_in_import=false`，阻止进入生成的 Raindrop HTML/CSV，但 audit/report 仍保留被排除记录与原因。
- Bookmark output 固定创建三个 folder：`参考女优Tag命中`、`需要查找`、`其他`。对于 not-found、access-challenge 和 unresolved metadata，`需要查找` 优先级最高，避免不确定项被 Tag 命中掩盖。
- Actress Tag reference HTML 提取读取 bookmark `TAGS`，去除系统/类型边界 Tag 和重复项，识别既定日文/中文/拉丁姓名形式；先 preview，用户确认后才替换 reference library。
- Skill 默认不得直接调用 MissAV 网站。Browser script 是默认网络机制。

## Twitter

- 优先把每条消息中的 ASCII `#tag` 作为 creator signal。
- `@handle` 和 `x.com` / `twitter.com` profile URL 作为 fallback。
- Handle 只能包含 1–15 个 ASCII letters、digits 或 underscore。
- 排除明显保留路径：`home`、`explore`、`search`、`settings`、`login`、`messages`、`notifications`。
- 排除明显短 topic tag 和推广/门户 Tag，尤其是紧跟“传送门”的 Tag。
- 边界 handle 进入 `review`，不得静默排除。
- mention fallback 时排除以 `_bot` 结尾的 handle。
- 去重时忽略大小写，但保留首次出现顺序。
- creator name 与 profile URL 必须分开返回；主页 URL 使用 `https://x.com/<handle>`。

## Bad.news

- 只接受 canonical host 下的 `https://bad.news/t/<digits>`。
- 规范化时去除 optional query、fragment 和 trailing path。
- 排除已确认的 `/app`、category page、home page、tracking URL、advertisement 与 non-post link。
- 按 canonical URL 精确去重，并保留首次出现顺序。
- 陌生但看起来可能有效的 post path 进入 `review`。

## Haijiao

- 只接受以下七个 category 下的 numeric direct post：`hjjd`、`hjmz`、`hjyc`、`hjfn`、`hjsz`、`hjrq`、`hjhj`。
- 规范化为 `https://www.haijiaolove.xyz/<category>/<digits>.html`。
- 排除已确认的 old domains、category pages、ads、redirects、tracking parameters 与其他 site paths。
- 新的 numeric direct-post shape 必须先结合 URL evidence 复核，再决定是否排除。

## Whos.tv solved answers

- 这是第五个启用工具，属于 batch collection + document generation workflow，不是 Telegram text filter。
- 必须使用 `scripts/` 中的 deterministic generator 与 organizer。
- dynamic cutoff 与 Markdown 契约以 `whostv-solved-answers.md` 为准。
- Whos.tv 成功结果不得自动进入 MissAV curated library；提取出的番号只有在用户明确选择后才能入库。

## 123AV（仅 legacy connected mode）

- query、account action 与 export 必须分开处理。
- Query 必须从 page title/body 验证 exact code evidence，不能把“只拿到 URL”当成成功。
- missing、access challenge、login required、timeout、network error 必须分开分类。
- Account action 必须 single-lane per site。
- 支持模式仅包括 Chrome extension、in-app serial assistant 与 export-only。
- 禁止读取 password、cookie、Local/Session Storage 或完整 page HTML。
- 普通网络失败或 `Error 1015` 时等待 10 秒再继续；未知 login/CAPTCHA state 必须变成 `verify_required` 并停止 side effect。