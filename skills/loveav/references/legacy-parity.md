# v0.5.13 兼容参考（联网适配器默认禁用）

本 Skill 保留 Windows v0.5.13 稳定版本中可复用的用户侧行为，但当前版本明确不启用 Telegram 连接、cloud execution、background queues 或 123AV account actions。

下面的内容用于防止未来迁移时漏掉旧能力，不代表当前版本获得了索要凭据或执行联网副作用的权限。

## 当前兼容宿主可直接复用

- MissAV、Twitter、Bad.news、海角四个确定性文本过滤器。
- 多文件与 pasted text 输入、source recognition、分钟级 time filtering、selection、稳定去重、permanent-history comparison 与 copy-ready output。
- MissAV 番号规范化、detail-link candidates、reference Tag extraction、两层独立 blacklist、经过验证的 browser-script generation 与三目录 Raindrop HTML export。
- 一个 source 可以绑定多个工具；同一消息只接收一次，但每个工具拥有独立 queue/status。某工具失败不得阻塞其他工具。
- Incremental/history/manual-read 语义：
  - `never`：永不改变 Telegram read state；
  - `manual`：等待用户明确确认；
  - `safe_auto`：只有 durable ingestion 成功且 checkpoint 有效后才允许标记已读；
  - historical pull 永不自动 mark read。
- rule versioning、preview/commit/rollback、package manifests、conflict-safe imports、CSV/JSON/TXT generation 与 privacy boundaries。
- task/history/result views、error categories、host 提供时的 retry/resume、business CRUD、snapshots、recycle-bin recovery 与 v0.5.13 business-data migration。

## 当前本地版不启用

- Telegram personal API QR/phone/2FA login、dialog discovery、group/channel history pagination、manual read marking、checkpoints、edit/delete propagation 与 account-safe session storage。
- Telegram Bot API updates、privacy-mode limitations、global offset handling、source discovery 与 source fan-out。
- 123AV exact page verification、独立 lookup pipeline、Chrome extension bridge、in-app serial assistant、10-second rate-limit recovery 与 export-only mode。

如果未来本地宿主增加这些能力，应以明确 capability 形式暴露，例如：

```text
telegram.sources.list
telegram.history.load
telegram.sync.incremental
telegram.mark_read
av123.lookup
av123.account.serial_action
```

其中 `telegram.mark_read` 仍必须要求 manual confirmation。

在这些 adapter 真正存在前，始终保持 manual mode。禁止用网页抓取或不可信 AI 猜测来替代缺失 adapter。

## 环境差异

- 兼容本地宿主可以提供 file access 与小型 local-library adapter。
- 任何环境都不应维护第二套过滤规则。未来 executor 必须调用本 Skill 的 rule contract 或共享的 deterministic implementation。

## 明确不纳入兼容范围

- Work/cloud execution 或自动升级到付费云服务。
- 静默执行 Telegram 或 Raindrop network writes。
- Skill 内直接做 Raindrop API synchronization；默认只生成 import files，除非用户明确启用了独立、可确认的 adapter。
- Skill package 内保存任何 secret、personal database、browser profile 或 raw message archive。